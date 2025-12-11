import os
import json
import yaml
import sqlite3
import asyncio

from datetime import datetime, timedelta
from telethon import TelegramClient
from pathlib import Path
from config_loader import load_config
from score import score_and_classify
from collections import Counter
from db import DB
from formatter import format_post_block  


conf = load_config()
cfg = conf["cfg"]
ENV = conf["env"]

# helper: parse chat id to int if possible, otherwise return as-is (string)
def _parse_chat_id(val, default):
    if val is None or val == "":
        return default
    try:
        return int(val)
    except Exception:
        return val

# use ENV values first; fallback to prior hardcoded defaults or cfg/os envs
API_ID = int(ENV.get("TG_API_ID", os.getenv("API_ID", "0")))
API_HASH = ENV.get("TG_API_HASH", os.getenv("API_HASH", ""))
PHONE = ENV.get("PHONE", os.getenv("PHONE", "+79608133326"))
SESSION = ENV.get("TG_SESSION", os.getenv("TG_SESSION", os.getenv("SESSION", "job_watcher.session")))

_target_from_env = ENV.get("TARGET_CHAT") or ENV.get("TARGET_CHAT_ID") or os.getenv("TARGET_CHAT")
TARGET_CHAT = _parse_chat_id(_target_from_env, os.getenv("TARGET_CHAT", -1003309146574))

DB_PATH = cfg.get("db_path") or ENV.get("DB_PATH") or os.getenv("DB_PATH", "jobwatcher.db")

CHANNELS = cfg.get("channels", [])


# 3.0 - Db init

db = DB(DB_PATH)
print("DEBUG: DB initialized, columns in 'seen':", db.get_columns())

# 4.0 TELETHON 
client = TelegramClient(SESSION, API_ID, API_HASH)


# 4.0 SCAN HISTORY
async def scan_history(client: TelegramClient, hours: int = 24, limit_per_channel: int = 2000):
    since = datetime.utcnow() - timedelta(hours=hours)
    results = []

    for ch in CHANNELS:
        print(f"[scan_history] Сканируем {ch}…")
        processed = 0
        async for msg in client.iter_messages(entity=ch, limit=limit_per_channel):
            if not msg:
                continue
            msg_date = getattr(msg, 'date', None)
            if msg_date is not None:
                msg_date = msg_date.replace(tzinfo=None)
                if msg_date < since:
                    break
            text = msg.message or getattr(msg, 'caption', '') or ''
            if not text:
                continue

            unique = f"{ch}::{text[:500]}"
            if db.has_seen(unique):
                continue


            res = score_and_classify(text, cfg)
            final = res.get('final_score')
            summary = res.get('summary')
            pos_sum = res.get('positive_sum', 0)
            neg_sum = res.get('negative_sum', 0)
            matches = res.get('matches', {})

            status = summary if final is not None else 'Отброшено'
            db.upsert_seen(
                msg_unique=unique,
                channel=ch,
                msg_id=msg.id,
                status=status,
                score=(final if final is not None else None),
                pos_sum=pos_sum,
                neg_sum=neg_sum,
                matches_json=json.dumps(matches, ensure_ascii=False),
                raw_text=text,
            )

            if final is not None and not summary.startswith('Точно нет'):
                results.append({
                    'channel': ch,
                    'msg_id': msg.id,
                    'final': final,
                    'pos': pos_sum,
                    'neg': neg_sum,
                    'summary': summary,
                    'preview': text[:800]
                })

            processed += 1
        print(f"[scan_history] {ch} обработано ~{processed} сообщений")
    return results


# 6.0 FETCH MESSAGES

async def fetch_messages(hours: int = 24, batch_size: int = 5):
    """
    Запускает сканирование истории каналов за последние `hours` часов,
    записывает в БД (scan_history делает это) и после формирует/отправляет отчёт.
    """
    print(f"[fetch_messages] Сканирование каналов за последние {hours} часов…")
    # scan_history должен вернуть список результатов с ожидаемыми полями
    results = await scan_history(client, hours=hours)

    if not results:
        print("[fetch_messages] Релевантных сообщений не найдено.")
        # отправляем в чат уведомление о пустой выборке
        await client.send_message(TARGET_CHAT, "Ничего релевантного за период не найдено.")
        return

    # вызов общей функции отправки/форматирования
    await send_results(client, results, TARGET_CHAT, batch_size=batch_size, pause_sec=4.0)

