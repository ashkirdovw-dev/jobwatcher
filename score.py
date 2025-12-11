# score.py

import re
import os
from typing import Dict, List, Tuple

from nltk.stem.snowball import SnowballStemmer
from nltk.stem import PorterStemmer

# debug: установите SCORE_DEBUG=1 в окружении, чтобы видеть лог
DEBUG = bool(os.getenv("SCORE_DEBUG"))

# Стеммеры
ru_stemmer = SnowballStemmer("russian")
en_stemmer = PorterStemmer()

# Веса маркеров (по ТЗ: отличные +2, допустимые +1, негативные -1, сильно-отрицательные -2)
WEIGHT_EXCELLENT = 2
WEIGHT_ACCEPTABLE = 1
WEIGHT_NEGATIVE = -1
WEIGHT_STRONG_NEG = -2


def _clean_token(tok: str) -> str:
    """Убираем внешние небуквенно-цифровые символы, оставляем внутренние (например c# -> c)."""
    # заменяем подчеркивания/прочее внутри на пробелы не нужно — просто убираем крайние небуквы
    return re.sub(r'^[^\w]+|[^\w]+$', '', tok, flags=re.UNICODE)


def normalize_word(word: str) -> str:
    """Стемминг + lower; удаляет крайние не-алфанум символы прежде чем стеммить."""
    if not word:
        return ""
    w = _clean_token(word).lower()
    if not w:
        return ""
    # если есть кириллица — русский стеммер
    if re.search(r"[а-яА-ЯёЁ]", w):
        try:
            return ru_stemmer.stem(w)
        except Exception:
            return w
    # иначе английский стеммер
    try:
        return en_stemmer.stem(w)
    except Exception:
        return w


_token_re = re.compile(r"[а-яА-ЯёЁa-zA-Z0-9#\+]+", flags=re.UNICODE)


def normalize_phrase(phrase: str) -> str:
    """
    Стеммируем фразу — каждое слово отдельно и возвращаем через пробел.
    Если фраза содержит несколько слов (например "api testing"), сохранится порядок.
    """
    tokens = _token_re.findall(phrase or "")
    stems = [normalize_word(t) for t in tokens if normalize_word(t)]
    return " ".join(stems)


def _build_norm_map(markers: List[str]) -> List[Tuple[str, str]]:
    """
    Возвращает список пар (norm, original) в порядке:
    более длинные нормы первыми (чтобы давать приоритет фразам).
    Убирает дубликаты нормализованных значений, оставляя первое вхождение.
    """
    if not markers:
        return []
    # norm -> orig (first seen)
    seen = {}
    # сортируем по длине (desc) чтобы фразы шли раньше коротких
    for orig in sorted(markers, key=lambda s: -len(s or "")):
        norm = normalize_phrase(orig)
        if norm and norm not in seen:
            seen[norm] = orig
    # возвращаем в виде списка (norm, orig)
    return list(seen.items())


def _regex_contains(norm_phrase: str, text_norm: str) -> bool:
    """
    Ищем norm_phrase как отдельную последовательность токенов в text_norm.
    Используем границы слов: (^| ) norm_phrase ( |$)
    """
    if not norm_phrase:
        return False
    # экранировать, но norm_phrase уже состоит из простых символов (стеммы), всё же экранируем
    pat = r"(^|\s)" + re.escape(norm_phrase) + r"($|\s)"
    return re.search(pat, text_norm) is not None


