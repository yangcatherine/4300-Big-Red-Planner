import requests
import json
import os
import re
from datetime import datetime

API_URL = "https://classes.cornell.edu/api/2.0/search/classes.json"
ROSTER = "FA25"


def format_to_24h(time_str):
    """Converts military to standard time"""
    if not time_str or time_str.strip() == "":
        return "TBA"
    try:
        clean_time = time_str.strip().upper()
        in_time = datetime.strptime(clean_time, "%I:%M%p")
        return in_time.strftime("%H:%M")
    except ValueError:
        return time_str


def extract_course_ids(text):
    if not text or text == "None":
        return []
    pattern = r"([A-Z]{2,5})\s+(\d{4}(?:[\s,&\/or]+\d{4})*)"
    matches = re.findall(pattern, text)
    found_ids = []
    for subject, numbers_str in matches:
        numbers = re.findall(r"\d{4}", numbers_str)
        for num in numbers:
            found_ids.append(f"{subject} {num}")
    return sorted(list(set(found_ids)))


def get_all_as_courses():
    subj_url = (
        f"https://classes.cornell.edu/api/2.0/config/subjects.json?roster={ROSTER}"
    )
    subjects = requests.get(subj_url).json()["data"]["subjects"]

    all_filtered_courses = []
    all_course_ids = set()

    for s in subjects:
        subj_code = s["value"]
        if subj_code == "PE":
            continue

        print(f"Fetching {subj_code}...")
        params = {"roster": ROSTER, "subject": subj_code}

        try:
            response = requests.get(API_URL, params=params)
            if response.status_code != 200:
                continue

            data = response.json()
            classes = data.get("data", {}).get("classes", [])

            for cls in classes:
                # Get distribution
                attributes = cls.get("crseAttrs", [])
                as_dist = [
                    str(a.get("crseAttrValue", "")).replace("-AS", "")
                    for a in attributes
                    if "-AS" in str(a.get("crseAttrValue", ""))
                ]

                if as_dist:
                    if f"{cls.get('subject')} {cls.get('catalogNbr')}" in all_course_ids:
                        continue  # Skip crosslisted courses

                    all_course_ids.add(f"{cls.get('subject')} {cls.get('catalogNbr')}")

                    enroll_groups = cls.get("enrollGroups", [])
                    units_min = 0
                    units_max = 0
                    simple_combinations = []
                    if enroll_groups:
                        units_min = enroll_groups[0].get("unitsMinimum", 0)
                        units_max = enroll_groups[0].get("unitsMaximum", 0)
                        simple_combinations = enroll_groups[0].get("simpleCombinations", [])

                    for item in simple_combinations:
                        all_course_ids.add(f"{item.get('subject')} {item.get('catalogNbr')}")
                    sections_list = []
                    
                    for group in enroll_groups:
                        for sec in group.get("classSections", []):

                            processed_meetings = []
                            # Get meetings
                            for m in sec.get("meetings", []):
                                processed_meetings.append(
                                    {
                                        "days": m.get("pattern") or "TBA",
                                        "start": format_to_24h(m.get("timeStart")),
                                        "end": format_to_24h(m.get("timeEnd")),
                                        "facility": sec.get("locationDescr") or "TBA",
                                    }
                                )

                            # Get instructors
                            profs = []
                            for m in sec.get("meetings", []):
                                for p in m.get("instructors", []):
                                    name = f"{p.get('firstName')} {p.get('lastName')}"
                                    if name not in profs:
                                        profs.append(name)

                            sections_list.append(
                                {
                                    "type": sec.get("ssrComponent", "UNT"),
                                    "section": sec.get("section", "N/A"),
                                    "class_number": sec.get("classNbr"),
                                    "meetings": processed_meetings,
                                    "instructors": profs,
                                }
                            )

                    raw_prereqs = cls.get("catalogPrereq", "None")
                    raw_overlaps = cls.get("catalogForbiddenOverlaps", "None")

                    # Build course object
                    all_filtered_courses.append(
                        {
                            "course_id": f"{cls.get('subject')} {cls.get('catalogNbr')}",
                            "title": cls.get("titleLong", "No Title"),
                            "credits_min": units_min,
                            "credits_max": units_max,
                            "description": cls.get(
                                "description", "No description available."
                            ),
                            "distribution_requirements": as_dist,
                            "prerequisites_raw": raw_prereqs,
                            "prerequisites_list": extract_course_ids(raw_prereqs),
                            "forbidden_overlaps_raw": raw_overlaps,
                            "forbidden_overlaps_list": extract_course_ids(raw_overlaps),
                            "sections": sections_list,
                            "url": f"https://classes.cornell.edu/browse/roster/{ROSTER}/class/{cls.get('subject')}/{cls.get('catalogNbr')}",
                        }
                    )
        except Exception as e:
            print(f"Error processing subject {subj_code}: {e}")
            continue

    return all_filtered_courses


if __name__ == "__main__":
    scraped_data = get_all_as_courses()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "cornell_FA25_courses.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=4, ensure_ascii=False)

    print(f"\nScrape complete!")
    print(f"Total A&S Courses found: {len(scraped_data)}")
    print(f"File saved to: {output_path}")
