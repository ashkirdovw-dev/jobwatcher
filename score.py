import re
from typing import Dict

def find_sentences(text: str):
    # Разбиваем на предложения
    parts = re.split(r'[\n\.\!?;]+', text)
    return [p.strip() for p in parts if p.strip()]

def match_count_in_sentence(word: str, sentence: str) -> int:
    # Проверяем точное совпадение слова
    pattern = r'\b' + re.escape(word.lower()) + r'\b'
    return 1 if re.search(pattern, sentence.lower()) else 0

def score_and_classify(text: str, cfg: Dict):
    text_low = (text or "").lower()

    # Проверка на игнор
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
    matches = {'excellent': [], 'acceptable': [], 'negative': [], 'strong_negative': []}
    positive_sum = 0
    negative_sum = 0

    for sent in sentences:
        s = sent.lower()
        for w in cfg.get("markers", {}).get("excellent_markers", []) or []:
            if match_count_in_sentence(w, s):
                positive_sum += 2
                matches['excellent'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("acceptable_markers", []) or []:
            if match_count_in_sentence(w, s):
                positive_sum += 1
                matches['acceptable'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("negative_markers", []) or []:
            if match_count_in_sentence(w, s):
                negative_sum -= 1
                matches['negative'].append((w, sent[:120]))
        for w in cfg.get("markers", {}).get("strong_negative_markers", []) or []:
            if match_count_in_sentence(w, s):
                negative_sum -= 2
                matches['strong_negative'].append((w, sent[:120]))

    final_score = positive_sum + negative_sum

    # Определяем summary
    if final_score is None:
        summary = "Точно нет"
    elif final_score >= 4:
        summary = "Хорошее совпадение"
    elif final_score >= 2:
        summary = "Альтернативно — рассмотреть"
    elif final_score >= 1:
        summary = "Похоже — надо вчитаться"
    else:
        summary = "Точно нет"

    return {
        'final_score': final_score,
        'positive_sum': positive_sum,
        'negative_sum': abs(negative_sum),
        'matches': matches,
        'summary': summary
    }
