import os
import json
import re
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing. Add it to your .env file.")

genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-2.5-flash")


def clean_json_response(raw_text: str) -> str:
    raw_text = raw_text.strip()

    if raw_text.startswith("```json"):
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text.replace("```", "").strip()

    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)

    if json_match:
        return json_match.group(0)

    return raw_text


def generate_recommended_study_blocks(
    semester_plan: List[Dict[str, Any]],
    semester_start_date: str,
    lecture_schedules: Dict[str, Dict[str, Any]],
    study_preferences: Dict[str, Any]
) -> Dict[str, Any]:
    """
    AI Study Block Recommender.

    Converts the semester roadmap into flexible study block recommendations.
    This does not create exact calendar times.
    """

    payload = {
        "semester_start_date": semester_start_date,
        "lecture_schedules": lecture_schedules,
        "study_preferences": study_preferences,
        "semester_plan": semester_plan
    }

    payload_json = json.dumps(payload, indent=2, default=str)

    prompt = f"""
You are SemesterOS Study Block Recommender.

Task:
Convert the semester roadmap into flexible study block recommendations.

Rules:
- Return valid JSON only. No markdown.
- Recommend day + date + duration, not exact clock times.
- Do not include start_time or end_time.
- Use only preferred_study_days and respect weekend_preference.
- Every roadmap task must appear in a block.
- Include weekly_buffer_tasks as recommended blocks.
- For weekly_buffer_tasks, use course_name: "All Courses" and task_type: "Buffer".
- Do not drop tasks, invent tasks, or return unscheduled tasks.
- Each block must stay in the same week as the roadmap task.
- Do not move tasks to earlier or later weeks.
- Split large tasks only within the same week.
- Every block must include a non-empty day from preferred_study_days.
- Every block must include date in YYYY-MM-DD format.
- Calculate date using semester_start_date, week number, and day.
- Use lecture_days for lecture reviews.
- Lecture review goes on the lecture day or next preferred study day.
- Spread project and exam prep across multiple blocks only within their roadmap week.

Balance:
- Spread blocks across preferred_study_days.
- Avoid overloading one day when other preferred days are available.
- Do not leave preferred days empty unless there are fewer blocks than days.
- Balance total minutes across days.
- Avoid more than 2-3 blocks/day unless week is Critical.

Duration:
- Lecture Review: 30-60
- Reading: 45-60
- Practice: 60-90
- Exam Prep: 90-120
- Project Work: 90-180
- Admin: 30-45
- Catch-up: 60-120
- Buffer: 45-90
Use session_length_style as preference.

Output JSON:
{{
  "recommended_study_blocks": [
    {{
      "week": "",
      "day": "",
      "date": "",
      "course_name": "",
      "task": "",
      "task_type": "Lecture Review | Exam Prep | Project Work | Reading | Practice | Admin | Catch-up | Buffer",
      "recommended_duration_minutes": 0,
      "priority": "Low | Medium | High",
      "reason": ""
    }}
  ],
  "scheduling_summary": {{
    "total_blocks": 0,
    "warnings": []
  }}
}}

Input:
{payload_json}
"""

    response = model.generate_content(prompt)
    raw_text = response.text
    cleaned_json = clean_json_response(raw_text)

    try:
        return json.loads(cleaned_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Failed to parse AI study block response as JSON.\n\nRaw response:\n{raw_text}"
        ) from error