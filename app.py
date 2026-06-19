import os
import re

import pandas as pd
import streamlit as st
from pypdf import PdfReader

from parser.assessment_extractor_agent import extract_assessments_from_syllabus
from planner.semester_planning_agent import generate_semester_plan
from planner.task_scheduler import generate_recommended_study_blocks
from utils.cache_manager import save_json
from integrations.google_calendar_link import create_google_calendar_link


DATA_FOLDER = "docs"


st.set_page_config(
    page_title="SemesterOS",
    page_icon="📚",
    layout="wide"
)


def read_text_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def read_pdf_file(file_path):
    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


def read_uploaded_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


def clean_syllabus_text(text):
    cutoff_keywords = [
        "university policies",
        "academic integrity",
        "campus policy",
        "student conduct",
        "disability accommodations",
        "title ix",
        "sjsu policy",
        "university policy"
    ]

    lowered_text = text.lower()

    cutoff_positions = [
        lowered_text.find(keyword)
        for keyword in cutoff_keywords
        if lowered_text.find(keyword) != -1
    ]

    if cutoff_positions:
        first_cutoff = min(cutoff_positions)
        text = text[:first_cutoff]

    max_characters = 30000

    if len(text) > max_characters:
        text = text[:max_characters]

    return text


def make_safe_key(text):
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)


def get_unique_course_names(semester_plan):
    course_names = []

    for week in semester_plan:
        for course_task in week.get("course_tasks", []):
            course_name = course_task.get("course_name", "")

            if course_name and course_name not in course_names:
                course_names.append(course_name)

    return course_names


def add_assignment_buffers_to_semester_plan(semester_plan):
    updated_plan = []

    for week in semester_plan:
        week_copy = week.copy()

        week_copy["weekly_buffer_tasks"] = [
            "Assignment Buffer: Reserve time for active homework, lab, or project work"
        ]

        updated_plan.append(week_copy)

    return updated_plan


def show_course_data(extracted_courses):
    st.header("Extracted Course Data")

    for course in extracted_courses:
        course_name = course.get("course_name", "Unknown Course")

        with st.expander(course_name, expanded=False):
            st.subheader("Basic Info")
            st.write(f"**Course:** {course.get('course_name', '')}")
            st.write(f"**Instructor:** {course.get('instructor', '')}")
            st.write(f"**Semester:** {course.get('semester', '')}")

            st.subheader("Grading Breakdown")
            grading_breakdown = course.get("grading_breakdown", {})

            if grading_breakdown:
                grading_df = pd.DataFrame(
                    list(grading_breakdown.items()),
                    columns=["Category", "Weight / Details"]
                )
                st.dataframe(grading_df, width="stretch")
            else:
                st.info("No grading breakdown found.")

            st.subheader("Major Assessments")
            major_assessments = course.get("major_assessments", [])

            if major_assessments:
                st.dataframe(pd.DataFrame(major_assessments), width="stretch")
            else:
                st.info("No major assessments found.")

            st.subheader("Project Info")
            project_info = course.get("project_info", {})

            if project_info:
                st.json(project_info)
            else:
                st.info("No project information found.")

            st.subheader("Weekly Topics")
            weekly_topics = course.get("weekly_topics", [])

            if weekly_topics:
                st.dataframe(pd.DataFrame(weekly_topics), width="stretch")
            else:
                st.info("No weekly topics found.")

            missing_info = course.get("missing_info", [])

            if missing_info:
                st.subheader("Missing Info")
                st.warning(", ".join(missing_info))


def show_semester_roadmap(semester_plan):
    st.header("Semester Roadmap")

    for week in semester_plan:
        week_number = week.get("week", "")
        weekly_focus = week.get("weekly_focus", "")
        workload_level = week.get("workload_level", "")
        reason = week.get("reason", "")
        course_tasks = week.get("course_tasks", [])
        weekly_buffer_tasks = week.get("weekly_buffer_tasks", [])

        with st.expander(
            f"Week {week_number} — {workload_level}",
            expanded=False
        ):
            if reason:
                st.caption(f"Why: {reason}")

            st.write(f"**Focus:** {weekly_focus}")

            if weekly_buffer_tasks:
                st.info("Weekly Buffer: Reserve time for active homework, lab, or project work")

            if course_tasks:
                st.subheader("Course Tasks")

                for course_task in course_tasks:
                    course_name = course_task.get("course_name", "")
                    priority = course_task.get("priority", "")
                    tasks = course_task.get("tasks", [])

                    st.markdown(f"**{course_name}** — Priority: `{priority}`")

                    for task in tasks:
                        st.write(f"- {task}")
            else:
                st.info("No tasks found for this week.")


