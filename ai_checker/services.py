import json
import logging
import os
import re
import time
import html
import zipfile
from datetime import date
from xml.etree import ElementTree

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
_EXTRACTION_FAILURE_FEEDBACK: dict[str, str] = {}
DEFAULT_STUDY_WEEKS = 12


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


def _env_bool_alias(names: tuple[str, ...], default: bool) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default


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
AI_CHECK_USE_LLM = _env_bool_alias(("AI_CHECK_USE_LLM", "USE_LLM_CHECK", "AI_USE_LLM"), False)
AI_CHECK_FALLBACK_TO_RULES_ON_ERROR = _env_bool_alias(("AI_CHECK_FALLBACK_TO_RULES_ON_LLM_ERROR",), True)

_DESCRIPTION_MARKERS = (
    "краткое описание курса",
    "описание курса",
    "course description",
    "course overview",
)
_GOAL_MARKERS = (
    "цель курса",
    "цели курса",
    "course goal",
    "course goals",
    "goal of the course",
)
_OUTCOME_MARKERS = (
    "ожидаемые результаты",
    "результаты обучения",
    "learning outcomes",
    "learning outcome",
    "course learning outcomes",
)
_METHODS_MARKERS = (
    "методы обучения",
    "teaching methods",
    "methods of teaching",
    "instructional methods",
)
_TOPIC_MARKERS = (
    "тематический план по неделям",
    "тематический план",
    "распределение тем",
    "план курса",
    "course schedule",
    "weekly schedule",
    "topics",
)
_LITERATURE_MARKERS = (
    "список литературы",
    "обязательная литература",
    "дополнительная литература",
    "литература",
    "bibliography",
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
_WEEK_RE = re.compile(r"(?:недел[яьи]|week|апта|тема)\s*[:#№-]?\s*\d{1,2}", re.IGNORECASE)


_SYLLABUS_TITLE_MARKERS = (
    "силлабус",
    "учебная программа",
    "syllabus",
    "sillabus",
    "course syllabus",
)
_COURSE_CONTEXT_MARKERS = (
    "курс",
    "дисциплин",
    "кредиты",
    "ects",
    "семестр",
    "пререквизит",
    "формат обучения",
    "уровень обучения",
    "образовательная программа",
    "преподаватель",
    "контакты преподавателя",
    "course",
    "semester",
    "credits",
    "prerequisite",
    "assessment",
)
_NON_SYLLABUS_MARKERS = (
    "резюме",
    "curriculum vitae",
    "resume",
    "invoice",
    "счет-фактура",
    "акт выполненных работ",
    "договор аренды",
    "паспорт",
    "удостоверение",
    "банковская выписка",
    "накладная",
    "чек",
    "bank statement",
    "purchase order",
    "quotation",
    "meeting",
    "meeting recording",
    "meeting transcript",
    "minutes of meeting",
    "transcript",
    "agenda",
    "attendees",
    "zoom meeting",
    "microsoft teams",
    "google meet",
    "протокол",
    "стенограмма",
    "повестка",
    "заседание",
    "участники",
    "собрание",
    "встреча",
    "запись встречи",
)
_POLICY_MARKERS = (
    "политика курса",
    "политики курса",
    "course policy",
    "course policies",
    "academic policy",
    "attendance policy",
    "assessment policy",
)
_PHILOSOPHY_MARKERS = (
    "философия преподавания и обучения",
    "философия преподавания",
    "teaching philosophy",
    "philosophy of teaching and learning",
)
_ACADEMIC_INTEGRITY_MARKERS = (
    "политика академической честности",
    "academic integrity",
    "использование ии",
    "use of ai",
    "artificial intelligence",
    "ai policy",
)
_INCLUSIVE_MARKERS = (
    "инклюзивное академическое сообщество",
    "инклюзивная среда",
    "inclusive academic community",
    "inclusive learning environment",
)
_SECTION_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "...",
    "n/a",
    "na",
    "none",
    "todo",
    "tbd",
    "нет",
    "пусто",
    "заполнить",
}
_SECTION_HEADING_MARKERS = (
    _DESCRIPTION_MARKERS
    + _GOAL_MARKERS
    + _OUTCOME_MARKERS
    + _METHODS_MARKERS
    + _POLICY_MARKERS
    + _PHILOSOPHY_MARKERS
    + _TOPIC_MARKERS
    + _LITERATURE_MARKERS
    + _ACADEMIC_INTEGRITY_MARKERS
    + _INCLUSIVE_MARKERS
)
_WEEK_VALUE_RE = re.compile(r"\d{1,2}(?:\s*[-\u2013\u2014]\s*\d{1,2})?")
_WEEK_LABEL_RE = re.compile(
    r"\b(?:week|\u043d\u0435\u0434\u0435\u043b\u044f|\u0430\u043f\u0442\u0430)\s*[:#\u2116-]?\s*(\d{1,2}(?:\s*[-\u2013\u2014]\s*\d{1,2})?)\b",
    re.IGNORECASE,
)
_TABLE_WEEK_ROW_RE = re.compile(r"^\|?\s*(\d{1,2}(?:\s*[-\u2013\u2014]\s*\d{1,2})?)\s*\|")
_PLAIN_WEEK_ROW_RE = re.compile(r"^\s*(\d{1,2}(?:\s*[-\u2013\u2014]\s*\d{1,2})?)(?:\s+(.+))?$")
_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
_HOURS_WITH_UNIT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(?:hours?|hour|\u0447\u0430\u0441(?:\u0430|\u043e\u0432)?)\b", re.IGNORECASE)
_PLAIN_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_TIMESTAMP_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_NUMBERED_SECTION_RE = re.compile(r"^\s*\d+[\.\)]\s+")
_SPEAKER_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:speaker|\u0441\u043f\u0438\u043a\u0435\u0440|\u0434\u043e\u043a\u043b\u0430\u0434\u0447\u0438\u043a|\u0432\u044b\u0441\u0442\u0443\u043f\u0430\u044e\u0449\u0438\u0439|\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a)\s*[\w-]*\s*:",
    re.IGNORECASE,
)
_INLINE_LITERATURE_HEADER_EXCLUSIONS = (
    "структура оценок",
    "результат обучения",
    "результат",
    "задания",
    "тема / модуль",
    "assignment",
    "assessment",
)
_LITERATURE_SUBSECTION_LABELS = {
    "обязательная литература",
    "дополнительная литература",
    "main literature",
    "additional literature",
}

