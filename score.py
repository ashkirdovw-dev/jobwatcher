import re
from nltk.stem.snowball import SnowballStemmer
from nltk.stem import PorterStemmer

ru_stemmer = SnowballStemmer("russian")
en_stemmer = PorterStemmer()

import yaml
from pathlib import Path

cfg_path = Path("config.yaml")
print("cfg_path exists?", cfg_path.exists())

with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

print("DEBUG cfg keys:", list(cfg.keys()))
print("DEBUG markers:", cfg.get("markers", {}))


def normalize_word(word: str) -> str:
    """Стемминг + приведение к нижнему регистру"""
    w = word.lower()
    if re.search("[а-яА-Я]", w):
        try:
            return ru_stemmer.stem(w)
        except Exception:
            return w
    else:
        return en_stemmer.stem(w)


def normalize_text(text: str) -> str:
    """Разбивает текст на слова и стеммит каждое"""
    tokens = re.findall(r"[а-яА-Яa-zA-Z]+", text.lower())
    stems = [normalize_word(t) for t in tokens]
    return " ".join(stems)


def score_and_classify(text, cfg):
    text_norm = normalize_text(text)

    positive_sum = 0
    negative_sum = 0
    matches = {}

    def add_match(key, word, weight):
        nonlocal positive_sum, negative_sum
        if weight > 0:
            positive_sum += weight
        else:
            negative_sum += weight
        matches.setdefault(key, []).append(word)

    # 1) strong negative — абсолютный приоритет
    for w in cfg.get("markers_strong_negative", []):
        w_norm = normalize_word(w)
        if w_norm in text_norm:
            add_match("strong_negative", w, -999)
            return {
                "final_score": None,
                "summary": "Точно нет",
                "positive_sum": positive_sum,
                "negative_sum": negative_sum,
                "matches": matches
            }

    # 2) strong positive
    for w in cfg.get("markers_strong_positive", []):
        w_norm = normalize_word(w)
        if w_norm in text_norm:
            add_match("strong_positive", w, 2)

    # 3) positive
    for w in cfg.get("markers_positive", []):
        w_norm = normalize_word(w)
        if w_norm in text_norm:
            add_match("positive", w, 1)

    # 4) negative
    for w in cfg.get("markers_negative", []):
        w_norm = normalize_word(w)
        if w_norm in text_norm:
            add_match("negative", w, -1)

    final_score = positive_sum + negative_sum

    if final_score >= 3:
        summary = "Хорошее совпадение"
    elif final_score >= 1:
        summary = "Возможно подходит"
    elif final_score == 0:
        summary = "Слабое совпадение"
    else:
        summary = "Плохое совпадение"

    return {
        "final_score": final_score,
        "summary": summary,
        "positive_sum": positive_sum,
        "negative_sum": negative_sum,
        "matches": matches
    }
