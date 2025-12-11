# formatter.py
from typing import Optional
from templates import render_post, render_summary  # шаблоны

def format_post_block(item, **kwargs):
    return render_post(item, **kwargs)


def build_emoji_bar(score: Optional[int], max_slots: int = 3) -> str:
    """
    Версия близкая к исходной: отображает заполненные слоты (🟩) и пустые (⬜).
    score может быть None.
    """
    if score is None:
        s = 0
    else:
        try:
            s = int(score)
        except Exception:
            s = 0
    full = max(0, min(max_slots, s))
    empty = max_slots - full
    return "🟩" * full + "⬜" * empty

def format_post_block(item: dict, preview_limit: int = 1500) -> str:
    """
    Форматирует блок так, как было раньше (не менять).
    Ожидаемые ключи в item: channel, msg_id, final (score), pos_sum, neg_sum,
    summary, preview, raw_text.
    Возвращает строку, готовую для отправки.
    """
    channel = item.get("channel", "")
    # сохраняем оригинальную логику: убрать @ в имени канала для формирования ссылки
    channel_name = channel.replace("@", "")
    msg_id = item.get("msg_id", "")
    # ссылка на пост Telegram (восстановлена, как в оригинале)
    post_link = f"https://t.me/{channel_name}/{msg_id}"

    final = item.get("final", None)
    pos_sum = item.get("pos_sum", 0)
    neg_sum = item.get("neg_sum", 0)
    summary = item.get("summary", "")
    # preview: если задано явным ключом — используем, иначе берём из raw_text (срез)
    preview = item.get("preview", "")
    if not preview:
        raw = item.get("raw_text", "") or ""
        preview = raw[:preview_limit]

    emoji_bar = build_emoji_bar(final, max_slots=3)

    lines = []
    # сохраняем прежний header — источник и ссылка на пост
    lines.append(f"Источник: {channel} | Ссылка на пост ({post_link})\n")

    # если у вас раньше был summary — поместим его после заголовка
    if summary:
        lines.append(f"{emoji_bar} {summary}")
    else:
        lines.append(f"{emoji_bar} Пост от {channel}")

    lines.append(f"Оценка: {final if final is not None else 'N/A'} ( +{pos_sum} / -{neg_sum} )")
    lines.append("")  # разделитель

    # Preview (фиксированно вставляем без дополнительного автоматического усечения)
    # (если нужно, sender будет заниматься батчингом/усечением)
    lines.append("Preview:")
    lines.append(preview)

    # разделитель в конце блока — точно как раньше
    lines.append("\n" + "-" * 30 + "\n")
    return "\n".join(lines)