_MIN_LITERATURE_YEAR = date.today().year - 3


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _extractor_dependency_status() -> tuple[dict[str, bool], list[str]]:
    available = {
        "markitdown": MarkItDown is not None,
        "pypdf": pypdf is not None,
    }
    missing = [name for name, ok in available.items() if not ok]
    return available, missing


def _cache_extraction_feedback(file_path: str, feedback: str | None) -> None:
    if not file_path:
        return
    if feedback:
        _EXTRACTION_FAILURE_FEEDBACK[file_path] = feedback
    else:
        _EXTRACTION_FAILURE_FEEDBACK.pop(file_path, None)


def _cached_extraction_feedback(file_path: str) -> str | None:
    return _EXTRACTION_FAILURE_FEEDBACK.get(file_path or "")


def _feedback_for_markitdown_exception(file_path: str, exc: Exception) -> str | None:
    lower_path = (file_path or "").lower()
    message = str(exc or "")
    plain = message.lower()

    if lower_path.endswith((".doc", ".docx")) and (
        "dependencies needed to read .docx files have not been installed" in plain
        or "optional dependency [docx]" in plain
        or "docxconverter threw missingdependencyexception" in plain
    ):
        return (
            "<h3>Ошибка AI-проверки</h3>"
            "<p>Не установлены зависимости для чтения Word-файлов.</p>"
            "<p>Установите пакеты командой <code>pip install -r requirements-ai.txt</code>, "
            "затем перезапустите <code>run_worker</code> и повторите проверку.</p>"
        )

    return None


def _extract_text_from_docx(file_path: str) -> str:
    try:
        with zipfile.ZipFile(file_path) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception as exc:
        logger.warning("DOCX zip extract error: %s", exc)
        return ""

    try:
        root = ElementTree.fromstring(document_xml)
    except Exception as exc:
        logger.warning("DOCX xml parse error: %s", exc)
        return ""

    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespaces):
        chunks: list[str] = []
        for node in paragraph.findall(".//w:t", namespaces):
            if node.text:
                chunks.append(node.text)
        if chunks:
            text = "".join(chunks).strip()
            if text:
                paragraphs.append(text)

    return "\n".join(paragraphs)


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


