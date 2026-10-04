# Сборка итогового протокола в простой .txt (без markdown, чтобы нормально открывался везде).
from datetime import datetime

LINE = "=" * 60


def _format_duration(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def build_report(result, transcript, duration):
    lines = [
        "ПРОТОКОЛ СОВЕЩАНИЯ",
        f"Дата обработки: {datetime.now():%d.%m.%Y}  |  Длительность записи: {_format_duration(duration)}",
        LINE,
        "",
        "ТЕМЫ",
    ]
    lines += [f"{i}. {topic}" for i, topic in enumerate(result["topics"], start=1)] or ["Не выделены"]

    lines += ["", "КРАТКОЕ СОДЕРЖАНИЕ", result["summary"]]

    lines += ["", "РЕШЕНИЯ И ИТОГИ"]
    lines += [f"- {decision}" for decision in result["decisions"]] or ["Решений не зафиксировано"]

    lines += ["", "ЗАДАЧИ"]
    lines += [
        f"- Задача: {t['task']} | Ответственный: {t['owner']} | Срок: {t['deadline']}"
        for t in result["tasks"]
    ] or ["Задач не зафиксировано"]

    lines += [
        "",
        LINE,
        "ПОЛНАЯ РАСШИФРОВКА",
        transcript,
        "",
        LINE,
        "Сформировано автоматически (Whisper + LLM). Возможны неточности — проверьте важные детали.",
    ]
    return "\n".join(lines) + "\n"
