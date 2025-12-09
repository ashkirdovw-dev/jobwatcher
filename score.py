# score.py
import re
from typing import Dict, List
import pymorphy2

morph = pymorphy2.MorphAnalyzer()

def normalize_ru(s: str) -> str:
    """Нормализация (лемматизация) русских слов; для латиницы просто lower()."""
    if not s:
        return s
    # простая эвристика: если есть кириллица — лемматизируем по словам
    if re.search(r'[а-яА-ЯёЁ]', s):
        parts = re.findall(r'\w+', s, flags=re.UNICODE)
        return " ".join(morph.parse(p)[0].normal_form.lower() for p in parts)
    return s.lower()

def find_sentences(text: str) -> List[str]:
    parts = re.split(r'[\n\.\!?;]+', text)
    return [p.strip() for p in parts if p.strip()]

def score_and_classify(text: str, cfg: Dict):
    text_orig = text or ""
    text_norm = normalize_ru(text_orig)
    # Immediate ignore markers (lemmatize markers when comparing)
    ignore = cfg.get("markers", {}).get("ignore_markers", []) or []
    for w in ignore:
        if normalize_ru(w) in text_norm:
            return {
                'final_score': None,
                'positive_sum': 0,
                'negative_sum': 0,
                'matches': {'ignore': [w]},
                'summary': f"Точно нет (ignore: {w})"
            }

    sentences = find_sentences(text_orig)
    # collect markers
    excellent = cfg.get("markers", {}).get("excellent_markers", []) or []
    acceptable = cfg.get("markers", {}).get("acceptable_markers", []) or []
    negative = cfg.get("markers", {}).get("negative_markers", []) or []
    strong_neg = cfg.get("markers", {}).get("strong_negative_markers", []) or []

    # Pre-normalize marker forms to avoid duplicates; prefer longer markers first
    def norm_list(lst):
        seen = {}
        # sort by length desc to match longer phrases first
        for w in sorted(lst, key=lambda x: -len(x)):
            nw = normalize_ru(w)
            if nw and nw not in seen:
                seen[nw] = w  # map normalized -> original
        return seen  # dict normalized -> original

    exc_map = norm_list(excellent)
    acc_map = norm_list(acceptable)
    neg_map = norm_list(negative)
    sneg_map = norm_list(strong_neg)

    positive_sum = 0
    negative_sum = 0
    matches = {'excellent': [], 'acceptable': [], 'negative': [], 'strong_negative': []}

    # For each sentence, check markers (longer normalized keys first)
    for sent in sentences:
        sent_norm = normalize_ru(sent)
        # strong negative first (priority)
        for k, orig in sneg_map.items():
            if k and k in sent_norm:
                negative_sum -= 2
                matches['strong_negative'].append((orig, sent[:120]))
                # remove occurrence to avoid double-count with shorter tokens
                sent_norm = sent_norm.replace(k, ' ')
        # negative
        for k, orig in neg_map.items():
            if k and k in sent_norm:
                negative_sum -= 1
                matches['negative'].append((orig, sent[:120]))
                sent_norm = sent_norm.replace(k, ' ')
        # excellent
        for k, orig in exc_map.items():
            if k and k in sent_norm:
                positive_sum += 2
                matches['excellent'].append((orig, sent[:120]))
                sent_norm = sent_norm.replace(k, ' ')
        # acceptable
        for k, orig in acc_map.items():
            if k and k in sent_norm:
                positive_sum += 1
                matches['acceptable'].append((orig, sent[:120]))
                sent_norm = sent_norm.replace(k, ' ')

    final_score = positive_sum + negative_sum

    # summary thresholds (можно вынести в cfg)
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
        'final_score': int(final_score),
        'positive_sum': int(positive_sum),
        'negative_sum': int(abs(negative_sum)),
        'matches': matches,
        'summary': summary
    }
