import re

# ========= РУССКИЙ СТЕММЕР ПОРТЕРА =========

VOWELS = "аеёиоуыэюя"

PERFECTIVEGROUND = re.compile(r"(ивши|ывши|ившись|ывшись|ив|ыв)$")
REFLEXIVE = re.compile(r"(с[яь])$")
ADJECTIVE = re.compile(r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею)$")
PARTICIPLE = re.compile(r"(ем|нн|вш|ющ|щ)$")
PARTICIPLE2 = re.compile(r"(ивш|ывш|ующ)$")
VERB = re.compile(r"(ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|ует|уют|ит|ыт|ена|ило|ыло|ено)$")
VERB2 = re.compile(r"(ив|ыв|овать|овать|овать)$")
NOUN = re.compile(r"(а|ев|ов|ие|ье|е|иями|ями|ами|еи|ии|ией|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|о|у|ах|иях|ях|ы|ь|ию|ью|ю|ия|ья)$")
RVRE = re.compile(r"^(.*?[аеёиоуыэюя])(.*)$")
DERIVATIONAL = re.compile(r".*ость?$")

def russian_stem(word):
    """
    Приводит русское слово к основе (стемминг Портера).
    """
    word = word.lower()
    m = RVRE.match(word)
    if not m:
        return word

    pre, rv = m.groups()

    # Шаг 1
    temp = PERFECTIVEGROUND.sub("", rv, 1)
    if temp == rv:
        temp = REFLEXIVE.sub("", rv, 1)

        a = ADJECTIVE.sub("", temp, 1)
        if a != temp:
            temp = PARTICIPLE.sub("", a, 1)
            temp = PARTICIPLE2.sub("", temp, 1)
        else:
            b = VERB.sub("", temp, 1)
            b2 = VERB2.sub("", temp, 1)
            if b != temp:
                temp = b
            elif b2 != temp:
                temp = b2
            else:
                temp = NOUN.sub("", temp, 1)

    rv = temp

    # Шаг 2
    rv = re.sub(r"и$", "", rv)

    # Шаг 3
    if DERIVATIONAL.match(rv):
        rv = re.sub(r"ость?$", "", rv)

    # Шаг 4
    rv = re.sub(r"ь$", "", rv)
    rv = re.sub(r"ейше?", "", rv)
    rv = re.sub(r"нн$", "н", rv)

    return pre + rv


# ========= СКОРИНГ =========

def score_and_classify(text, cfg):
    text_l = text.lower()

    # СТЕММИРУЕМ текст для поиска русских слов
    words = re.findall(r"[а-яА-ЯёЁa-zA-Z]+", text_l)
    stems = {w: russian_stem(w) for w in words}  # слово → стем
    text_stemmed = " ".join(stems.values())

    positive_sum = 0
    negative_sum = 0
    matches = {}

    def add(key, word, weight):
        nonlocal positive_sum, negative_sum
        if weight > 0:
            positive_sum += weight
        else:
            negative_sum += weight
        matches.setdefault(key, []).append(word)

    # Удобный хелпер
    def contains(marker):
        marker_l = marker.lower()
        marker_stem = russian_stem(marker_l)
        return (
            marker_l in text_l
            or marker_stem in text_stemmed
        )

    # === Группы маркеров ===
    for w in cfg.get("excellent_markers", []):
        if contains(w):
            add("excellent", w, 3)

    for w in cfg.get("acceptable_markers", []):
        if contains(w):
            add("acceptable", w, 1)

    for w in cfg.get("negative_markers", []):
        if contains(w):
            add("negative", w, -1)

    for w in cfg.get("strong_negative_markers", []):
        if contains(w):
            add("strong_negative", w, -3)

    # === Итог ===
    if matches.get("strong_negative"):
        return {
            "final_score": None,
            "summary": "Точно нет",
            "positive_sum": positive_sum,
            "negative_sum": negative_sum,
            "matches": matches,
        }

    total = positive_sum + negative_sum

    if total >= 3:
        summary = "Хорошее совпадение"
    elif total >= 1:
        summary = "Возможно подходит"
    elif total == 0:
        summary = "Слабое совпадение"
    else:
        summary = "Плохое совпадение"

    return {
        "final_score": total,
        "summary": summary,
        "positive_sum": positive_sum,
        "negative_sum": negative_sum,
        "matches": matches,
    }