def show_study_block_recommender(semester_plan):
    st.header("Study Preferences")
    st.caption("Choose your preferences before generating recommended study blocks.")

    course_names = get_unique_course_names(semester_plan)

    if not course_names:
        st.warning("No courses found in the semester plan.")
        return

    days_of_week = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    ]

    st.subheader("Semester Start Date")

    semester_start_date = st.date_input(
        "Select semester start date"
    )

    st.subheader("Lecture Days")

    lecture_schedules = {}

    for course_name in course_names:
        safe_course_key = make_safe_key(course_name)

        with st.expander(f"{course_name} lecture days", expanded=False):
            lecture_days = st.multiselect(
                f"Select lecture days for {course_name}",
                days_of_week,
                key=f"lecture_days_{safe_course_key}"
            )

            lecture_schedules[course_name] = {
                "lecture_days": lecture_days
            }

    st.subheader("Study Preferences")

    preferred_study_days = st.multiselect(
        "Preferred study days",
        days_of_week,
        default=["Monday", "Wednesday", "Friday"]
    )

    session_length_style = st.selectbox(
        "Preferred session length style",
        [
            "Short sessions: 30-45 minutes",
            "Balanced sessions: 60-90 minutes",
            "Deep work sessions: 90-120 minutes"
        ],
        index=1
    )

    weekend_preference = st.selectbox(
        "Weekend preference",
        [
            "No weekends",
            "Saturday only",
            "Sunday only",
            "Both Saturday and Sunday"
        ],
        index=1
    )

    generate_blocks_button = st.button(
        "Create Study Blocks",
        width="stretch"
    )

    if generate_blocks_button:
        if not preferred_study_days:
            st.warning("Please select at least one preferred study day.")
            return

        study_preferences = {
            "preferred_study_days": preferred_study_days,
            "session_length_style": session_length_style,
            "weekend_preference": weekend_preference
        }

        with st.spinner("Generating recommended study blocks..."):
            recommended_blocks = generate_recommended_study_blocks(
                semester_plan=semester_plan,
                semester_start_date=str(semester_start_date),
                lecture_schedules=lecture_schedules,
                study_preferences=study_preferences
            )

        save_json(RECOMMENDED_BLOCKS_CACHE, recommended_blocks)
        st.session_state["recommended_blocks"] = recommended_blocks
        st.session_state["show_study_preferences"] = False

        st.success("Recommended study blocks generated and saved.")


