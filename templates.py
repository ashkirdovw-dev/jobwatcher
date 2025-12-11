# templates.py — минимальная заглушка, пока мы не начали полноценные шаблоны

def render_post(item: dict) -> str:
    # item содержит: channel, msg_id, text, score, label, link и др.
    # Возвращаем просто text — логика будет расширяться позже.
    return item.get("text", "(no text)")


def render_summary(summary: dict) -> str:
    # summary будет словарём с итогами отправки/группировками/всем остальным.
    # Пока — минимально безопасное поведение.
    return "Summary placeholder"
