import os
import json
import re
from typing import Any, Dict

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


def extract_assessments_from_syllabus(syllabus_text: str) -> Dict[str, Any]:
    """
    AI call 1:
    Converts raw syllabus text into compact structured course JSON.
    """

    prompt = f"""
Extract compact planning data from this syllabus.

Rules:
- First decide whether the text is a valid course syllabus.
- A valid syllabus should include course planning information such as course title, grading, assessments, schedule, assignments, exams, projects, or weekly topics.
- If the text is not a valid syllabus, return is_valid_syllabus=false, validation_reason, and empty planning fields.
Do not force extraction from irrelevant text.
- Return only valid JSON.
- Do not invent assignment due dates.
- Use empty string or empty list if missing.
- Keep output compact.

JSON structure:
{{
  "course_name": "",
  "instructor": "",
  "semester": "",
  "grading_breakdown": {{
    "assignments": "",
    "quizzes": "",
    "midterm": "",
    "final": "",
    "project": "",
    "participation": "",
    "other": ""
  }},
  "major_assessments": [
    {{
      "title": "",
      "type": "",
      "date": "",
      "weight": ""
    }}
  ],
  "project_info": {{
    "has_project": false,
    "title": "",
    "weight": "",
    "milestones": [
      {{
        "title": "",
        "date": ""
      }}
    ]
  }},
  "weekly_topics": [
    {{
      "week": "",
      "topic": ""
    }}
  ],
  "is_valid_syllabus": true,
  "validation_reason": "",
  "missing_info": []
}}

Syllabus:
{syllabus_text}
"""

    response = model.generate_content(prompt)
    raw_text = response.text
    cleaned_json = clean_json_response(raw_text)

    try:
        return json.loads(cleaned_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Failed to parse Gemini extraction response as JSON.\n\nRaw response:\n{raw_text}"
        ) from error