def display_recommended_study_blocks(recommended_blocks):
    st.subheader("Recommended Study Blocks")

    study_blocks = recommended_blocks.get("recommended_study_blocks", [])

    if not study_blocks:
        st.info("No recommended study blocks found.")
        return

    blocks_df = pd.DataFrame(study_blocks)

    blocks_df["google_calendar"] = blocks_df.apply(
        lambda row: create_google_calendar_link(row.to_dict()),
        axis=1
    )

    preferred_columns = [
        "week",
        "day",
        "date",
        "course_name",
        "task",
        "task_type",
        "recommended_duration_minutes",
        "priority",
        "reason",
        "google_calendar"
    ]

    existing_columns = [
        column for column in preferred_columns
        if column in blocks_df.columns
    ]

    blocks_df = blocks_df[existing_columns]

    calendar_column_config = {
        "google_calendar": st.column_config.LinkColumn(
            "Add to Google Calendar",
            display_text="📅"
        )
    }

    if "week" in blocks_df.columns:
        blocks_df["week_sort"] = blocks_df["week"].astype(str).str.extract(
            r"(\d+)"
        )[0]

        blocks_df["week_sort"] = pd.to_numeric(
            blocks_df["week_sort"],
            errors="coerce"
        ).fillna(0).astype(int)

        day_order = {
            "Monday": 1,
            "Tuesday": 2,
            "Wednesday": 3,
            "Thursday": 4,
            "Friday": 5,
            "Saturday": 6,
            "Sunday": 7
        }

        if "day" in blocks_df.columns:
            blocks_df["day_sort"] = blocks_df["day"].map(day_order).fillna(99)
            blocks_df = blocks_df.sort_values(
                by=["week_sort", "day_sort"]
            )
        else:
            blocks_df = blocks_df.sort_values(by=["week_sort"])

        csv = blocks_df.drop(
            columns=[
                column for column in ["week_sort", "day_sort", "google_calendar"]
                if column in blocks_df.columns
            ],
            errors="ignore"
        ).to_csv(index=False)

        st.download_button(
            "Download Recommended Study Blocks as CSV",
            csv,
            "recommended_study_blocks.csv",
            "text/csv",
            width="stretch"
        )

        week_numbers = blocks_df["week_sort"].unique()

        for week_number in week_numbers:
            week_df = blocks_df[
                blocks_df["week_sort"] == week_number
            ].copy()

            display_week_label = week_df["week"].iloc[0]

            with st.expander(f"Week {display_week_label}", expanded=False):
                if "day" in week_df.columns:
                    days = week_df["day"].dropna().unique()

                    for day in days:
                        day_df = week_df[week_df["day"] == day].copy()
                        day_date = ""

                        if "date" in day_df.columns and not day_df["date"].dropna().empty:
                            day_date = day_df["date"].dropna().iloc[0]

                        if day_date:
                            st.markdown(f"### {day} — {day_date}")
                        else:
                            st.markdown(f"### {day}")

                        columns_to_drop = [
                            column for column in ["week_sort", "day_sort", "week", "day", "date"]
                            if column in day_df.columns
                        ]

                        day_df = day_df.drop(columns=columns_to_drop)

                        st.dataframe(
                            day_df,
                            width="stretch",
                            column_config=calendar_column_config
                        )
                else:
                    columns_to_drop = [
                        column for column in ["week_sort", "day_sort"]
                        if column in week_df.columns
                    ]

                    week_df = week_df.drop(columns=columns_to_drop)

                    st.dataframe(
                        week_df,
                        width="stretch",
                        column_config=calendar_column_config
                    )
    else:
        st.dataframe(
            blocks_df,
            width="stretch",
            column_config=calendar_column_config
        )

    st.subheader("Recommendation Summary")

    scheduling_summary = recommended_blocks.get("scheduling_summary", {})

    total_blocks = scheduling_summary.get("total_blocks", len(study_blocks))
    warnings = scheduling_summary.get("warnings", [])

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Total Recommended Blocks", total_blocks)

    with col2:
        st.metric("Warnings", len(warnings))

    if warnings:
        st.warning("Recommendation warnings:")
        for warning in warnings:
            st.write(f"- {warning}")


def extract_and_cache_courses(uploaded_files=None):
    extracted_courses = []

    if uploaded_files:
        for uploaded_file in uploaded_files:
            with st.spinner(f"Extracting course data from {uploaded_file.name}..."):
                if uploaded_file.name.endswith(".txt"):
                    syllabus_text = uploaded_file.read().decode("utf-8")
                elif uploaded_file.name.endswith(".pdf"):
                    syllabus_text = read_uploaded_pdf(uploaded_file)
                else:
                    continue

                syllabus_text = clean_syllabus_text(syllabus_text)
                extracted_course = extract_assessments_from_syllabus(syllabus_text)

                if not extracted_course.get("is_valid_syllabus", True):
                    st.warning(
                        f"{uploaded_file.name} was skipped: "
                        f"{extracted_course.get('validation_reason', 'Not a valid syllabus.')}"
                    )
                    continue

                extracted_courses.append(extracted_course)

        save_json(EXTRACTED_COURSES_CACHE, extracted_courses)
        return extracted_courses

    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER, exist_ok=True)

    syllabus_files = [
        file_name for file_name in os.listdir(DATA_FOLDER)
        if file_name.endswith(".txt") or file_name.endswith(".pdf")
    ]

    if not syllabus_files:
        st.warning("No uploaded files or sample .txt/.pdf syllabus files found.")
        return []

    for file_name in syllabus_files:
        file_path = os.path.join(DATA_FOLDER, file_name)

        with st.spinner(f"Extracting course data from {file_name}..."):
            if file_name.endswith(".txt"):
                syllabus_text = read_text_file(file_path)
            elif file_name.endswith(".pdf"):
                syllabus_text = read_pdf_file(file_path)
            else:
                continue

            syllabus_text = clean_syllabus_text(syllabus_text)
            extracted_course = extract_assessments_from_syllabus(syllabus_text)
            extracted_courses.append(extracted_course)

    save_json(EXTRACTED_COURSES_CACHE, extracted_courses)

    return extracted_courses


