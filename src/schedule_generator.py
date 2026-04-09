"""
Finds all valid course schedules that add distribution-fulfilling courses
without time conflicts with required courses or with each other.
"""

import random
from itertools import product
from typing import Optional, List


DAY_MAP = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}
MAX_GENERATED_SCHEDULES = 250


def _parse_days(days_str: str) -> set[int]:
    """Parse days string into set of day indices."""
    if not days_str or days_str == "TBA":
        return set()
    return {DAY_MAP[d] for d in days_str.upper() if d in DAY_MAP}


def _time_to_minutes(time_str: str) -> Optional[int]:
    """Convert 'HH:MM' to minutes since midnight. Returns None for TBA."""
    if not time_str or time_str == "TBA":
        return None
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _meetings_overlap(m1: dict, m2: dict) -> bool:
    """Check if two meetings overlap in time."""
    days1 = _parse_days(m1.get("days", ""))
    days2 = _parse_days(m2.get("days", ""))
    if not days1 or not days2:
        return False
    if not (days1 & days2):
        return False
    start1 = _time_to_minutes(m1.get("start", ""))
    end1 = _time_to_minutes(m1.get("end", ""))
    start2 = _time_to_minutes(m2.get("start", ""))
    end2 = _time_to_minutes(m2.get("end", ""))
    if start1 is None or end1 is None or start2 is None or end2 is None:
        return False
    return not (end1 <= start2 or end2 <= start1)


def _get_section_meetings(section: dict) -> list[dict]:
    """Get meetings from a section, deduplicated by day+time."""
    meetings = section.get("meetings", [])
    seen = set()
    result = []
    for m in meetings:
        key = (m.get("days"), m.get("start"), m.get("end"))
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result


def _get_section_combinations(course: dict) -> list[list[dict]]:
    """Get all valid section combinations for a course."""
    sections = course.get("sections", [])
    if not sections:
        return [[]]

    # Group sections by type
    by_type: dict[str, list[dict]] = {}
    for sec in sections:
        t = sec.get("type", "UNT")
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(sec)

    type_names = list(by_type.keys())
    choices = [by_type[t] for t in type_names]
    combinations = []
    for combo in product(*choices):
        combinations.append(list(combo))
    return combinations


def _meetings_from_section_combo(sections: list[dict]) -> list[dict]:
    """Flatten all meetings from a section combination."""
    meetings = []
    for sec in sections:
        meetings.extend(_get_section_meetings(sec))
    return meetings


def _schedules_overlap(meetings_a: list[dict], meetings_b: list[dict]) -> bool:
    """Check if any meeting in A overlaps with any meeting in B."""
    for m1 in meetings_a:
        for m2 in meetings_b:
            if _meetings_overlap(m1, m2):
                return True
    return False


def _total_credits(courses: list[dict]) -> int:
    """Sum credits_max for all courses in a schedule."""
    return sum(c.get("credits_max", c.get("credits_min", 0)) for c in courses)


def _get_courses_from_allowed_distributions(
    catalog: list[dict], allowed_dists: set[str], exclude_ids: set[str]
) -> list[dict]:
    """Get courses whose distributions are only from the allowed set."""
    return [
        c
        for c in catalog
        if c.get("course_id") not in exclude_ids
        and (dists := set(c.get("distribution_requirements", [])))
        and dists <= allowed_dists
    ]


def _stable_seed(parts: list[str]) -> int:
    """Build a seed from stable string parts."""
    joined = "|".join(parts)
    return sum((i + 1) * ord(ch) for i, ch in enumerate(joined))


def generate_schedules(
    required_courses: list[dict],
    distributions: list[str],
    catalog: Optional[list] = None,
    catalog_path: Optional[str] = None,
    excluded_courses: Optional[list] = None,
    max_results: Optional[int] = None,
) -> List[list]:
    """
    Generate valid course schedules that add courses satisfying the desired
    distributions without overlapping with required courses or with each other.

    Args:
        required_courses: List of course dicts the student must take.
        distributions: Added courses must have distributions only from this set.
        catalog: Full list of course dicts to choose from. If None, catalog_path is used.
        catalog_path: Path to JSON file with courses.
        excluded_courses: Courses already taken. Can be a list of course dicts or course
                          ID strings. These will not be added to any schedule.
        max_results: Optional requested result limit. Generation is always capped at 250.

    Returns:
        List of valid schedules. Each schedule is a list of course dicts.
        Only schedules with total credits >= 12 and < 22 are returned.

    Raises:
        ValueError: If fewer than 2 required courses are provided.
    """
    import json
    import os

    if len(required_courses) < 2:
        raise ValueError("At least 2 required courses must be provided")

    if catalog is None:
        if catalog_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            catalog_path = os.path.join(
                os.path.dirname(script_dir), "data", "cornell_FA25_courses.json"
            )
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f)

    required_ids = {c.get("course_id", "") for c in required_courses}
    exclude_ids = required_ids.copy()
    if excluded_courses:
        for item in excluded_courses:
            cid = item.get("course_id", item) if isinstance(item, dict) else item
            if cid:
                exclude_ids.add(str(cid))

    def get_blocked_meetings(course: dict) -> list[dict]:
        """Get of all meetings from a course."""
        all_meetings = []
        for sec in course.get("sections", []):
            all_meetings.extend(_get_section_meetings(sec))
        return all_meetings

    required_meetings = []
    for c in required_courses:
        required_meetings.extend(get_blocked_meetings(c))

    # Add courses from allowed distributions
    allowed_dists = set(distributions)
    results: list[list[dict]] = []
    if max_results is None:
        limit = MAX_GENERATED_SCHEDULES
    else:
        limit = min(max_results, MAX_GENERATED_SCHEDULES)
    seed_parts = sorted(required_ids) + sorted(allowed_dists)
    rng = random.Random(_stable_seed(seed_parts))

    def backtrack(
        current_schedule: list[dict],
        current_meetings: list[dict],
        used_course_ids: set[str],
        min_course_id: str,
    ) -> None:
        if len(results) >= limit:
            return
        if _total_credits(current_schedule) >= 12:
            results.append(current_schedule.copy())
        candidates = _get_courses_from_allowed_distributions(
            catalog, allowed_dists, used_course_ids
        )
        rng.shuffle(candidates)
        for course in candidates:
            if len(results) >= limit:
                return
            cid = course.get("course_id", "")
            if cid <= min_course_id:
                continue
            for combo in _get_section_combinations(course):
                combo_meetings = _meetings_from_section_combo(combo)
                if _schedules_overlap(combo_meetings, required_meetings):
                    continue
                if _schedules_overlap(combo_meetings, current_meetings):
                    continue
                new_schedule = current_schedule + [course]
                if _total_credits(new_schedule) >= 22:
                    continue
                new_meetings = current_meetings + combo_meetings
                new_used = used_course_ids | {cid}
                backtrack(new_schedule, new_meetings, new_used, cid)

    initial_schedule = list(required_courses)
    backtrack(initial_schedule, [], exclude_ids, "")

    # Filter by credit limits
    seen = set()
    unique = []
    for sched in results:
        creds = _total_credits(sched)
        if creds < 12 or creds >= 22:
            continue
        key = tuple(sorted(c.get("course_id", "") for c in sched))
        if key not in seen:
            seen.add(key)
            unique.append(sched)

    # Mix output order
    random.Random(_stable_seed(seed_parts)).shuffle(unique)

    return unique