MESSAGE_LIMIT = 4000  # безопасный лимит (Telegram ~4096)

def _truncate_to_fit(block: str, limit: int = MESSAGE_LIMIT) -> str:
    if len(block) <= limit:
        return block
    # аккуратно обрезаем контент — пробуем обрезать preview (последняя часть блока)
    # предполагаем, что preview в блоке идёт в конце, и есть маркер разделения перед ним
    trunc = block[:limit - 1]  # простая обрезка
    # стараемся не резать середину эмодзи/UTF-8, но Python строка — безопасно
    return trunc + "\n…"

async def send_results(client, results: list, target_chat_id, batch_size=None, pause_sec: float = 1.2):

    """
    Надёжная отправка результатов:
    - сначала отправляет заглавный отчет о запуске,
    - затем посты по одному (с обрезкой если нужно),
    - в конце итоговый отчет с реальными счетчиками.
    """
    total = len(results)
    if total == 0:
        await client.send_message(target_chat_id, "Ничего релевантного за период не найдено.")
        print("[send_results] Нечего отправлять.")
        return

    # Считаем статистику до отправки
    counts_by_summary = Counter(r.get("summary", "Нет метки") for r in results)
    # формируем стартовый отчет
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [
        f"JobWatcher — отчёт сканирования",
        f"Время: {now}",
        f"Найдено: {total} пост(ов)",
        "Распределение по итогам:"
    ]
    for k, v in counts_by_summary.items():
        header_lines.append(f"  {k}: {v}")
    header_lines.append("")  # пустая строка
    header_text = "\n".join(header_lines)
    try:
        await client.send_message(target_chat_id, header_text)
    except Exception as e:
        print(f"[send_results] Ошибка при отправке header: {e}")

    sent = 0
    failed = 0
    failed_items = []

    # Отправляем посты по одному — так проще контролировать длину и ошибки
    for idx, item in enumerate(results, start=1):
        block = format_post_block(item)  # используем вашу форматирующую функцию
        # защищаем от слишком длинного блока
        if len(block) > MESSAGE_LIMIT:
            # попытаемся укоротить preview внутри item и пересобрать
            preview = item.get("preview", "")
            # оценка длины: сколько символов нужно убрать
            excess = len(block) - MESSAGE_LIMIT + 100  # +100 запас
            if preview and len(preview) > excess:
                new_preview = preview[:-excess] + "…"
                item_short = dict(item)
                item_short["preview"] = new_preview
                block = format_post_block(item_short)
            else:
                # тупо обрезаем строку
                block = _truncate_to_fit(block, MESSAGE_LIMIT)

        try:
            await client.send_message(target_chat_id, block)
            sent += 1
            if DEBUG:
                print(f"[send_results] Sent {idx}/{total}")
        except Exception as e:
            failed += 1
            failed_items.append((item.get("channel"), item.get("msg_id"), str(e)))
            print(f"[send_results] Ошибка при отправке: {e}")
        # пауза между сообщениями
        await asyncio.sleep(pause_sec)

    # финальный отчет
    final_lines = [
        f"JobWatcher — итог отправки ({now})",
        f"Всего найдено: {total}",
        f"Отправлено: {sent}",
        f"Не отправлено: {failed}"
    ]
    if failed:
        final_lines.append("\nСписок ошибок (канал, msg_id, ошибка):")
        for ch, mid, err in failed_items:
            final_lines.append(f" - {ch} {mid} — {err}")
    final_text = "\n".join(final_lines)
    try:
        await client.send_message(target_chat_id, final_text)
    except Exception as e:
        print(f"[send_results] Ошибка при отправке финального отчёта: {e}")

    print(f"[send_results] Отправлено {sent} из {total}, упало {failed}.")

# ================= 7.0 MAIN =================
async def main():
    await client.start(phone=PHONE)

    hours = input("За какой период сканировать? (в часах, например 24 / 72 / 168): ")
    try:
        hours = int(hours)
    except:
        print("Некорректное число. Использую 24.")
        hours = 24

    print(f"Сканирую каналы за {hours} часов…")
    await fetch_messages(hours)
    print("Готово.")

    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
