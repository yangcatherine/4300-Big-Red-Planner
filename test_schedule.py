"""Test script for generating schedules"""

import json
import sys

sys.path.insert(0, "src")
from schedule_generator import generate_schedules, _total_credits

with open("data/cornell_FA25_courses.json") as f:
    catalog = json.load(f)

required = [c for c in catalog if c["course_id"] in ["CS 1110", "CS 2110"]]

schedules = generate_schedules(
    required,
    ["ALC", "HST", "SCD", "WRI"],
    catalog=catalog,
    excluded_courses=[],
)

print(f"Found {len(schedules)} schedules\n")
for i, sched in enumerate(schedules[:10]):
    creds = _total_credits(sched)
    ids = [c["course_id"] for c in sched]
    print(f"{i+1}. {ids} ({creds} credits)")
