"""Test script for generating schedules"""

import json
import sys

sys.path.insert(0, "src")
from schedule_generator import (
    MAX_GENERATED_SCHEDULES,
    _total_credits,
    generate_schedules,
)

with open("data/cornell_FA25_courses.json") as f:
    catalog = json.load(f)

required = [c for c in catalog if c["course_id"] in ["CS 1110", "CS 2110"]]
required_ids = {c["course_id"] for c in required}

schedules = generate_schedules(
    required,
    ["ALC", "HST", "SCD", "WRI"],
    catalog=catalog,
    excluded_courses=[],
)

assert (
    len(schedules) <= MAX_GENERATED_SCHEDULES
), f"Expected at most {MAX_GENERATED_SCHEDULES} schedules, got {len(schedules)}"

for sched in schedules:
    for course in sched:
        if course["course_id"] in required_ids:
            continue
        assert not (
            course.get("prerequisites_raw", "") or ""
        ).strip(), f"Course {course['course_id']} has prereqs"

print(f"Found {len(schedules)} schedules\n")
for i, sched in enumerate(schedules[:10]):
    creds = _total_credits(sched)
    ids = [c["course_id"] for c in sched]
    print(f"{i+1}. {ids} ({creds} credits)")

print("\nAll checks passed.")
