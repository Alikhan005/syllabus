import os
import threading
from pathlib import Path

_GUIDELINES = None
_GUIDELINES_LOCK = threading.Lock()
_ENV_LOADED = False

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if load_dotenv is None:
        return
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _env_int(name: str, default: int) -> int:
    _ensure_env_loaded()
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    _ensure_env_loaded()
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def get_llm_mode() -> str:
    return _env_str("LLM_ASSISTANT_MODE", "auto").lower()


_GUIDELINES_LIMIT = _env_int("LLM_GUIDELINES_LIMIT", 2000)
_PDF_GUIDELINES_LIMIT = _env_int("LLM_GUIDELINES_PDF_LIMIT", 1600)
_PDF_GUIDELINES_PAGES = _env_int("LLM_GUIDELINES_PDF_PAGES", 2)

_DEFAULT_GUIDELINES = (
    "Рекомендации по заполнению силлабуса:\n"
    "1. Укажите цель курса и результаты обучения.\n"
    "2. Распишите темы по неделям, укажите формат и часы.\n"
    "3. Для каждой темы добавьте краткое описание и задания.\n"
    "4. Литература: основная 2-3, дополнительная 2-5 источников.\n"
    "5. Опишите оценивание: виды работ, проценты, критерии.\n"
    "6. Добавьте политики курса (посещаемость, дедлайны, академическая честность).\n"
    "7. Проверьте согласованность количества недель и часов с учебным планом.\n"
)


def _load_guidelines_from_txt(path: Path) -> str:
    for encoding in ("utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding).strip()
        except Exception:
            continue
    return ""


def _extract_guidelines_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""

    chunks = []
    total_len = 0
    for idx, page in enumerate(reader.pages):
        if idx >= _PDF_GUIDELINES_PAGES:
            break
        text = page.extract_text() or ""
        if text.strip():
            snippet = text.strip()
            chunks.append(snippet)
            total_len += len(snippet)
            if total_len >= _PDF_GUIDELINES_LIMIT:
                break

    joined = "\n".join(chunks)
    return joined[:_PDF_GUIDELINES_LIMIT]


def _trim_guidelines(text: str, limit: int = _GUIDELINES_LIMIT) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def load_guidelines() -> str:
    global _GUIDELINES
    if _GUIDELINES is not None:
        return _GUIDELINES

    with _GUIDELINES_LOCK:
        if _GUIDELINES is not None:
            return _GUIDELINES

        root = Path(__file__).resolve().parents[1]
        txt_path = Path(os.getenv("SYLLABUS_GUIDELINES_PATH", root / "docs" / "syllabus_guidelines.txt"))
        pdf_path = Path(os.getenv("SYLLABUS_GUIDELINES_PDF", root / "Sillabus it sturtup.pdf"))

        guidelines = ""
        if txt_path.exists():
            guidelines = _load_guidelines_from_txt(txt_path)

        pdf_excerpt = ""
        if pdf_path.exists():
            pdf_excerpt = _extract_guidelines_from_pdf(pdf_path)

        if not guidelines and pdf_excerpt:
            guidelines = pdf_excerpt
        elif guidelines and pdf_excerpt:
            guidelines = f"{guidelines}\n\nКраткий фрагмент из PDF:\n{pdf_excerpt}"

        if not guidelines:
            guidelines = _DEFAULT_GUIDELINES
        else:
            guidelines = _trim_guidelines(guidelines)

        _GUIDELINES = guidelines
        return _GUIDELINES
