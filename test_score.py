import yaml
from pathlib import Path
from score import score_and_classify
from nltk.stem.snowball import SnowballStemmer


""" cfg_path = Path("config.yaml")
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)


test_texts = [
    "QA Automation Engineer\nУдалённо, Россия\nКомпания: PrideInBrains javascript java AQA",

]


for i, txt in enumerate(test_texts, 1):
    res = score_and_classify(txt, cfg)
    print(f"\n=== Текст {i} ===")
    print(txt)
    print("--- Результат ---")
    print("final_score:", res['final_score'])
    print("positive_sum:", res['positive_sum'], ", negative_sum:", res['negative_sum'])
    print("summary:", res['summary'])
    print("matches:", res['matches']) """


# ==== 1. Загрузка конфигурации ====
cfg_path = Path("config.yaml")
print("cfg_path exists?", cfg_path.exists())

with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

print("DEBUG cfg keys:", list(cfg.keys()))
print("DEBUG markers:", cfg.get("markers", {}))

# ==== 2. Настройка стеммера ====
stemmer = SnowballStemmer("english")

def stemmed_lower(word: str) -> str:
    return stemmer.stem(word.lower())

# ==== 3. Тестовые тексты ====
test_texts = [
    "QA Automation Engineer\nУдалённо, Россия\nКомпания: PrideInBrains javascript java AQA api middle"
]

# ==== 4. Проход по каждому тексту ====
for i, txt in enumerate(test_texts, 1):
    print(f"\n=== Текст {i} ===\n{txt}\n")
    
    # Разбиваем текст на слова для дебага
    words_in_text = [w.strip(",.()[]:;-") for w in txt.lower().split()]
    
    # Проверка каждого маркера
    for category, markers in cfg.get("markers", {}).items():
        for m in markers:
            m_stem = stemmed_lower(m)
            for w in words_in_text:
                w_stem = stemmed_lower(w)
                if w_stem == m_stem:
                    print(f"DEBUG MATCH: word '{w}' in text matches marker '{m}' ({category}) via stem")

    # ==== 5. Вызов функции скоринга ====
    res = score_and_classify(txt, cfg)
    
    # ==== 6. Вывод результата ====
    print("--- Результат ---")
    print("final_score:", res['final_score'])
    print("positive_sum:", res['positive_sum'], ", negative_sum:", res['negative_sum'])
    print("summary:", res['summary'])
    print("matches:", res['matches'])