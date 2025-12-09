import os
import json
import yaml
import sqlite3
from datetime import datetime, timedelta
from telethon import TelegramClient
from pathlib import Path
from dotenv import load_dotenv
from score import score_and_classify

# ================= 1.0 LOAD ENV =================
# print("=== DEBUG START ===")
# print("Working dir:", os.getcwd())
# print("Files in dir:", os.listdir(os.getcwd()))

# if Path(".env").exists():
#     print(".env FOUND")
# else:
#     print(".env NOT FOUND!")

# load_dotenv(dotenv_path=Path(".env"), override=True)
# from dotenv import dotenv_values
# print("=== DEBUG raw .env ===")
# print(dotenv_values())
# print("=== DEBUG values END ===")

# print("DEBUG raw API_ID =", repr(os.getenv("API_ID")))
# print("DEBUG raw API_HASH =", repr(os.getenv("API_HASH")))
# print("DEBUG raw TARGET_CHAT_ID =", repr(os.getenv("TARGET_CHAT_ID")))
# print("=== DEBUG END ===")

# API_ID = int(os.getenv("API_ID"))
# API_HASH = os.getenv("API_HASH")
# TARGET_CHAT = int(os.getenv("TARGET_CHAT_ID"))
# SESSION = os.getenv("TG_SESSION", "jobwatcher.session")
# DB_PATH = os.getenv("DB_PATH", "jobs.db")

# ================= 1.0 LOAD ENV =================
API_ID = 30613985
API_HASH = "84b69a2aa33d0fa75efe171614b155a7"
PHONE = "+79608133326"
TARGET_CHAT = -1003309146574
SESSION = "job_watcher.session"
DB_PATH = "jobwatcher.db"


# ================= 2.0 LOAD CONFIG =================
config_path = Path("config.yaml")
if not config_path.exists():
    print("config.yaml not found. Create it from config.example.yaml and edit channels/markers.")
    exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

CHANNELS = cfg.get("channels", [])


# ================= 3.0 - Database initialization =================
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# создаём таблицу заново, если не существует
c.execute("""
CREATE TABLE IF NOT EXISTS seen (
    msg_unique TEXT PRIMARY KEY,
    channel TEXT,
    msg_id INTEGER,
    status TEXT,
    score INTEGER,
    pos_sum INTEGER,
    neg_sum INTEGER,
    matches TEXT,
    raw_text TEXT,
    first_seen_ts INTEGER
)
""")
conn.commit()

# проверка колонок (debug)
cols = [t[1] for t in c.execute("PRAGMA table_info(seen)")]
print("DEBUG: columns in 'seen' table:", cols)


# ================= 4.0 TELETHON =================
client = TelegramClient(SESSION, API_ID, API_HASH)


# ================= 4.0 SCAN HISTORY =================
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
            cur = conn.execute("SELECT 1 FROM seen WHERE msg_unique=?", (unique,))
            if cur.fetchone():
                continue

            res = score_and_classify(text, cfg)
            final = res.get('final_score')
            summary = res.get('summary')
            pos_sum = res.get('positive_sum', 0)
            neg_sum = res.get('negative_sum', 0)
            matches = res.get('matches', {})

            status = summary if final is not None else 'Отброшено'
            conn.execute(
                "INSERT OR REPLACE INTO seen(msg_unique, channel, msg_id, status, score, pos_sum, neg_sum, matches, raw_text, first_seen_ts) VALUES(?,?,?,?,?,?,?,?,?,strftime('%s','now'))",
                (unique, ch, msg.id, status, final if final is not None else None, pos_sum, neg_sum, json.dumps(matches, ensure_ascii=False), text)
            )
            conn.commit()

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

# ================= 5.0 FETCH MESSAGES =================
async def fetch_messages(hours: int = 24, batch_size: int = 5):
    """
    Сканирует указанные каналы за последние `hours` часов,
    применяет scoring и отправляет результаты в TARGET_CHAT.
    """
    print(f"[fetch_messages] Сканирование каналов за последние {hours} часов…")
    results = await scan_history(client, hours=hours)

    if not results:
        print("[fetch_messages] Релевантных сообщений не найдено.")
        await client.send_message(TARGET_CHAT, "Ничего релевантного за период не найдено.")
        return

    # Сортируем по финальному скору (desc)
    results.sort(key=lambda r: r['final'], reverse=True)

    # Отправка пакетами
    for i in range(0, len(results), batch_size):
        chunk = results[i:i+batch_size]
        lines = []
        for r in chunk:
            lines.append(
                f"Источник: {r['channel']} | id: {r['msg_id']}\n"
                f"Рейтинг: {r['final']} (+{r['pos']}/-{r['neg']}) | Итог: {r['summary']}\n"
                f"{r['preview']}\n---\n"
            )
        msg_text = "\n".join(lines)
        try:
            await client.send_message(TARGET_CHAT, msg_text)
        except Exception as e:
            print(f"[fetch_messages] Ошибка при отправке: {e}")
        # Пауза, чтобы не ловить FloodWaitError
        await asyncio.sleep(2)

    print(f"[fetch_messages] Отправлено {len(results)} сообщений в чат {TARGET_CHAT}.")

# ================= 6.0 MAIN =================
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
