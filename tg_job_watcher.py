# tg_job_watcher.py - исправленная рабочая версия
# Запуск: python tg_job_watcher.py

import os
import re
import asyncio
import sqlite3
import json
import yaml
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button

load_dotenv()

# Окружение
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "job_watcher.session")
TARGET_CHAT = os.getenv("TARGET_CHAT", "me")  # 'me' = Saved Messages
DB_PATH = os.getenv("DB_PATH", "jobwatcher.db")

# Загружаем конфиг
with open("config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

CHANNELS = [c for c in cfg.get("channels", []) if c]

# Подключение к базе и создание таблицы (если нет)
conn = sqlite3.connect(DB_PATH)
conn.execute("""
CREATE TABLE IF NOT EXISTS seen (
    msg_unique TEXT PRIMARY KEY,
    channel TEXT,
    msg_id INTEGER,
    status TEXT,
    score INTEGER,
    pos_sum INTEGER,
    neg_sum INTEGER,
    matches TEXT,
    first_seen_ts INTEGER
)
""")
conn.commit()

client = TelegramClient(SESSION, API_ID, API_HASH)

# Вспомогательные функции

def find_sentences(text: str):
    parts = re.split(r'[\n\.\!?;]+', text)
    return [p.strip() for p in parts if p.strip()]


def match_count_in_sentence(word: str, sentence: str) -> int:
    pattern = r'\b' + re.escape(word.lower()) + r'\b'
    return 1 if re.search(pattern, sentence.lower()) else 0


def score_and_classify(text: str, cfg: dict):
    text_low = (text or "").lower()
    # Immediate ignore
    for w in cfg.get("markers", {}).get("ignore_markers", []) or []:
        if re.search(r'\b' + re.escape(w.lower()) + r'\b', text_low):
            return {
                'final_score': None,
                'positive_sum': 0,
                'negative_sum': 0,
                'matches': {'ignore': [w]},
                'summary': f"Точно нет (ignore: {w})"
            }

    sentences = find_sentences(text)
    required_kw = [k.lower() for k in cfg.get("context_keywords", {}).get("required", []) or []]
    desirable_kw = [k.lower() for k in cfg.get("context_keywords", {}).get("desirable", []) or []]

    def sentence_multiplier(sentence: str) -> float:
        s = sentence.lower()
        for rk in required_kw:
            if re.search(r'\b' + re.escape(rk) + r'\b', s):
                return 1.8
        for dk in desirable_kw:
            if re.search(r'\b' + re.escape(dk) + r'\b', s):
                return 0.6
        return 1.0

    matches = {'excellent': [], 'acceptable': [], 'negative': [], 'strong_negative': []}
    positive_sum = 0.0
    negative_sum = 0.0

    for sent in sentences:
        mult = sentence_multiplier(sent)
        s = sent.lower()
        for w in cfg.get("markers", {}).get("excellent_markers", []) or []:
            if match_count_in_sentence(w, s):
                val = 2 * mult
                positive_sum += val
                matches['excellent'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("acceptable_markers", []) or []:
            if match_count_in_sentence(w, s):
                val = 1 * mult
                positive_sum += val
                matches['acceptable'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("negative_markers", []) or []:
            if match_count_in_sentence(w, s):
                val = -1 * mult
                negative_sum += val
                matches['negative'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("strong_negative_markers", []) or []:
            if match_count_in_sentence(w, s):
                val = -2 * mult
                negative_sum += val
                matches['strong_negative'].append((w, sent[:120]))

    positive_sum = int(round(positive_sum))
    negative_sum = int(round(negative_sum))  # <= 0
    final_score = positive_sum + negative_sum

    thr = cfg.get("thresholds", {"target": 4, "alternative": 2, "maybe": 1})
    if final_score is None:
        summary = "Точно нет"
    elif final_score >= thr.get("target", 4):
        summary = "Хорошее совпадение" if negative_sum == 0 else "Хорошее, но есть минусы (противоречиво)"
    elif final_score >= thr.get("alternative", 2):
        summary = "Альтернативно — рассмотреть"
    elif final_score >= thr.get("maybe", 1):
        summary = "Похоже — надо вчитаться"
    else:
        summary = "Точно нет"

    return {
        'final_score': int(final_score),
        'positive_sum': int(positive_sum),
        'negative_sum': int(abs(negative_sum)),
        'matches': matches,
        'summary': summary
    }


@client.on(events.NewMessage(chats=CHANNELS))
async def newmsg_handler(event):
    msg = event.message
    channel = getattr(event.chat, "username", getattr(event.chat, "title", str(event.chat)))
    text = (msg.message or "")
    if msg.media and not text:
        text = getattr(msg, "caption", "") or ""

    unique = f"{channel}::{(text[:500]).strip()}"
    cur = conn.execute("SELECT 1 FROM seen WHERE msg_unique=?", (unique,))
    if cur.fetchone():
        return

    # используем новую функцию подсчёта
    res = score_and_classify(text, cfg)
    final = res.get('final_score')            # число или None если ignore
    summary = res.get('summary', 'Без метки')
    pos_sum = res.get('positive_sum', 0)
    neg_sum = res.get('negative_sum', 0)
    matches = res.get('matches', {})

    # если immediate ignore -> сохраняем и пропускаем
    if final is None or summary.startswith("Точно нет"):
        status = "Отброшено"
        conn.execute(
            "INSERT OR REPLACE INTO seen(msg_unique, channel, msg_id, status, score, first_seen_ts) VALUES(?,?,?,?,?,strftime('%s','now'))",
            (unique, channel, msg.id, status, None)
        )
        conn.commit()
        return

    # Иначе — сохраняем расширённую запись
    status = summary
    matches_json = json.dumps(matches, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO seen(msg_unique, channel, msg_id, status, score, pos_sum, neg_sum, matches, first_seen_ts) VALUES(?,?,?,?,?,?,?,?,strftime('%s','now'))",
        (unique, channel, msg.id, status, final, pos_sum, neg_sum, matches_json)
    )
    conn.commit()

    preview = text.strip()
    if len(preview) > 900:
        preview = preview[:900] + "…"

    buttons = [
        [Button.inline("Отклик", f"apply:{msg.id}:{channel}"), Button.inline("Пропустить", f"skip:{msg.id}:{channel}")],
        [Button.inline("Сохранить", f"save:{msg.id}:{channel}")]
    ]

    await client.send_message(
        TARGET_CHAT,
        f"Источник: {channel}\nРейтинг: {final} (плюсы: +{pos_sum}, минусы: -{neg_sum})\nИтог: {status}\n\n{preview}",
        buttons=buttons
    )


@client.on(events.CallbackQuery)
async def callback(event):
    data = event.data.decode('utf-8') if event.data else ""
    await event.answer()
    parts = data.split(":", 2)
    if len(parts) >= 3:
        cmd, msg_id, channel = parts
    else:
        return

    cur = conn.execute("SELECT msg_unique FROM seen WHERE msg_id=?", (int(msg_id),))
    row = cur.fetchone()
    if row:
        unique = row[0]
        if cmd == "apply":
            conn.execute("UPDATE seen SET status='Откликнулся' WHERE msg_unique=?", (unique,))
            conn.commit()
            await client.send_message(TARGET_CHAT, f"Отмечено как «Откликнулся» для сообщения {msg_id} в {channel}")
        elif cmd == "skip":
            conn.execute("UPDATE seen SET status='Неинтересно' WHERE msg_unique=?", (unique,))
            conn.commit()
            await client.send_message(TARGET_CHAT, f"Отмечено как «Неинтересно» для сообщения {msg_id}")
        elif cmd == "save":
            conn.execute("UPDATE seen SET status='Сохранено' WHERE msg_unique=?", (unique,))
            conn.commit()
            await client.send_message(TARGET_CHAT, f"Сохранено: сообщение {msg_id}")
    else:
        await client.send_message(TARGET_CHAT, "Не удалось найти запись в БД для этого сообщения.")


async def main():
    await client.start()
    print("Клиент запущен. Ожидание новых сообщений...")
    await client.run_until_disconnected()



if __name__ == "__main__":
    asyncio.run(main())
