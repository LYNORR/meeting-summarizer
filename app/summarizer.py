# Конспект: текст расшифровки -> структурированный протокол (JSON) через локальную LLM в Ollama.
import json
import logging

import requests

from app import config

logger = logging.getLogger(__name__)

# v3. v1 из плана путал решения и задачи; v2 превращал отложенный вопрос в задачу.
SYSTEM_PROMPT = """Ты — секретарь совещаний. Тебе дана автоматическая расшифровка совещания на русском языке; в ней могут быть ошибки распознавания. Составь протокол строго по тексту.

Поля протокола:
- topics — 3–7 коротких тем совещания.
- summary — 3–6 предложений о ходе совещания.
- tasks — ВСЕ поручения: конкретные действия, которые кто-то должен выполнить после встречи. Для каждого: task — что сделать; owner — имя ответственного; deadline — срок.
- decisions — то, о чём участники договорились окончательно (утвердили, перенесли, отказались). Поручения конкретным людям сюда не пиши — они уже в tasks.

Правила:
1) Ничего не выдумывай: используй только то, что есть в расшифровке.
2) Если ответственный или срок не названы — пиши «не указано» и нигде, в том числе в summary, не приписывай задачу конкретному человеку. Срок может быть не датой («к пятнице», «до релиза») — это тоже срок.
3) Вопрос, который обсудили, но не решили или отложили, — это НЕ решение и НЕ задача: не пиши его ни в decisions, ни в tasks. Упомяни его в summary как нерешённый.
4) Если решений или задач нет — верни пустой список.
5) Даты, числа и имена переписывай точно как в расшифровке.
6) Очевидные ошибки распознавания исправляй по смыслу, но факты не меняй.
7) Пиши кратко, деловым языком, на русском."""

# JSON-схема ответа (structured output): Ollama заставляет модель отвечать строго в этом формате.
# Модель пишет поля по порядку: tasks стоит до decisions, чтобы поручения не «утекали» в решения.
SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "deadline": {"type": "string"},
                },
                "required": ["task", "owner", "deadline"],
            },
        },
        "decisions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topics", "summary", "tasks", "decisions"],
}

NOT_SPECIFIED = "не указано"


class OllamaUnavailableError(Exception):
    """Ollama не запущена — сервер вернёт 503."""


class SummarizerError(Exception):
    """Понятная пользователю ошибка конспекта (текст сообщения показываем как есть)."""


def check_ollama():
    """Для /api/health: (всё ли в порядке, понятный статус)."""
    try:
        response = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return False, "Ollama не запущена. Откройте приложение Ollama или выполните `ollama serve`"
    models = [m["name"] for m in response.json().get("models", [])]
    if config.OLLAMA_MODEL not in models:
        return False, f"Модель не скачана. Выполните `ollama pull {config.OLLAMA_MODEL}`"
    return True, f"Готово к работе (модель {config.OLLAMA_MODEL})"


def _ask_llm(transcript):
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Расшифровка совещания:\n\n" + transcript},
        ],
        "stream": False,   # ждём ответ целиком, а не по кусочкам
        "format": SCHEMA,
        "options": {
            # Главный подводный камень: по умолчанию контекст маленький, и Ollama МОЛЧА обрезает текст.
            "num_ctx": config.OLLAMA_NUM_CTX,
            "temperature": config.OLLAMA_TEMPERATURE,
        },
    }
    try:
        response = requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.OLLAMA_TIMEOUT)
    except requests.ConnectionError:
        raise OllamaUnavailableError("Ollama не запущена. Откройте приложение Ollama или выполните `ollama serve`")
    if response.status_code == 404:
        raise SummarizerError(f"Модель не скачана. Выполните `ollama pull {config.OLLAMA_MODEL}`")
    if not response.ok:
        # Например, «model requires more system memory» — на 8 ГБ это реальный сценарий.
        raise SummarizerError(f"Ollama вернула ошибку: {response.text[:300]}")

    data = response.json()
    # Сколько токенов модель реально прочитала: если число упирается в num_ctx — текст обрезан.
    logger.info("Токенов на входе: %s из %s", data.get("prompt_eval_count"), config.OLLAMA_NUM_CTX)
    return data["message"]["content"]


def _parse(content):
    """Разбираем JSON от модели; при неудаче возвращаем None."""
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(result, dict) or not all(key in result for key in SCHEMA["required"]):
        return None
    # Пустые и «Не указано» с разным регистром приводим к единому «не указано».
    for task in result["tasks"]:
        for key in ("owner", "deadline"):
            value = task.get(key, "").strip()
            task[key] = NOT_SPECIFIED if not value or value.lower() == NOT_SPECIFIED else value
    return result


def summarize(transcript):
    """Возвращает dict: topics, summary, tasks, decisions. Пустую расшифровку сюда не передаём."""
    # Маленькая модель иногда ломает JSON: даём ей ровно одну повторную попытку.
    for attempt in (1, 2):
        result = _parse(_ask_llm(transcript))
        if result is not None:
            return result
        logger.warning("Модель вернула некорректный JSON (попытка %s)", attempt)
    raise SummarizerError("Не удалось составить протокол: модель вернула некорректный ответ. Попробуйте ещё раз.")
