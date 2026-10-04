# Распознавание речи: аудиофайл -> текст (faster-whisper).
from faster_whisper import WhisperModel

from app import config

# Модель храним в памяти и загружаем один раз: загрузка занимает секунды и ~1 ГБ RAM.
_model = None


class AudioError(Exception):
    """Проблема с самим файлом (повреждён, слишком длинный) — сервер вернёт 400."""


def load_model():
    global _model
    if _model is None:
        # При первом запуске модель скачивается с HuggingFace (нужен интернет), дальше берётся из кэша.
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(path):
    """Возвращает (текст расшифровки, длительность аудио в секундах)."""
    model = load_model()
    try:
        segments, info = model.transcribe(
            path,
            language=config.LANGUAGE,
            vad_filter=True,                   # вырезаем тишину: защита от «галлюцинаций» Whisper на паузах
            beam_size=5,                       # перебор 5 вариантов на каждом шаге: точнее, чем жадный выбор
            condition_on_previous_text=False,  # не тянем ошибку из прошлого куска в следующий (защита от зацикливания)
        )
    except Exception:
        # Сюда попадаем, если файл не декодируется: например, это не аудио, а переименованный документ.
        raise AudioError("Не удалось прочитать аудиофайл. Возможно, он повреждён.")

    # Длительность известна ещё до распознавания, поэтому длинную запись отсекаем сразу.
    if info.duration > config.MAX_DURATION_MIN * 60:
        raise AudioError(f"Запись длиннее {config.MAX_DURATION_MIN} минут. Загрузите запись покороче.")

    # segments — генератор: само распознавание происходит здесь, при проходе по нему.
    text = " ".join(segment.text.strip() for segment in segments)
    return text.strip(), info.duration
