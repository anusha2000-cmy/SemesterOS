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

    json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)

    if json_match:
        return json_match.group(0)

    return raw_text


def compact_courses_for_planning(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes unnecessary fields before sending to the planning model.
    This reduces token usage.
    """

    compact_courses = []

    for course in courses:
        compact_courses.append({
            "course_name": course.get("course_name", ""),
            "grading_breakdown": course.get("grading_breakdown", {}),
            "major_assessments": course.get("major_assessments", []),
            "project_info": course.get("project_info", {}),
            "weekly_topics": course.get("weekly_topics", []),
            "missing_info": course.get("missing_info", [])
        })

    return compact_courses


def generate_semester_plan(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    AI call 2:
    Converts compact course JSON into an unscheduled weekly roadmap.
    """

    compact_courses = compact_courses_for_planning(courses)
    courses_json = json.dumps(compact_courses, indent=2)

    prompt = f"""
Create a realistic 15-week semester roadmap from this course data.

Rules:
- Return only valid JSON.
- Do not invent due dates, exams, assignments, labs, or projects.
- Do not create duplicate tasks for the same assessment.
- Use practical tasks, not generic advice.
- Include lecture review tasks as: "Review lecture notes for <topic>".


Assignments/projects:
- Due week: include "Submit/Complete <assessment>".
- Large assignment/lab: include "Start working on <assessment>" 1 week before due when possible.
- In Week 1, do not use "Work on Project" unless a project milestone is due.
- Early project tasks should be light: review requirements, brainstorm ideas, choose topic.
- Projects should continue across the semester after requirements/topic are established.
- Increase project work near checkpoints, demos, reports, and presentations.

Exam rules:
- Midterm prep starts 1-2 weeks before the exam.
- Final prep starts 2-3 weeks before the exam.
- Exam week must use:
  - "Complete final review for <course> <exam>"
  - "Take/Complete <exam>"
- Do not write "Begin exam preparation" in the exam week.
- Do not schedule prep for an exam after that exam week.
- Do not schedule exam prep unless that exam exists in the course data.

Workload:
- Critical: multiple exams or major deadlines.
- High: one major assessment plus project work.
- Medium: assignments/labs or moderate project work.
- Low: mostly lecture review/light work.

Return JSON array:
[
  {{
    "week": 1,
    "weekly_focus": "",
    "workload_level": "Low | Medium | High | Critical",
    "reason": "",
    "course_tasks": [
      {{
        "course_name": "",
        "priority": "Low | Medium | High",
        "tasks": []
      }}
    ]
  }}
]

Course data:
{courses_json}
"""

    response = model.generate_content(prompt)
    raw_text = response.text
    cleaned_json = clean_json_response(raw_text)

    try:
        return json.loads(cleaned_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Failed to parse Gemini planning response as JSON.\n\nRaw response:\n{raw_text}"
        ) from error