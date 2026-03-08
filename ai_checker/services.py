import json
import logging
import os
import re
import time
import html

try:
    # Better extraction quality for DOCX/PDF when available.
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None

try:
    # Fallback extractor for PDF.
    import pypdf
except ImportError:
    pypdf = None

from syllabi.models import Syllabus

from .llm import generate_text, get_model_name
from .models import AiCheckResult

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(min_value, value)


def _env_float(name: str, default: float, min_value: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(min_value, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int_alias(names: tuple[str, ...], default: int, min_value: int = 1) -> int:
    for name in names:
        if os.getenv(name) is not None:
            return _env_int(name, default, min_value=min_value)
    return max(min_value, default)


def _env_float_alias(names: tuple[str, ...], default: float, min_value: float = 0.0) -> float:
    for name in names:
        if os.getenv(name) is not None:
            return _env_float(name, default, min_value=min_value)
    return max(min_value, default)


# AI payload tuning: include head/middle/tail instead of only file beginning.
MAX_INPUT_CHARS = _env_int_alias(("AI_CHECK_MAX_INPUT_CHARS", "LLM_CHECK_TEXT_LIMIT"), 5000, min_value=1200)
HEAD_CHARS = _env_int("AI_CHECK_HEAD_CHARS", 2200, min_value=600)
MIDDLE_CHARS = _env_int("AI_CHECK_MIDDLE_CHARS", 900, min_value=300)
TAIL_CHARS = _env_int("AI_CHECK_TAIL_CHARS", 2200, min_value=600)
LLM_MAX_TOKENS = _env_int_alias(("AI_CHECK_LLM_MAX_TOKENS", "LLM_CHECK_MAX_TOKENS"), 220, min_value=80)
LLM_TEMPERATURE = _env_float_alias(("AI_CHECK_LLM_TEMPERATURE",), 0.1, min_value=0.0)
FAST_RULES_ENABLED = _env_bool("AI_CHECK_FAST_RULES", True)
PDF_FAST_EXTRACTION = _env_bool("AI_CHECK_PDF_FAST_EXTRACTION", True)

_GOAL_MARKERS = (
    "цель курса",
    "цели курса",
    "course goal",
    "learning outcomes",
    "ожидаемые результаты",
)
_TOPIC_MARKERS = (
    "тематический план",
    "распределение тем",
    "план курса",
    "course schedule",
    "topics",
)
_LITERATURE_MARKERS = (
    "литература",
    "основная литература",
    "дополнительная литература",
    "библиограф",
    "references",
    "reading list",
)
_HARD_FAILURE_MARKERS = (
    "файл пуст",
    "empty file",
    "нечитаем",
    "не удалось извлечь",
    "cannot extract",
    "critical error",
)
_WEEK_RE = re.compile(r"(?:недел[яьи]|week|тема)\s*[:#№-]?\s*\d{1,2}", re.IGNORECASE)


_SYLLABUS_TITLE_MARKERS = (
    "\u0441\u0438\u043b\u043b\u0430\u0431\u0443\u0441",
    "\u0443\u0447\u0435\u0431\u043d\u0430\u044f \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430",
    "syllabus",
    "sillabus",
    "course syllabus",
)
_COURSE_CONTEXT_MARKERS = (
    "\u043a\u0443\u0440\u0441",
    "\u0434\u0438\u0441\u0446\u0438\u043f\u043b\u0438\u043d",
    "\u043a\u0440\u0435\u0434\u0438\u0442",
    "\u0441\u0435\u043c\u0435\u0441\u0442\u0440",
    "\u043f\u0440\u0435\u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442",
    "course",
    "semester",
    "credits",
    "prerequisite",
    "assessment",
)
_NON_SYLLABUS_MARKERS = (
    "\u0440\u0435\u0437\u044e\u043c\u0435",
    "curriculum vitae",
    "resume",
    "invoice",
    "\u0441\u0447\u0435\u0442-\u0444\u0430\u043a\u0442\u0443\u0440",
    "\u0430\u043a\u0442 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043d\u044b\u0445 \u0440\u0430\u0431\u043e\u0442",
    "\u0434\u043e\u0433\u043e\u0432\u043e\u0440 \u0430\u0440\u0435\u043d\u0434\u044b",
    "\u043f\u0430\u0441\u043f\u043e\u0440\u0442",
    "\u0443\u0434\u043e\u0441\u0442\u043e\u0432\u0435\u0440\u0435\u043d\u0438",
    "\u0431\u0430\u043d\u043a\u043e\u0432\u0441\u043a\u0430\u044f \u0432\u044b\u043f\u0438\u0441\u043a\u0430",
    "\u043d\u0430\u043a\u043b\u0430\u0434\u043d\u0430\u044f",
    "\u0447\u0435\u043a",
    "bank statement",
    "purchase order",
    "quotation",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _normalize_text_for_ai(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _build_representative_excerpt(full_text: str) -> str:
    text = _normalize_text_for_ai(full_text)
    if len(text) <= MAX_INPUT_CHARS:
        return text

    separator = "\n\n-----\n\n"
    middle_start = max(0, (len(text) // 2) - (MIDDLE_CHARS // 2))
    middle_end = min(len(text), middle_start + MIDDLE_CHARS)

    ranges = _merge_ranges(
        [
            (0, min(len(text), HEAD_CHARS)),
            (middle_start, middle_end),
            (max(0, len(text) - TAIL_CHARS), len(text)),
        ]
    )

    parts = [text[start:end] for start, end in ranges]
    excerpt = separator.join(part for part in parts if part)
    if len(excerpt) <= MAX_INPUT_CHARS:
        return excerpt

    # If merged excerpt is still too long, preserve beginning and end.
    head_budget = max(1000, min(HEAD_CHARS, MAX_INPUT_CHARS // 2))
    tail_budget = max(1000, MAX_INPUT_CHARS - head_budget - len(separator))
    return f"{text[:head_budget]}{separator}{text[-tail_budget:]}"


def _missing_extractor_feedback(file_path: str) -> str | None:
    lower_path = (file_path or "").lower()
    if lower_path.endswith(".pdf") and MarkItDown is None and pypdf is None:
        return (
            "<h3>Ошибка AI-проверки</h3>"
            "<p>Не установлены зависимости для чтения PDF.</p>"
            "<p>Установите дополнительные пакеты командой <code>pip install -r requirements-ai.txt</code> "
            "и повторите проверку.</p>"
        )

    if lower_path.endswith((".doc", ".docx")) and MarkItDown is None:
        return (
            "<h3>Ошибка AI-проверки</h3>"
            "<p>Не установлены зависимости для чтения Word-файлов.</p>"
            "<p>Установите дополнительные пакеты командой <code>pip install -r requirements-ai.txt</code> "
            "и повторите проверку.</p>"
        )

    return None


def _humanize_runtime_error(exc: Exception) -> str:
    message = str(exc or "").strip()
    plain = message.lower()

    if "requirements-ai.txt" in plain or ("httpx" in plain and "remote llm" in plain):
        body = (
            "Не установлены дополнительные AI-зависимости для удалённой LLM. "
            "Установите <code>requirements-ai.txt</code>."
        )
    elif "remote llm is not configured" in plain or "llm_api_key" in plain:
        body = (
            "Удалённая LLM не настроена. Укажите <code>LLM_API_KEY</code> "
            "или переключитесь на локальную модель."
        )
    elif "llama-cpp-python" in plain or "llm model not found" in plain:
        body = (
            "Локальная LLM не настроена. Установите <code>llama-cpp-python</code> и задайте "
            "<code>LLM_MODEL_PATH</code>, либо настройте удалённую API-модель."
        )
    else:
        body = html.escape(message) or "Не удалось выполнить AI-проверку."

    return f"<h3>Ошибка AI-проверки</h3><p>{body}</p>"


def extract_text_from_file(file_path: str) -> str:
    """Extract text from file with a fast path for PDF."""
    if not os.path.exists(file_path):
        return ""

    lower_path = file_path.lower()
    is_pdf = lower_path.endswith(".pdf")
    pypdf_tried = False

    if is_pdf and pypdf and PDF_FAST_EXTRACTION:
        try:
            pypdf_tried = True
            reader = pypdf.PdfReader(file_path)
            parts: list[str] = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    parts.append(txt)
            text = "\n".join(parts)
            if len(text) > 50:
                logger.info("pypdf extracted text successfully (fast path)")
                return text
        except Exception as exc:
            logger.warning("pypdf extract error (fast path): %s", exc)

    if MarkItDown:
        try:
            md = MarkItDown()
            result = md.convert(file_path)
            if result.text_content and len(result.text_content) > 50:
                logger.info("MarkItDown extracted text successfully")
                return result.text_content
        except Exception as exc:
            logger.warning("MarkItDown extract error: %s", exc)

    # If PDF fast mode is disabled, still try pypdf as fallback before giving up.
    if is_pdf and pypdf and not pypdf_tried:
        try:
            reader = pypdf.PdfReader(file_path)
            parts: list[str] = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    parts.append(txt)
            text = "\n".join(parts)
            if len(text) > 50:
                logger.info("pypdf extracted text successfully (fallback)")
                return text
        except Exception as exc:
            logger.warning("pypdf extract error (fallback): %s", exc)

    return ""


def build_syllabus_text_from_db(syllabus: Syllabus) -> str:
    parts = [f"Course: {syllabus.course.code}"]
    if syllabus.course_description:
        parts.append(f"Description: {syllabus.course_description}")

    topics = syllabus.syllabus_topics.filter(is_included=True).order_by("week_number")
    if topics.exists():
        parts.append("\nTopics:")
        for st in topics:
            parts.append(f"Week {st.week_number}: {st.get_title()}")
            if st.learning_outcomes:
                parts.append(f"  - Outcome: {st.learning_outcomes}")

    return "\n".join(parts)


def _build_optimized_prompt(syllabus_text: str) -> str:
    """
    Fast prompt with softer blocking logic.
    Critical fail only for unreadable document or fully missing core sections.
    """
    return (
        "<|im_start|>system\n"
        "Ты эксперт Учебно-методического управления (УМУ). Проверь структуру силлабуса мягко и справедливо.\n"
        "Правила:\n"
        "1. Оцени наличие ключевых блоков: цель/результаты, темы по неделям, литература.\n"
        "2. Ставь approved=false только при критических проблемах: документ нечитаем или ключевой раздел полностью отсутствует.\n"
        "3. Старые источники, неполная детализация или частичные несоответствия — это рекомендации, а не блокирующая ошибка.\n"
        "4. Если структура в целом корректна, ставь approved=true и дай краткие рекомендации в feedback.\n"
        "Ответь СТРОГО JSON: {\"approved\": boolean, \"feedback\": \"HTML text\"}.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Текст силлабуса (фрагменты):\n{syllabus_text}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _parse_json_response(text: str) -> dict:
    """Extract JSON from model output even when extra formatting exists."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
    except Exception:
        pass

    return {
        "approved": False,
        "feedback": f"<h3>Результат анализа</h3><p>{cleaned[:500]}...</p>",
    }


def _looks_like_complete_syllabus(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").lower())
    if len(normalized) < 250:
        return False

    has_goal = _contains_any(normalized, _GOAL_MARKERS)
    has_literature = _contains_any(normalized, _LITERATURE_MARKERS)
    has_topics = _contains_any(normalized, _TOPIC_MARKERS) or len(_WEEK_RE.findall(normalized)) >= 8
    return has_goal and has_literature and has_topics


def _is_hard_failure_feedback(feedback: str) -> bool:
    plain = re.sub(r"<[^>]+>", " ", feedback or "").lower()
    plain = re.sub(r"\s+", " ", plain)
    return _contains_any(plain, _HARD_FAILURE_MARKERS)


def _detect_non_syllabus_document(source_text: str) -> tuple[bool, list[str]]:
    normalized = re.sub(r"\s+", " ", (source_text or "").lower()).strip()
    if not normalized:
        return False, []

    week_hits = len(_WEEK_RE.findall(normalized))
    has_goal = _contains_any(normalized, _GOAL_MARKERS)
    has_topics = _contains_any(normalized, _TOPIC_MARKERS) or week_hits >= 8
    has_literature = _contains_any(normalized, _LITERATURE_MARKERS)
    has_title = _contains_any(normalized, _SYLLABUS_TITLE_MARKERS)
    course_signal = sum(1 for marker in _COURSE_CONTEXT_MARKERS if marker in normalized)

    positive_score = (
        int(has_title) * 3
        + int(has_goal) * 2
        + int(has_topics) * 2
        + int(has_literature) * 2
        + min(course_signal, 3)
    )
    if week_hits >= 8:
        positive_score += 2
    elif week_hits >= 3:
        positive_score += 1

    non_hits = [marker for marker in _NON_SYLLABUS_MARKERS if marker in normalized]
    negative_score = len(non_hits) * 3

    # Confident syllabus profile: do not block.
    if positive_score >= 6 and positive_score >= negative_score:
        return False, []

    if non_hits and (negative_score >= 6 or (positive_score <= 2 and week_hits == 0)):
        return True, non_hits[:3]

    # Long files without any syllabus signal are likely irrelevant uploads.
    if not non_hits and positive_score <= 1 and len(normalized) >= 1200:
        return True, ["no-core-syllabus-signals"]

    return False, []


def _build_not_syllabus_feedback(cues: list[str]) -> str:
    intro = (
        "<h3>Проверка остановлена</h3>"
        "<p>Загруженный файл не похож на учебный силлабус.</p>"
        "<p>Пожалуйста, загрузите документ, где есть цель курса, темы по неделям и литература.</p>"
    )
    if not cues:
        return intro

    labels: list[str] = []
    for cue in cues:
        if cue == "no-core-syllabus-signals":
            labels.append("не найдены ключевые разделы силлабуса")
        else:
            labels.append(html.escape(cue))
    items = "".join(f"<li>{label}</li>" for label in labels[:5])
    return f"{intro}<p>Обнаруженные признаки другого документа:</p><ul>{items}</ul>"


def _quick_structure_decision(source_text: str) -> dict | None:
    """
    Fast deterministic path:
    - Approve when all key blocks are confidently detected.
    - Reject when almost all key blocks are missing.
    - Otherwise defer to LLM.
    """
    if not FAST_RULES_ENABLED:
        return None

    normalized = re.sub(r"\s+", " ", (source_text or "").lower())
    if len(normalized) < 250:
        return {
            "approved": False,
            "feedback": (
                "<h3>Ошибка</h3>"
                "<p>Недостаточно текста для автоматической проверки структуры силлабуса.</p>"
            ),
            "raw_response": "fast-rules:insufficient-text",
            "model_name": "rules-fast-v1",
        }

    week_hits = len(_WEEK_RE.findall(normalized))
    has_goal = _contains_any(normalized, _GOAL_MARKERS)
    has_topics = _contains_any(normalized, _TOPIC_MARKERS) or week_hits >= 8
    has_literature = _contains_any(normalized, _LITERATURE_MARKERS)
    score = int(has_goal) + int(has_topics) + int(has_literature)

    if score == 3:
        return {
            "approved": True,
            "feedback": (
                "<h3>Проверка завершена</h3>"
                "<p>Ключевые разделы найдены: цель/результаты, тематический план, литература.</p>"
                "<p>Силлабус автоматически передан на следующий этап.</p>"
            ),
            "raw_response": "fast-rules:approved",
            "model_name": "rules-fast-v1",
        }

    if score <= 1:
        missing: list[str] = []
        if not has_goal:
            missing.append("цель курса/learning outcomes")
        if not has_topics:
            missing.append("темы по неделям")
        if not has_literature:
            missing.append("список литературы")
        missing_html = "".join(f"<li>{item}</li>" for item in missing)
        return {
            "approved": False,
            "feedback": (
                "<h3>Требуется доработка</h3>"
                "<p>В документе не обнаружены ключевые разделы структуры.</p>"
                f"<ul>{missing_html}</ul>"
            ),
            "raw_response": "fast-rules:missing-core-sections",
            "model_name": "rules-fast-v1",
        }

    return None


def _apply_lenient_guardrail(result_data: dict, source_text: str) -> dict:
    approved = bool(result_data.get("approved"))
    feedback = str(result_data.get("feedback", "") or "")

    if approved:
        return result_data
    if not _looks_like_complete_syllabus(source_text):
        return result_data
    if _is_hard_failure_feedback(feedback):
        return result_data

    note = (
        "<p><b>Примечание:</b> замечания ИИ сохранены как рекомендации. "
        "Структура документа распознана как достаточная для передачи на следующий этап.</p>"
    )
    if "замечания ИИ сохранены как рекомендации" in feedback:
        merged_feedback = feedback
    else:
        merged_feedback = f"{feedback}\n{note}" if feedback else note

    patched = dict(result_data)
    patched["approved"] = True
    patched["feedback"] = merged_feedback
    return patched


def run_ai_check(syllabus: Syllabus) -> AiCheckResult:
    logger.info("AI check started for syllabus id=%s", syllabus.id)
    started_at = time.perf_counter()

    content_source = "db"
    extracted_text = ""

    if syllabus.pdf_file:
        extracted_text = extract_text_from_file(syllabus.pdf_file.path)
        if extracted_text:
            content_source = "file"

    if content_source == "file":
        full_text = extracted_text
    else:
        full_text = build_syllabus_text_from_db(syllabus)

    ai_text = _build_representative_excerpt(full_text)
    logger.info("AI check input length=%s chars (source=%s)", len(ai_text), content_source)

    if len(ai_text) < 50:
        dependency_feedback = None
        if syllabus.pdf_file:
            dependency_feedback = _missing_extractor_feedback(syllabus.pdf_file.path)
        return _save_check_result(
            syllabus,
            False,
            dependency_feedback or "<h3>Ошибка</h3><p>Файл пустой или не удалось извлечь текст.</p>",
            "empty",
            "none",
        )

    is_not_syllabus, cues = _detect_non_syllabus_document(full_text)
    if is_not_syllabus:
        logger.info(
            "AI non-syllabus guard triggered for syllabus id=%s in %.2fs",
            syllabus.id,
            time.perf_counter() - started_at,
        )
        return _save_check_result(
            syllabus,
            False,
            _build_not_syllabus_feedback(cues),
            "fast-rules:not-syllabus",
            "rules-fast-v1",
        )

    fast_result = _quick_structure_decision(full_text)
    if fast_result is not None:
        logger.info(
            "AI fast-rules path used for syllabus id=%s (approved=%s) in %.2fs",
            syllabus.id,
            fast_result["approved"],
            time.perf_counter() - started_at,
        )
        return _save_check_result(
            syllabus,
            bool(fast_result["approved"]),
            str(fast_result["feedback"]),
            str(fast_result["raw_response"]),
            str(fast_result["model_name"]),
        )

    prompt = _build_optimized_prompt(ai_text)

    model_name = "unknown"
    raw_response = ""
    result_data: dict = {}

    try:
        raw_response = generate_text(
            prompt,
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
        )
        model_name = get_model_name()
        result_data = _parse_json_response(raw_response)
        result_data = _apply_lenient_guardrail(result_data, full_text)
    except Exception as exc:
        logger.error("LLM error during syllabus check: %s", exc)
        result_data = {"approved": False, "feedback": _humanize_runtime_error(exc)}
        raw_response = str(exc)

    logger.info(
        "AI LLM path finished for syllabus id=%s in %.2fs",
        syllabus.id,
        time.perf_counter() - started_at,
    )

    return _save_check_result(
        syllabus,
        bool(result_data.get("approved", False)),
        str(result_data.get("feedback", "Нет ответа")),
        raw_response,
        model_name,
    )


def _save_check_result(syllabus, approved, feedback, raw_response, model_name):
    syllabus.ai_feedback = feedback
    syllabus.save(update_fields=["ai_feedback"])

    plain_feedback = re.sub(r"<[^>]+>", " ", str(feedback))
    plain_feedback = re.sub(r"\s+", " ", plain_feedback).strip()
    if len(plain_feedback) > 200:
        clean_summary = plain_feedback[:200] + "..."
    else:
        clean_summary = plain_feedback or "AI-проверка завершена."

    return AiCheckResult.objects.create(
        syllabus=syllabus,
        model_name=model_name,
        summary=clean_summary,
        raw_result={"approved": approved, "feedback": feedback, "full_response": raw_response},
    )