def main():
    st.title("SemesterOS")
    st.caption("AI-powered semester roadmap and study block recommender")
    st.divider()

    if "extracted_courses" not in st.session_state:
        st.session_state["extracted_courses"] = None

    if "semester_plan" not in st.session_state:
        st.session_state["semester_plan"] = None

    if "recommended_blocks" not in st.session_state:
        st.session_state["recommended_blocks"] = None

    if "show_study_preferences" not in st.session_state:
        st.session_state["show_study_preferences"] = False

    st.sidebar.header("Controls")

    uploaded_files = st.sidebar.file_uploader(
        "Upload syllabus files",
        type=["pdf", "txt"],
        accept_multiple_files=True
    )

    extract_button = st.sidebar.button(
        "Extract and Save Course Data",
        width="stretch"
    )

    if extract_button:
        extracted_courses = extract_and_cache_courses(uploaded_files)

        if extracted_courses:
            st.session_state["extracted_courses"] = extracted_courses
            st.sidebar.success("Course data extracted and saved.")

    
    generate_plan_button = st.sidebar.button(
        "Generate and Save Semester Plan",
        width="stretch"
    )

    if generate_plan_button:
        extracted_courses = st.session_state.get("extracted_courses")

        if not extracted_courses:
            st.sidebar.warning("Please extract or load course data first.")
        else:
            with st.spinner("Generating semester roadmap..."):
                semester_plan = generate_semester_plan(extracted_courses)
                semester_plan = add_assignment_buffers_to_semester_plan(semester_plan)

            save_json(SEMESTER_PLAN_CACHE, semester_plan)
            st.session_state["semester_plan"] = semester_plan

            st.sidebar.success("Semester plan generated and saved.")

    generate_blocks_button = st.sidebar.button(
        "Generate Recommended Study Blocks",
        width="stretch"
    )

    if generate_blocks_button:
        semester_plan = st.session_state.get("semester_plan")

        if not semester_plan:
            st.sidebar.warning("Generate or load the semester roadmap first.")
        else:
            st.session_state["semester_plan"] = semester_plan
            st.session_state["show_study_preferences"] = True


    extracted_courses = st.session_state.get("extracted_courses")
    semester_plan = st.session_state.get("semester_plan")
    recommended_blocks = st.session_state.get("recommended_blocks")

    if not extracted_courses and not semester_plan and not recommended_blocks:
        st.info("Get started with SemesterOS:")

        st.markdown(
            """
            - Upload syllabus PDF/TXT files from the sidebar.
            - Click **Extract and Save Course Data**.
            - Click **Generate and Save Semester Plan**.
            - Open the **Study Blocks** tab and click **Generate Recommended Study Blocks** from the sidebar when ready.
            """
        )

    tab1, tab2, tab3 = st.tabs([
        "Courses",
        "Semester Roadmap",
        "Study Blocks"
    ])

    with tab1:
        if extracted_courses:
            show_course_data(extracted_courses)
        else:
            st.info("No courses extracted yet.")

    with tab2:
        if semester_plan:
            show_semester_roadmap(semester_plan)
        else:
            st.info("No semester roadmap generated yet.")

    with tab3:
        if st.session_state.get("show_study_preferences", False):
            if semester_plan:
                show_study_block_recommender(semester_plan)
            else:
                st.warning("Generate or load the semester roadmap first.")
        elif recommended_blocks:
            display_recommended_study_blocks(recommended_blocks)
        else:
            st.info("Click 'Generate Recommended Study Blocks' in the sidebar to begin.")


if __name__ == "__main__":
    main()