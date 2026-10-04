# Все настройки проекта в одном месте: чтобы сменить модель, достаточно поменять одну строку.

# Распознавание речи (faster-whisper)
WHISPER_MODEL = "small"         # tiny / base / small / medium / large-v3: точнее, но медленнее и тяжелее
WHISPER_DEVICE = "cpu"          # на GPU-сервере здесь будет "cuda"
WHISPER_COMPUTE_TYPE = "int8"   # квантизация: меньше памяти и быстрее на CPU
LANGUAGE = "ru"                 # задаём явно: автоопределение языка иногда ошибается

# Языковая модель (Ollama)
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:4b"      # выбрана по сравнению с qwen2.5:3b: меньше выдумок, та же скорость
OLLAMA_NUM_CTX = 8192           # без этого Ollama молча обрежет длинную расшифровку
OLLAMA_TEMPERATURE = 0.2        # низкая температура: меньше «фантазий»
OLLAMA_TIMEOUT = 600            # секунд на ответ модели

# Ограничения на загружаемый файл
ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".oga"}  # .ogg/.oga — голосовые из Telegram
MAX_FILE_SIZE_MB = 50
MAX_DURATION_MIN = 15           # длиннее — расшифровка может не влезть в контекст LLM (num_ctx)