def score_and_classify(text: str, cfg: Dict) -> Dict:
    """
    Основная функция скоринга.
    """
    text = text or ""
    # нормализованный и стеммированный текст (строка)
    # Используем ту же tokenization что и для маркеров
    text_tokens = _token_re.findall(text.lower())
    text_norm_tokens = [normalize_word(t) for t in text_tokens if normalize_word(t)]
    text_norm = " ".join(text_norm_tokens)

    if DEBUG:
        print("[score] text_norm:", text_norm)

    # взять маркеры из cfg['markers']
    markers_block = {}
    if isinstance(cfg, dict):
        markers_block = cfg.get("markers", {}) or {}

    excellent_markers = markers_block.get("excellent_markers", []) or []
    acceptable_markers = markers_block.get("acceptable_markers", []) or []
    negative_markers = markers_block.get("negative_markers", []) or []
    strong_negative_markers = markers_block.get("strong_negative_markers", []) or []
    ignore_markers = markers_block.get("ignore_markers", []) or []

    # нормализованные карты: список (norm, original)
    exc_map = _build_norm_map(excellent_markers)
    acc_map = _build_norm_map(acceptable_markers)
    neg_map = _build_norm_map(negative_markers)
    sneg_map = _build_norm_map(strong_negative_markers)
    ign_map = _build_norm_map(ignore_markers)

    # Результаты
    positive_sum = 0
    negative_sum = 0
    matches = {'excellent': [], 'acceptable': [], 'negative': [], 'strong_negative': [], 'ignore': []}

    # 1) Проверка на игнор (если найден — завершить обработку и вернуть final_score = None)
    for norm, orig in ign_map:
        if _regex_contains(norm, text_norm):
            matches['ignore'].append(orig)
            if DEBUG:
                print(f"[score] IGNORE matched: {orig} (norm='{norm}'). Returning ignore.")
            return {
                'final_score': None,
                'positive_sum': int(positive_sum),
                'negative_sum': int(abs(negative_sum)),
                'matches': matches,
                'summary': f"Точно нет (ignore: {orig})"
            }

    # 2) Собираем все совпадения и суммируем
    # strong negative
    for norm, orig in sneg_map:
        if _regex_contains(norm, text_norm):
            matches['strong_negative'].append(orig)
            negative_sum += abs(WEIGHT_STRONG_NEG)  # accumulate as positive magnitude for negative_sum
            if DEBUG:
                print(f"[score] strong_negative matched: {orig} -> {WEIGHT_STRONG_NEG}")

    # acceptable (+1)
    for norm, orig in acc_map:
        if _regex_contains(norm, text_norm):
            matches['acceptable'].append(orig)
            positive_sum += WEIGHT_ACCEPTABLE
            if DEBUG:
                print(f"[score] acceptable matched: {orig} -> +{WEIGHT_ACCEPTABLE}")

    # excellent (+2)
    for norm, orig in exc_map:
        if _regex_contains(norm, text_norm):
            matches['excellent'].append(orig)
            positive_sum += WEIGHT_EXCELLENT
            if DEBUG:
                print(f"[score] excellent matched: {orig} -> +{WEIGHT_EXCELLENT}")

    # negative (-1)
    for norm, orig in neg_map:
        if _regex_contains(norm, text_norm):
            matches['negative'].append(orig)
            negative_sum += abs(WEIGHT_NEGATIVE)
            if DEBUG:
                print(f"[score] negative matched: {orig} -> {WEIGHT_NEGATIVE}")

    # final sums: positive_sum (already positive amount), negative_sum (positive magnitude)
    # Compute final_score = positive_sum - negative_sum
    final_score_val = positive_sum - negative_sum

    # If there were any strong_negative matches, by TЗ we should mark final as reject (None),
    # but KEEP the computed sums and matches for transparency.


    # No strong negative -> normal summary based on thresholds (configurable)
    # thresholds могут лежать в cfg['thresholds'] как dict {target, alternative, maybe}
    thr = (cfg.get("thresholds") if isinstance(cfg, dict) else None) or {}
    t_good = int(thr.get("target", 4))
    t_alt = int(thr.get("alternative", 2))
    t_maybe = int(thr.get("maybe", 1))

    if final_score_val >= t_good:
        summary = "Хорошее совпадение"
    elif final_score_val >= t_alt:
        summary = "Альтернативно — рассмотреть"
    elif final_score_val >= t_maybe:
        summary = "Похоже — надо вчитаться"
    else:
        summary = "Точно нет"

    if DEBUG:
        print(f"[score] final_score: {final_score_val}, pos:{positive_sum}, neg:{negative_sum}, summary:{summary}")

    return {
        'final_score': int(final_score_val),
        'positive_sum': int(positive_sum),
        'negative_sum': int(negative_sum),
        'matches': matches,
        'summary': summary
    }
