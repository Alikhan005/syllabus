import os
import threading
import logging
from pathlib import Path

# Настраиваем логгер этого модуля.
logger = logging.getLogger(__name__)

try:
    import httpx
except Exception as exc:  # pragma: no cover - необязательная зависимость
    httpx = None
    _HTTPX_IMPORT_ERROR = exc
else:
    _HTTPX_IMPORT_ERROR = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - необязательная зависимость
    load_dotenv = None

try:
    from llama_cpp import Llama
except Exception as exc:  # pragma: no cover - ошибка импорта будет показана при использовании
    Llama = None
    _LLAMA_IMPORT_ERROR = exc
else:
    _LLAMA_IMPORT_ERROR = None

_LLM = None
_INIT_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if load_dotenv is None:
        return
    # Пробуем загрузить .env из корня проекта (на 2 уровня выше).
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _remote_config() -> dict | None:
    """Загружает настройки удаленной LLM через OpenAI/Mistral/LocalAI-совместимый API."""
    _ensure_env_loaded()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")

    # Если ключа нет, удаленный режим не настроен.
    if not api_key:
        return None

    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_REMOTE_MODEL", "").strip() or "gpt-4o-mini"
    timeout = float(os.getenv("LLM_REMOTE_TIMEOUT", "30"))
    org = os.getenv("OPENAI_ORG", "").strip()

    return {
        "api_key": api_key,
        "api_url": api_url,
        "model": model,
        "timeout": timeout,
        "org": org,
    }


def _use_remote() -> bool:
    """Определяет, нужно ли использовать удаленный API вместо локальной модели."""
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()

    if provider in {"local", "llama", "llama-cpp"}:
        return False

    if provider in {"remote", "api", "openai", "openrouter", "groq", "mistral"}:
        return True

    # В режиме auto используем удаленный API только при наличии remote-настроек.
    return _remote_config() is not None


def _split_prompt(prompt: str) -> tuple[str, str]:
    """Разделяет prompt на system/user части для API-запроса."""
    if "<|im_start|>system" not in prompt:
        return "", prompt
    system = ""
    users = []
    parts = prompt.split("<|im_start|>")
    for part in parts:
        if part.startswith("system\n"):
            system = part[len("system\n") :].split("<|im_end|>", 1)[0].strip()
        elif part.startswith("user\n"):
            user = part[len("user\n") :].split("<|im_end|>", 1)[0].strip()
            if user:
                users.append(user)
    if users:
        return system, "\n\n".join(users)
    return "", prompt


def _generate_remote_text(
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
    if httpx is None:
        raise RuntimeError(
            "Remote LLM mode requires httpx. Install it from requirements-ai.txt."
        )

    config = _remote_config()
    if not config:
        raise RuntimeError("Remote LLM is not configured. Set LLM_API_KEY.")

    system, user = _split_prompt(prompt)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    headers = {"Authorization": f"Bearer {config['api_key']}"}
    if config["org"]:
        headers["OpenAI-Organization"] = config["org"]

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=config["timeout"]) as client:
            response = client.post(config["api_url"], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error(f"Error calling remote LLM: {e}")
        raise RuntimeError(f"Remote LLM connection failed: {e}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Remote LLM returned no choices.")

    choice = choices[0]
    # Поддерживаем и chat-формат, и completion-style формат ответа.
    if isinstance(choice, dict):
        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
        if choice.get("text"):
            return str(choice["text"]).strip()

    raise RuntimeError("Remote LLM returned an unexpected response.")


def _resolve_model_path() -> str:
    """
    Определяет путь к локальной модели.
    Используется только при явном запуске локального провайдера.
    Поддерживаемый источник:
    1. Переменная окружения LLM_MODEL_PATH.
    """
    _ensure_env_loaded()
    env_path = os.getenv("LLM_MODEL_PATH")
    if env_path and Path(env_path).exists():
        logger.info(f"Using model from env: {env_path}")
        return env_path
    if env_path:
        logger.warning(f"LLM_MODEL_PATH is set but file does not exist: {env_path}")

    logger.warning(
        "No local model path found. Set LLM_MODEL_PATH for local mode "
        "or configure remote API (LLM_PROVIDER=remote / LLM_API_KEY)."
    )
    return ""


def get_model_name() -> str:
    if _use_remote():
        config = _remote_config()
        return config["model"] if config else "remote-not-configured"
    model_path = _resolve_model_path()
    return Path(model_path).name if model_path else "unknown"


def warmup_llm() -> str:
    """
    Прогревает LLM по возможности, чтобы уменьшить задержку первого запроса.
    Возвращает имя выбранной модели или провайдера.
    """
    if _use_remote():
        if _remote_config() is None:
            raise RuntimeError(
                "Remote LLM mode is selected but not configured. "
                "Set LLM_API_KEY or OPENAI_API_KEY."
            )
        return get_model_name()
    get_llm()
    return get_model_name()


def get_llm() -> "Llama":
    if Llama is None:
        raise RuntimeError(
            "llama-cpp-python is not installed or failed to import: "
            f"{_LLAMA_IMPORT_ERROR}. Install with: pip install llama-cpp-python"
        )

    global _LLM
    if _LLM is None:
        with _INIT_LOCK:
            if _LLM is None:
                model_path = _resolve_model_path()

                # Если путь к модели неверный, возвращаем понятную ошибку.
                if not model_path or not Path(model_path).exists():
                    raise RuntimeError(
                        f"LLM model not found at '{model_path}'. "
                        "Please set LLM_MODEL_PATH in .env to your .gguf file location."
                    )

                # Загружаем runtime-параметры из .env или берем значения по умолчанию.
                n_ctx = int(os.getenv("LLM_CTX", "4096"))

                # Автовыбор потоков оставляет 2 ядра для системы.
                default_threads = max(1, (os.cpu_count() or 4) - 2)
                n_threads = int(os.getenv("LLM_THREADS", str(default_threads)))

                n_batch = int(os.getenv("LLM_BATCH", "512"))
                n_gpu_layers = int(os.getenv("LLM_GPU_LAYERS", "0"))

                logger.info(f"Loading Llama model from {model_path} (ctx={n_ctx}, threads={n_threads})...")

                try:
                    _LLM = Llama(
                        model_path=model_path,
                        n_ctx=n_ctx,
                        n_threads=n_threads,
                        n_batch=n_batch,
                        n_gpu_layers=n_gpu_layers,
                        verbose=False,
                    )
                    logger.info("Model loaded successfully.")
                except Exception as e:
                    logger.error(f"Failed to load Llama model: {e}")
                    raise RuntimeError(f"Failed to initialize Llama model: {e}")

    return _LLM


def generate_text(
    prompt: str,
    max_tokens: int = 900,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> str:
    """
    Главная точка входа для генерации текста.
    Сначала выбирает удаленный API, затем локальную модель.
    """
    # 1. Сначала пробуем удаленный API, если он включен.
    if _use_remote():
        try:
            return _generate_remote_text(prompt, max_tokens, temperature, top_p)
        except Exception as e:
            # Если удаленный API упал, пробрасываем ошибку дальше.
            # Локальный fallback не запускается без явной настройки провайдера.
            logger.error(f"Remote generation failed: {e}")
            raise e

    # 2. Переходим к локальной модели, если удаленный режим выключен.
    llm = get_llm()
    with _RUN_LOCK:
        output = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=["<|im_end|>"],
        )
    return output["choices"][0]["text"].strip()
