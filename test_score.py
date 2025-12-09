# # test_score.py — проверка скоринга без Telegram

# import yaml
# from score import score_and_classify

# # 1. Загружаем config.yaml
# with open("config.yaml", "r", encoding="utf-8") as f:
#     cfg = yaml.safe_load(f)

# print("DEBUG cfg:", cfg)

# # 2. Пример текста, который хотим проверить
# test_texts = [
#     """
#     QA automation Engineer
#     Формат: удалённо (территория РФ)
#     ЗП: до 360 т.р.
#     Компания: PrideInBrains
#     """,
#     """
#     📺 База 1000+ реальных собеседований
#     На программиста, тестировщика, аналитика и другие IT профы.
#     Есть собесы от ведущих компаний: Сбер, Яндекс, ВТБ, Тинькофф, Озон, Wildberries и т.д.
#     """
# ]

# # 3. Проверяем каждый текст
# for i, txt in enumerate(test_texts, 1):
#     result = score_and_classify(txt, cfg)
#     print(f"=== Текст {i} ===")
#     print(txt)
#     print("--- Результат ---")
#     print(f"final_score: {result['final_score']}")
#     print(f"positive_sum: {result['positive_sum']}, negative_sum: {result['negative_sum']}")
#     print(f"summary: {result['summary']}")
#     print(f"matches: {result['matches']}")
#     print("\n\n")


# ------------------
# from pathlib import Path
# import yaml

# cfg_path = Path("config.yaml")
# print("cfg_path exists?", cfg_path.exists())
# with open(cfg_path, "r", encoding="utf-8") as f:
#     cfg = yaml.safe_load(f)
# print("DEBUG cfg:", cfg)


# -------------------
from score import score_and_classify
import yaml
from pathlib import Path

# Загружаем YAML
cfg_path = Path("config.yaml")
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# Тестовые тексты
test_texts = [
    "QA Automation Engineer\nУдалённо, Россия\nКомпания: PrideInBrains javascript java AQA",
    # "База 1000+ реальных собеседований для программистов, тестировщиков, аналитиков"
]

# Проверка каждого текста
for i, txt in enumerate(test_texts, 1):
    res = score_and_classify(txt, cfg)
    print(f"\n=== Текст {i} ===")
    print(txt)
    print("--- Результат ---")
    print("final_score:", res['final_score'])
    print("positive_sum:", res['positive_sum'], ", negative_sum:", res['negative_sum'])
    print("summary:", res['summary'])
    print("matches:", res['matches'])

# ------------------

# from score import match_count_in_sentence

# text = "QA Automation Engineer"
# markers = ["QA", "automation"]

# for m in markers:
#     print(f"Маркер: {m} -> найден:", match_count_in_sentence(m, text))
