import json
import re

from ai_checker.assistant import load_guidelines, _assistant_mode
from ai_checker.llm import generate_text, get_model_name


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if not match:
            raise
    return json.loads(match.group(0))


def _ai_enabled() -> bool:
    mode = _assistant_mode().lower()
    return mode not in {"off", "0", "false", "rules", "fast"}


def generate_syllabus_draft(syllabus) -> tuple[dict, str]:
    if not _ai_enabled():
        raise RuntimeError(
            "AI is disabled on this host. Set LLM_ASSISTANT_MODE=llm "
            "and install llama-cpp-python to enable drafts."
        )
    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .order_by("week_number")
    )
    topics_payload = []
    for st in topics:
        topic = st.topic
        description = (
            topic.description_ru
            or topic.description_en
            or topic.description_kz
            or ""
        )
        topics_payload.append(
            {
                "topic_id": topic.id,
                "week": st.week_label or st.week_number,
                "title": st.get_title(),
                "description": description,
            }
        )

    guidelines = load_guidelines()
    course = syllabus.course
    course_title = course.display_title
    course_description = course.description_ru or course.description_en or course.description_kz or ""
    prompt = (
        "You are a syllabus drafting assistant. Return STRICT JSON only.\n"
        "Use Russian language for all content values.\n"
        "Follow the guidelines and mirror the tone of a university syllabus.\n\n"
        "GUIDELINES:\n"
        f"{guidelines}\n\n"
        "COURSE INFO:\n"
        f"code: {course.code}\n"
        f"title: {course_title}\n"
        f"description_hint: {course_description}\n"
        f"semester: {syllabus.semester}\n"
        f"academic_year: {syllabus.academic_year}\n"
        f"total_weeks: {syllabus.total_weeks}\n"
        f"language: {syllabus.main_language}\n\n"
        "TOPICS (id, week, title, description):\n"
        f"{json.dumps(topics_payload, ensure_ascii=False)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "course_description": "string",\n'
        '  "course_goal": "string",\n'
        '  "learning_outcomes": ["string", "..."],\n'
        '  "teaching_methods": ["string", "..."],\n'
        '  "teaching_philosophy": "string",\n'
        '  "course_policy": "string",\n'
        '  "academic_integrity_policy": "string",\n'
        '  "inclusive_policy": "string",\n'
        '  "assessment_policy": "string",\n'
        '  "grading_scale": "string",\n'
        '  "main_literature": ["string", "..."],\n'
        '  "additional_literature": ["string", "..."],\n'
        '  "appendix": "string",\n'
        '  "weekly_plan": [\n'
        "    {\n"
        '      "topic_id": 1,\n'
        '      "week_label": "1-2",\n'
        '      "tasks": "string",\n'
        '      "outcomes": ["RO1", "RO2"],\n'
        '      "literature": "string",\n'
        '      "assessment": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )

    result = generate_text(
        prompt,
        max_tokens=1400,
        temperature=0.2,
        top_p=0.9,
    )
    data = _parse_json(result)
    return data, get_model_name()