def _clean_markdown_line(line: str) -> str:
    cleaned = (line or "").strip().strip("|")
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"^[>\-\*\+\u2022]+\s*", "", cleaned)
    cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _looks_like_heading(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    cleaned = _clean_markdown_line(stripped).lower()
    return len(cleaned) <= 120 and any(marker in cleaned for marker in _SECTION_HEADING_MARKERS)


def _is_placeholder_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return normalized in _SECTION_PLACEHOLDERS


def _extract_section_lines(source_text: str, markers: tuple[str, ...], limit: int = 40) -> list[str]:
    lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    collected: list[str] = []

    for index, raw_line in enumerate(lines):
        cleaned = _clean_markdown_line(raw_line)
        lowered = cleaned.lower()
        if not cleaned or not any(marker in lowered for marker in markers):
            continue

        for marker in markers:
            marker_index = lowered.find(marker)
            if marker_index == -1:
                continue
            tail = cleaned[marker_index + len(marker) :].lstrip(" :-|")
            if tail and not _is_placeholder_text(tail):
                collected.append(tail)
            break

        for follow_line in lines[index + 1 :]:
            if len(collected) >= limit:
                break
            if _looks_like_heading(follow_line):
                break
            next_cleaned = _clean_markdown_line(follow_line)
            if not next_cleaned:
                if collected:
                    continue
                continue
            collected.append(next_cleaned)
        break

    return [line for line in collected if line]


def _extract_section_text(source_text: str, markers: tuple[str, ...], limit: int = 40) -> str:
    return " ".join(_extract_section_lines(source_text, markers, limit=limit)).strip()


def _extract_numbered_section_lines(
    source_text: str,
    markers: tuple[str, ...],
    limit: int = 80,
    require_numbered_start: bool = False,
) -> list[str]:
    lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    collected: list[str] = []

    for index, raw_line in enumerate(lines):
        if require_numbered_start and not _NUMBERED_SECTION_RE.match(raw_line):
            continue
        cleaned = _clean_markdown_line(raw_line)
        lowered = cleaned.lower()
        if not cleaned or not any(marker in lowered for marker in markers):
            continue

        for marker in markers:
            marker_index = lowered.find(marker)
            if marker_index == -1:
                continue
            tail = cleaned[marker_index + len(marker) :].lstrip(" :-|")
            if tail and not _is_placeholder_text(tail):
                collected.append(tail)
            break

        for follow_line in lines[index + 1 :]:
            if len(collected) >= limit:
                break
            if _NUMBERED_SECTION_RE.match(follow_line) and _looks_like_heading(follow_line):
                break
            next_cleaned = _clean_markdown_line(follow_line)
            if not next_cleaned:
                if collected:
                    continue
                continue
            collected.append(next_cleaned)
        break

    return [line for line in collected if line]


def _extract_literature_lines(source_text: str, limit: int = 60) -> list[str]:
    lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start_index = None
    start_is_numbered = False
    initial_tail = ""

    for index, raw_line in enumerate(lines):
        cleaned = _clean_markdown_line(raw_line)
        lowered = cleaned.lower()
        if not cleaned or not any(marker in lowered for marker in _LITERATURE_MARKERS):
            continue
        if any(marker in lowered for marker in _INLINE_LITERATURE_HEADER_EXCLUSIONS):
            continue
        start_index = index
        start_is_numbered = bool(_NUMBERED_SECTION_RE.match(raw_line))
        for marker in _LITERATURE_MARKERS:
            marker_index = lowered.find(marker)
            if marker_index == -1:
                continue
            initial_tail = cleaned[marker_index + len(marker) :].lstrip(" :-|")
            break
        if start_is_numbered:
            break
        if start_index is not None:
            break

    if start_index is None:
        return []

    collected: list[str] = []
    current_item = ""
    if initial_tail and not _is_placeholder_text(initial_tail):
        current_item = initial_tail

    for follow_line in lines[start_index + 1 :]:
        if len(collected) >= limit:
            break
        if start_is_numbered and _NUMBERED_SECTION_RE.match(follow_line) and _looks_like_heading(follow_line):
            break
        if not start_is_numbered and _looks_like_heading(follow_line):
            break

        next_cleaned = _clean_markdown_line(follow_line)
        if not next_cleaned:
            continue

        lowered = next_cleaned.lower()
        if lowered in _LITERATURE_SUBSECTION_LABELS:
            if current_item:
                collected.append(current_item)
                current_item = ""
            continue
        if any(marker in lowered for marker in _INLINE_LITERATURE_HEADER_EXCLUSIONS):
            continue

        is_numbered_item = bool(_NUMBERED_SECTION_RE.match(follow_line)) and not _looks_like_heading(follow_line)
        if is_numbered_item:
            if current_item:
                collected.append(current_item)
            current_item = next_cleaned
            continue

        if current_item:
            current_item = f"{current_item} {next_cleaned}".strip()
        else:
            current_item = next_cleaned

    if current_item:
        collected.append(current_item)

    return collected[:limit]


def _normalize_topic(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u0400-\u04ff]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _parse_hours_values(chunks: list[str]) -> list[float]:
    values: list[float] = []
    for chunk in chunks:
        if not chunk:
            continue
        for match in _HOURS_WITH_UNIT_RE.findall(chunk):
            try:
                values.append(float(match.replace(",", ".")))
            except ValueError:
                continue

    if values:
        return values

    for chunk in chunks:
        candidate = _clean_markdown_line(chunk)
        if not candidate or not _PLAIN_NUMBER_RE.fullmatch(candidate):
            continue
        try:
            values.append(float(candidate.replace(",", ".")))
        except ValueError:
            continue
    return values


def _expand_week_tokens(raw_value: str, expected_weeks: int) -> list[int]:
    cleaned = (raw_value or "").replace("?", "-").replace("?", "-")
    weeks: list[int] = []
    seen: set[int] = set()

    for token in _WEEK_VALUE_RE.findall(cleaned):
        if "-" in token:
            start_text, end_text = re.split(r"\s*-\s*", token, maxsplit=1)
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            candidates = range(start, end + 1)
        else:
            try:
                candidates = [int(token)]
            except ValueError:
                continue

        for week in candidates:
            if 1 <= week <= expected_weeks and week not in seen:
                seen.add(week)
                weeks.append(week)

    return weeks


def _extract_week_entries(source_text: str, expected_weeks: int) -> list[dict]:
    entries: list[dict] = []

    for raw_line in source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue

        week_values: list[int] = []
        topic = ""
        hours_values: list[float] = []
        source_key = _clean_markdown_line(stripped)

        table_match = _TABLE_WEEK_ROW_RE.match(stripped)
        if table_match:
            week_values = _expand_week_tokens(table_match.group(1), expected_weeks)
            raw_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            cells = [_clean_markdown_line(cell) for cell in raw_cells if cell.strip()]
            if len(cells) >= 2:
                topic = cells[1]
            hours_values = _parse_hours_values(cells[2:])
        else:
            label_match = _WEEK_LABEL_RE.search(stripped)
            if label_match:
                week_values = _expand_week_tokens(label_match.group(1), expected_weeks)
                tail = stripped[label_match.end() :].lstrip(" :-|")
                topic = _clean_markdown_line(tail)
                hours_values = _parse_hours_values([stripped])
            else:
                plain_match = _PLAIN_WEEK_ROW_RE.match(stripped)
                if not plain_match:
                    continue
                week_values = _expand_week_tokens(plain_match.group(1), expected_weeks)
                topic = _clean_markdown_line(plain_match.group(2) or "")
                if topic.startswith("%"):
                    continue
                hours_values = _parse_hours_values([stripped])

        if not week_values:
            continue

        for week_number in week_values:
            entries.append(
                {
                    "week": week_number,
                    "topic": topic,
                    "hours": hours_values,
                    "raw": _clean_markdown_line(stripped),
                    "source_key": source_key,
                }
            )

    return entries


def _build_formal_markdown_result(source_text: str, expected_weeks: int = DEFAULT_STUDY_WEEKS) -> dict:
    blocking_issues: list[str] = []
    advisory_notes: list[str] = []

    description_text = _extract_section_text(source_text, _DESCRIPTION_MARKERS, limit=20)
    goals_text = _extract_section_text(source_text, _GOAL_MARKERS, limit=20)
    outcomes_text = _extract_section_text(source_text, _OUTCOME_MARKERS, limit=25)
    methods_text = _extract_section_text(source_text, _METHODS_MARKERS, limit=20)
    policies_text = _extract_section_text(source_text, _POLICY_MARKERS, limit=25)
    philosophy_text = _extract_section_text(source_text, _PHILOSOPHY_MARKERS, limit=20)
    academic_integrity_text = _extract_section_text(source_text, _ACADEMIC_INTEGRITY_MARKERS, limit=25)
    inclusive_text = _extract_section_text(source_text, _INCLUSIVE_MARKERS, limit=20)
    topics_lines = _extract_numbered_section_lines(
        source_text,
        _TOPIC_MARKERS,
        limit=260,
        require_numbered_start=True,
    )
    if not topics_lines:
        topics_lines = _extract_section_lines(source_text, _TOPIC_MARKERS, limit=120)
    topics_text = " ".join(topics_lines).strip()
    literature_lines = _extract_literature_lines(source_text, limit=60)
    week_entries = _extract_week_entries("\n".join(topics_lines), expected_weeks)

    if not description_text or _is_placeholder_text(description_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u041a\u0440\u0430\u0442\u043a\u043e\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0443\u0440\u0441\u0430'.")
    if not goals_text or _is_placeholder_text(goals_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u0426\u0435\u043b\u044c \u043a\u0443\u0440\u0441\u0430'.")
    if not outcomes_text or _is_placeholder_text(outcomes_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u041e\u0436\u0438\u0434\u0430\u0435\u043c\u044b\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b' / learning outcomes.")
    if not methods_text or _is_placeholder_text(methods_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u041c\u0435\u0442\u043e\u0434\u044b \u043e\u0431\u0443\u0447\u0435\u043d\u0438\u044f'.")
    if not philosophy_text or _is_placeholder_text(philosophy_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u0424\u0438\u043b\u043e\u0441\u043e\u0444\u0438\u044f \u043f\u0440\u0435\u043f\u043e\u0434\u0430\u0432\u0430\u043d\u0438\u044f \u0438 \u043e\u0431\u0443\u0447\u0435\u043d\u0438\u044f'.")
    if not policies_text or _is_placeholder_text(policies_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u043a\u0443\u0440\u0441\u0430'.")
    if not academic_integrity_text or _is_placeholder_text(academic_integrity_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u0430\u043a\u0430\u0434\u0435\u043c\u0438\u0447\u0435\u0441\u043a\u043e\u0439 \u0447\u0435\u0441\u0442\u043d\u043e\u0441\u0442\u0438 \u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435 \u0418\u0418'.")
    if not inclusive_text or _is_placeholder_text(inclusive_text):
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0431\u043b\u043e\u043a \u043f\u0440\u043e \u0438\u043d\u043a\u043b\u044e\u0437\u0438\u0432\u043d\u043e\u0435 \u0430\u043a\u0430\u0434\u0435\u043c\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u043e.")
    if (not topics_text or _is_placeholder_text(topics_text)) and not week_entries:
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u0422\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043b\u0430\u043d \u043f\u043e \u043d\u0435\u0434\u0435\u043b\u044f\u043c'.")
    if not literature_lines:
        blocking_issues.append("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u043d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b '\u0421\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b'.")

    if literature_lines:
        outdated_sources: list[str] = []
        yearless_sources: list[str] = []
        for line in literature_lines:
            years = [int(year) for year in _YEAR_RE.findall(line)]
            if not years:
                yearless_sources.append(line)
                continue
            latest_year = max(years)
            if latest_year < _MIN_LITERATURE_YEAR:
                outdated_sources.append(f"{line} (\u0433\u043e\u0434: {latest_year})")

        for item in outdated_sources[:5]:
            advisory_notes.append(f"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b \u0441\u0442\u0430\u0440\u0448\u0435 3 \u043b\u0435\u0442 \u0438 \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f: {item}.")
        for item in yearless_sources[:3]:
            advisory_notes.append(f"\u0423 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0430 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d \u0433\u043e\u0434, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043d\u0435\u043b\u044c\u0437\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c: {item}.")

    unique_weeks = sorted({entry["week"] for entry in week_entries})
    if week_entries:
        missing_weeks = [str(week) for week in range(1, expected_weeks + 1) if week not in unique_weeks]
        if missing_weeks:
            blocking_issues.append(
                "\u0412 \u0442\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u043c \u043f\u043b\u0430\u043d\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044e\u0442 \u043d\u0435\u0434\u0435\u043b\u0438: " + ", ".join(missing_weeks) + "."
            )
    elif topics_text and not _is_placeholder_text(topics_text):
        blocking_issues.append(
            "\u0422\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043b\u0430\u043d \u043d\u0430\u0439\u0434\u0435\u043d, \u043d\u043e \u043d\u0435\u0434\u0435\u043b\u0438 \u043d\u0435 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u044b. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u044f\u0432\u043d\u044b\u0435 \u043d\u043e\u043c\u0435\u0440\u0430 \u043d\u0435\u0434\u0435\u043b\u044c \u0438\u043b\u0438 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u044b \u0432\u0440\u043e\u0434\u0435 1-2, 3-4, 10-12."
        )

    duplicate_topics: list[str] = []
    seen_topics: dict[str, tuple[str, int]] = {}
    zero_or_negative_hours: list[str] = []

    for entry in week_entries:
        topic_key = _normalize_topic(entry["topic"])
        if topic_key:
            previous = seen_topics.get(topic_key)
            if previous and previous[0] != entry["source_key"]:
                duplicate_topics.append(
                    f'\u0442\u0435\u043c\u0430 "{entry["topic"]}" \u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442\u0441\u044f \u0432 \u043d\u0435\u0434\u0435\u043b\u044f\u0445 {previous[1]} \u0438 {entry["week"]}'
                )
            else:
                seen_topics[topic_key] = (entry["source_key"], entry["week"])

        if entry["hours"] and any(value <= 0 for value in entry["hours"]):
            zero_or_negative_hours.append(
                f'\u043d\u0435\u0434\u0435\u043b\u044f {entry["week"]}: \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f \u0447\u0430\u0441\u043e\u0432 {", ".join(str(value).rstrip("0").rstrip(".") for value in entry["hours"])}'
            )

    for item in duplicate_topics[:5]:
        advisory_notes.append("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e \u0434\u0443\u0431\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0435\u043c: " + item + ".")
    for item in zero_or_negative_hours[:5]:
        blocking_issues.append("\u041d\u0430\u0439\u0434\u0435\u043d\u044b \u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0435 \u0447\u0430\u0441\u044b \u043f\u043e \u0442\u0435\u043c\u0430\u043c: " + item + ".")

    if blocking_issues:
        all_notes = blocking_issues + advisory_notes
        summary = f"\u0424\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 AlmaU: \u043d\u0430\u0439\u0434\u0435\u043d\u043e {len(blocking_issues)} \u043a\u0440\u0438\u0442\u0438\u0447\u043d\u044b\u0445 \u0437\u0430\u043c\u0435\u0447\u0430\u043d\u0438\u0439."
        items_html = "".join(f"<li>{html.escape(issue)}</li>" for issue in all_notes)
        feedback = f"<h3>Summary</h3><p>{html.escape(summary)}</p><ul>{items_html}</ul>"
        return {
            "approved": False,
            "feedback": feedback,
            "raw_response": "formal-markdown-check:issues",
            "model_name": "markitdown-rules-v2",
        }

    if advisory_notes:
        summary = f"\u0424\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 AlmaU: \u043a\u0440\u0438\u0442\u0438\u0447\u043d\u044b\u0445 \u0437\u0430\u043c\u0435\u0447\u0430\u043d\u0438\u0439 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e, \u043d\u043e \u0435\u0441\u0442\u044c {len(advisory_notes)} \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438."
        items_html = "".join(f"<li>{html.escape(issue)}</li>" for issue in advisory_notes)
        feedback = f"<h3>Summary</h3><p>{html.escape(summary)}</p><ul>{items_html}</ul>"
        return {
            "approved": True,
            "feedback": feedback,
            "raw_response": "formal-markdown-check:approved-with-recommendations",
            "model_name": "markitdown-rules-v2",
        }

    summary = "\u0421\u0438\u043b\u043b\u0430\u0431\u0443\u0441 \u0441\u043e\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u0430\u043c AlmaU"
    feedback = f"<h3>Summary</h3><p>{summary}</p>"
    return {
        "approved": True,
        "feedback": feedback,
        "raw_response": "formal-markdown-check:approved",
        "model_name": "markitdown-rules-v2",
    }


def _missing_extractor_feedback(file_path: str) -> str | None:
    lower_path = (file_path or "").lower()
    cached_feedback = _cached_extraction_feedback(file_path)
    if cached_feedback:
        return cached_feedback

    if lower_path.endswith(".pdf"):
        _deps, missing = _extractor_dependency_status()
        if missing:
            missing_text = ", ".join(missing)
            return (
                "<h3>Ошибка AI-проверки</h3>"
                "<p>Не хватает библиотек для чтения PDF.</p>"
                f"<p>Отсутствуют: <code>{html.escape(missing_text)}</code>.</p>"
                "<p>Установите их: <code>pip install -r requirements-ai.txt</code> и перезапустите "
                "<code>run_worker</code>, затем повторно отправьте файл на AI-проверку.</p>"
                "<p>Проверка установленных библиотек внутри текущего окружения:</p>"
                f"<ul><li>markitdown: {_extract_dependency_state(_deps['markitdown'])}</li>"
                f"<li>pypdf: {_extract_dependency_state(_deps['pypdf'])}</li></ul>"
            )

    if lower_path.endswith(".doc"):
        return (
            "<h3>Ошибка AI-проверки</h3>"
            "<p>Формат <code>.doc</code> поддерживается неустойчиво.</p>"
            "<p>Сохраните документ в <code>.docx</code> или PDF и повторите проверку.</p>"
        )

    return None


def _extract_dependency_state(ok: bool) -> str:
    return "✅ установлена" if ok else "❌ не установлена"


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

def _humanize_runtime_error_legacy(exc: Exception) -> str:
    message = str(exc or "").strip()
    plain = message.lower()

    if "requirements-ai.txt" in plain or ("httpx" in plain and "remote llm" in plain):
        body = (
            "AI dependencies are missing for the selected mode. "
            "Install <code>requirements-ai.txt</code>."
        )
    elif "remote llm is not configured" in plain or "llm_api_key" in plain:
        if AI_CHECK_USE_LLM:
            body = (
                "Remote LLM mode is enabled but not configured. "
                "Set <code>LLM_API_KEY</code> or disable LLM with <code>AI_CHECK_USE_LLM=false</code>."
            )
        else:
            body = (
                "LLM is not configured, but rules-only checking is available. "
                "Keep <code>AI_CHECK_USE_LLM=false</code> for formal validation without API keys."
            )
    elif "llama-cpp-python" in plain or "llm model not found" in plain:
        body = (
            "Local LLM mode is not configured. Install <code>llama-cpp-python</code> and set "
            "<code>LLM_MODEL_PATH</code>, or disable LLM with <code>AI_CHECK_USE_LLM=false</code>."
        )
    else:
        body = html.escape(message) or "AI check failed."

    return f"<h3>AI Check Error</h3><p>{body}</p>"


def extract_text_from_file(file_path: str) -> str:
    """Extract text from file with a fast path for PDF."""
    if not os.path.exists(file_path):
        return ""

    _cache_extraction_feedback(file_path, None)

    lower_path = file_path.lower()
    is_pdf = lower_path.endswith(".pdf")
    is_docx = lower_path.endswith(".docx")
    pypdf_tried = False

    if is_docx:
        text = _extract_text_from_docx(file_path)
        if text.strip():
            logger.info("DOCX stdlib extracted text successfully")
            _cache_extraction_feedback(file_path, None)
            return text
        return ""

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
                _cache_extraction_feedback(file_path, None)
                return result.text_content
        except Exception as exc:
            logger.warning("MarkItDown extract error: %s", exc)
            _cache_extraction_feedback(file_path, _feedback_for_markitdown_exception(file_path, exc))

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
                _cache_extraction_feedback(file_path, None)
                return text
        except Exception as exc:
            logger.warning("pypdf extract error (fallback): %s", exc)

    return ""


def build_syllabus_text_from_db(syllabus: Syllabus) -> str:
    parts = [
        f"Syllabus: {syllabus.course.code}",
        f"Semester: {syllabus.semester}",
        f"Academic year: {syllabus.academic_year}",
    ]

    course_title = syllabus.course.display_title if getattr(syllabus, "course", None) else ""
    if course_title:
        parts.append(f"Course title: {course_title}")

    if syllabus.course_description:
        parts.append(f"\nDescription:\n{syllabus.course_description}")
    if syllabus.course_goal:
        parts.append(f"\nCourse goal:\n{syllabus.course_goal}")
    if syllabus.learning_outcomes:
        parts.append(f"\nLearning outcomes:\n{syllabus.learning_outcomes}")

    policy_chunks = [
        syllabus.course_policy,
        syllabus.academic_integrity_policy,
        syllabus.inclusive_policy,
        syllabus.assessment_policy,
    ]
    policy_text = "\n".join(chunk.strip() for chunk in policy_chunks if chunk and chunk.strip())
    if policy_text:
        parts.append(f"\nCourse policy:\n{policy_text}")

    topics = syllabus.syllabus_topics.filter(is_included=True).order_by("week_number")
    if topics.exists():
        parts.append("\nTopics:")
        for st in topics:
            topic_line = f"Week {st.week_number}: {st.get_title()}"
            hours_value = st.custom_hours or getattr(st.topic, "default_hours", None)
            if hours_value:
                topic_line += f" | Hours: {hours_value}"
            parts.append(topic_line)
            if st.learning_outcomes:
                parts.append(f"Outcome: {st.learning_outcomes}")
            if st.tasks:
                parts.append(f"Tasks: {st.tasks}")
            if st.literature_notes:
                parts.append(f"Topic literature: {st.literature_notes}")

    literature_lines = []
    if syllabus.main_literature:
        literature_lines.extend(line.strip() for line in syllabus.main_literature.splitlines() if line.strip())
    if syllabus.additional_literature:
        literature_lines.extend(line.strip() for line in syllabus.additional_literature.splitlines() if line.strip())
    if literature_lines:
        parts.append("\nLiterature:")
        parts.extend(literature_lines)

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
    timestamp_hits = len(_TIMESTAMP_RE.findall(source_text or ""))
    speaker_hits = len(_SPEAKER_LINE_RE.findall(source_text or ""))

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
    if timestamp_hits >= 5:
        negative_score += 4
    elif timestamp_hits >= 3:
        negative_score += 2
    if speaker_hits >= 3:
        negative_score += 4
    elif speaker_hits >= 1:
        negative_score += 2

    if positive_score >= 6 and positive_score >= negative_score:
        return False, []

    if (timestamp_hits >= 5 and speaker_hits >= 2) or (
        any(
            cue in normalized
            for cue in (
                "meeting",
                "meeting recording",
                "meeting transcript",
                "стенограмма",
                "протокол",
                "запись встречи",
            )
        )
        and (timestamp_hits >= 3 or speaker_hits >= 1)
        and positive_score <= 3
    ):
        return True, ["meeting-transcript", *non_hits[:2]]

    if non_hits and (negative_score >= 6 or (positive_score <= 2 and week_hits == 0)):
        return True, non_hits[:3]

    if not non_hits and positive_score <= 1 and len(normalized) >= 600:
        return True, ["no-core-syllabus-signals"]

    return False, []


def _build_not_syllabus_feedback(cues: list[str]) -> str:
    intro = (
        "<h3>Проверка остановлена</h3>"
        "<p>Загруженный файл не похож на учебный силлабус.</p>"
        "<p>Для AI-проверки нужен именно силлабус с базовой структурой: цель курса, темы по неделям, политики курса и литература.</p>"
    )
    if not cues:
        return intro

    labels: list[str] = []
    for cue in cues:
        if cue == "no-core-syllabus-signals":
            label = "не найдены ключевые разделы силлабуса"
        elif cue == "meeting-transcript":
            label = "файл похож на протокол, стенограмму или расшифровку встречи"
        elif cue in {"meeting", "meeting recording", "meeting transcript", "minutes of meeting"}:
            label = "обнаружены признаки meeting/meeting recording документа"
        elif cue in {"transcript", "стенограмма"}:
            label = "обнаружены признаки стенограммы или расшифровки"
        elif cue in {"agenda", "повестка"}:
            label = "обнаружены признаки повестки встречи"
        elif cue in {"протокол", "заседание", "участники", "собрание", "встреча", "запись встречи"}:
            label = "обнаружены признаки протокола или служебного документа"
        else:
            label = html.escape(cue)
        if label not in labels:
            labels.append(label)
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
        if extracted_text.strip():
            content_source = "file"
        elif syllabus.pdf_file:
            dependency_feedback = _missing_extractor_feedback(syllabus.pdf_file.path)
            if dependency_feedback is None:
                dependency_feedback = (
                    "<h3>Ошибка AI-проверки</h3>"
                    "<p>Не удалось извлечь текст из загруженного файла. "
                    "Проверьте, что это PDF/DOCX, а его содержимое не является картинкой."
                )
            return _save_check_result(
                syllabus,
                False,
                dependency_feedback,
                "empty",
                "none",
            )

    if content_source == "file":
        full_text = extracted_text
    else:
        full_text = build_syllabus_text_from_db(syllabus)

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

    if content_source == "file":
        formal_result = _build_formal_markdown_result(
            full_text,
            expected_weeks=syllabus.total_weeks or DEFAULT_STUDY_WEEKS,
        )
        logger.info(
            "AI formal markdown path used for syllabus id=%s (approved=%s) in %.2fs",
            syllabus.id,
            formal_result["approved"],
            time.perf_counter() - started_at,
        )
        return _save_check_result(
            syllabus,
            bool(formal_result["approved"]),
            str(formal_result["feedback"]),
            str(formal_result["raw_response"]),
            str(formal_result["model_name"]),
        )

    ai_text = _build_representative_excerpt(full_text)
    logger.info("AI check input length=%s chars (source=%s)", len(ai_text), content_source)

    if len(ai_text) < 50:
        dependency_feedback = None
        if syllabus.pdf_file:
            dependency_feedback = _missing_extractor_feedback(syllabus.pdf_file.path)
        return _save_check_result(
            syllabus,
            False,
            dependency_feedback or "<h3>Summary</h3><p>\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0442\u0435\u043a\u0441\u0442 \u0438\u0437 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043d\u043e\u0433\u043e \u0444\u0430\u0439\u043b\u0430.</p>",
            "empty",
            "none",
        )

    if not AI_CHECK_USE_LLM:
        logger.info(
            "AI LLM disabled for syllabus id=%s by AI_CHECK_USE_LLM=false. Using formal rules only.",
            syllabus.id,
        )
        formal_result = _build_formal_markdown_result(
            full_text,
            expected_weeks=syllabus.total_weeks or DEFAULT_STUDY_WEEKS,
        )
        return _save_check_result(
            syllabus,
            bool(formal_result["approved"]),
            str(formal_result["feedback"]),
            str(formal_result["raw_response"]),
            str(formal_result["model_name"]),
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
        if AI_CHECK_FALLBACK_TO_RULES_ON_ERROR:
            logger.info("Falling back to formal rules for syllabus id=%s after LLM error.", syllabus.id)
            formal_result = _build_formal_markdown_result(
                full_text,
                expected_weeks=syllabus.total_weeks or DEFAULT_STUDY_WEEKS,
            )
            return _save_check_result(
                syllabus,
                bool(formal_result["approved"]),
                str(formal_result["feedback"]),
                str(formal_result["raw_response"]),
                str(formal_result["model_name"]),
            )
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
