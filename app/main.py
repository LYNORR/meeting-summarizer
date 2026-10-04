# Веб-сервер: отдаёт страницу и обрабатывает загруженную запись совещания.
import logging
import os
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app import config, report, summarizer, transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)
# Скрываем служебные запросы huggingface_hub (проверка версии модели Whisper), чтобы лог был читаемым.
logging.getLogger("httpx").setLevel(logging.WARNING)

INDEX_HTML = Path(__file__).resolve().parent.parent / "static" / "index.html"


@asynccontextmanager
async def lifespan(app):
    # Whisper загружаем один раз при старте сервера, а не на каждый запрос.
    logger.info("Загружаю модель Whisper (%s)...", config.WHISPER_MODEL)
    transcriber.load_model()
    logger.info("Модель Whisper загружена. Откройте http://127.0.0.1:8000")
    yield


app = FastAPI(title="Meeting Summarizer", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)


@app.get("/api/health")
def health():
    ok, message = summarizer.check_ollama()
    return JSONResponse(status_code=200 if ok else 503, content={"ok": ok, "message": message})


# Обычный def, а НЕ async def: обработка тяжёлая и синхронная. С async def она заблокировала бы
# весь сервер, а обычную def FastAPI сам запускает в отдельном потоке.
@app.post("/api/process")
def process(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Неподдерживаемый формат. Загрузите файл .mp3, .m4a, .wav или .ogg")

    # Проверяем Ollama заранее, чтобы пользователь не ждал распознавание впустую.
    ok, message = summarizer.check_ollama()
    if not ok:
        raise HTTPException(503, message)

    # Whisper читает аудио с диска, поэтому сохраняем загрузку во временный файл.
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        size = os.path.getsize(tmp_path)
        if size == 0:
            raise HTTPException(400, "Файл пустой.")
        if size > config.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(400, f"Файл больше {config.MAX_FILE_SIZE_MB} МБ.")

        start = time.perf_counter()
        try:
            transcript, duration = transcriber.transcribe(tmp_path)
        except transcriber.AudioError as error:
            raise HTTPException(400, str(error))
        transcribe_sec = time.perf_counter() - start
        logger.info("Распознавание: %.1f с (длительность записи %.1f с)", transcribe_sec, duration)

        if not transcript:
            # Тишина или музыка: LLM не вызываем, иначе она начнёт выдумывать протокол.
            raise HTTPException(400, "Речь не распознана. Проверьте, что в записи есть голос.")

        start = time.perf_counter()
        try:
            result = summarizer.summarize(transcript)
        except summarizer.OllamaUnavailableError as error:
            raise HTTPException(503, str(error))
        except summarizer.SummarizerError as error:
            raise HTTPException(500, str(error))
        summarize_sec = time.perf_counter() - start
        logger.info("Конспект: %.1f с", summarize_sec)
    finally:
        # Сервер ничего не хранит: временный файл удаляем всегда, даже если случилась ошибка.
        os.remove(tmp_path)

    return {
        **result,
        "transcript": transcript,
        "report_text": report.build_report(result, transcript, duration),
        "stats": {
            "duration_sec": round(duration, 1),
            "transcribe_sec": round(transcribe_sec, 1),
            "summarize_sec": round(summarize_sec, 1),
        },
    }
