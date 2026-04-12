"""
Routes: React app serving, course search, schedule generation, and episode search API.

To enable AI chat, set USE_LLM = True below. See llm_routes.py for AI code.
"""
import os
import json
from itertools import product
from flask import send_from_directory, request, jsonify, current_app
from sklearn.metrics.pairwise import cosine_similarity
from models import db, Professor
from schedule_generator import generate_schedules

# ── AI toggle ────────────────────────────────────────────────────────────────
USE_LLM = False
# ─────────────────────────────────────────────────────────────────────────────

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
_catalog_path = os.path.join(_project_root, "data", "cornell_FA25_courses.json")
_ratings_jsonl_path = os.path.join(_project_root, "data", "ratings.jsonl")
_ratings_csv_path = os.path.join(_project_root, "data", "cornell_ratings_data.csv")
_ratings_path = _ratings_jsonl_path if os.path.exists(_ratings_jsonl_path) else _ratings_csv_path
_DAY_MAP = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}
_DEFAULT_WEIGHTS = {"similarity": 0.5, "rating": 0.3, "difficulty": 0.2}


def _load_catalog():
    """Load course catalog from JSON."""
    with open(_catalog_path, encoding="utf-8") as f:
        return json.load(f)


def _course_to_suggestion(course: dict) -> dict:
    """Convert full course dict to CourseSuggestion format."""
    return {
        "course_id": course.get("course_id", ""),
        "title": course.get("title", ""),
        "credits": course.get("credits_min", course.get("credits_max", 0)),
        "distributions": course.get("distribution_requirements", []),
    }


def _time_to_minutes(time_str: str):
    if not time_str or time_str == "TBA":
        return None
    try:
        h, m = time_str.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def _parse_days(days_str: str) -> set:
    if not days_str or days_str == "TBA":
        return set()
    return {_DAY_MAP[d] for d in days_str.upper() if d in _DAY_MAP}


def _meetings_overlap(m1: dict, m2: dict) -> bool:
    d1 = _parse_days(m1.get("days", ""))
    d2 = _parse_days(m2.get("days", ""))
    if not d1 or not d2 or not (d1 & d2):
        return False
    s1 = _time_to_minutes(m1.get("start", ""))
    e1 = _time_to_minutes(m1.get("end", ""))
    s2 = _time_to_minutes(m2.get("start", ""))
    e2 = _time_to_minutes(m2.get("end", ""))
    if s1 is None or e1 is None or s2 is None or e2 is None:
        return False
    return not (e1 <= s2 or e2 <= s1)


def _meetings_conflict_with_any(meetings: list[dict], occupied: list[dict]) -> bool:
    return any(_meetings_overlap(m, o) for m in meetings for o in occupied)


def _section_meetings(section: dict) -> list[dict]:
    sec_type = section.get("type", "UNT")
    seen = set()
    out = []
    for m in section.get("meetings", []):
        key = (m.get("days", ""), m.get("start", ""), m.get("end", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "type": sec_type,
            "days": m.get("days", ""),
            "start": m.get("start", ""),
            "end": m.get("end", ""),
        })
    return out


def _section_combinations(course: dict) -> list[list[dict]]:
    sections = course.get("sections", [])
    if not sections:
        return [[]]
    by_type = {}
    for sec in sections:
        t = sec.get("type", "UNT")
        by_type.setdefault(t, []).append(sec)
    return [list(combo) for combo in product(*by_type.values())]


def _choose_non_overlapping_sections(schedule_courses: list[dict]) -> dict:
    combos_by_course = {}
    for course in schedule_courses:
        cid = course.get("course_id", "")
        combos = _section_combinations(course)
        combos_by_course[cid] = combos if combos else [[]]

    selected = {}

    def backtrack(idx: int, occupied: list[dict]) -> bool:
        if idx >= len(schedule_courses):
            return True
        course = schedule_courses[idx]
        cid = course.get("course_id", "")
        for combo in combos_by_course.get(cid, [[]]):
            combo_meetings = []
            for sec in combo:
                combo_meetings.extend(_section_meetings(sec))
            if _meetings_conflict_with_any(combo_meetings, occupied):
                continue
            selected[cid] = combo
            if backtrack(idx + 1, occupied + combo_meetings):
                return True
        return False

    if backtrack(0, []):
        return selected
    return {c.get("course_id", ""): [] for c in schedule_courses}


def _course_to_schedule_course(course: dict, selected_sections: list[dict] | None = None) -> dict:
    """Convert full course dict to ScheduleCourse format."""
    instructors = []
    seen = set()
    meetings = []
    sections = selected_sections if selected_sections is not None else course.get("sections", [])
    for sec in sections:
        sec_type = sec.get("type", "UNT")
        for inst in sec.get("instructors", []):
            if inst and inst not in seen:
                seen.add(inst)
                instructors.append(inst)
        meetings.extend(_section_meetings(sec))
    return {
        "course_id": course.get("course_id", ""),
        "title": course.get("title", ""),
        "credits": course.get("credits_min", course.get("credits_max", 0)),
        "distributions": course.get("distribution_requirements", []),
        "instructors": instructors,
        "meetings": meetings,
    }


def _clean_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip().lower().replace(".", "")


def _safe_weight(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if v < 0:
        return 0.0
    return v


def _normalize_weights(raw_weights: dict) -> dict:
    weights = {
        "similarity": _safe_weight(raw_weights.get("similarity"), _DEFAULT_WEIGHTS["similarity"]),
        "rating": _safe_weight(raw_weights.get("rating"), _DEFAULT_WEIGHTS["rating"]),
        "difficulty": _safe_weight(raw_weights.get("difficulty"), _DEFAULT_WEIGHTS["difficulty"]),
    }
    total = sum(weights.values())
    if total <= 0:
        return _DEFAULT_WEIGHTS.copy()
    return {k: v / total for k, v in weights.items()}


def _score_schedule_with_breakdown(
    schedule_courses: list[dict], df, prof_dict: dict, vectorizer, tfidf_matrix, query: str, weights: dict
):
    query_vec = vectorizer.transform([query or ""])
    course_breakdown = []
    sim_values = []
    rating_values = []
    difficulty_values = []

    for course in schedule_courses:
        instructor_components = []
        for inst in course.get("instructors", []):
            prof_idx = prof_dict.get(_clean_name(inst))
            if prof_idx is None:
                continue
            row = df.iloc[prof_idx]
            rating = float(row.get("Rating", 0.0) or 0.0)
            difficulty = float(row.get("Difficulty", 0.0) or 0.0)
            num_ratings = int(row.get("Num_Ratings", 0) or 0)
            if num_ratings <= 0:
                continue
            sim = cosine_similarity(query_vec, tfidf_matrix[prof_idx])[0][0]
            rating_norm = rating / 5.0
            difficulty_norm = difficulty / 5.0
            instructor_components.append({
                "sim": sim,
                "rating": rating_norm,
                "difficulty": difficulty_norm,
                "score": (
                    weights["similarity"] * sim
                    + weights["rating"] * rating_norm
                    + weights["difficulty"] * difficulty_norm
                ),
            })

        if instructor_components:
            avg_sim = sum(x["sim"] for x in instructor_components) / len(instructor_components)
            avg_rating = sum(x["rating"] for x in instructor_components) / len(instructor_components)
            avg_difficulty = sum(x["difficulty"] for x in instructor_components) / len(instructor_components)
            course_score = sum(x["score"] for x in instructor_components) / len(instructor_components)
            explanation = (
                f"Matched {len(instructor_components)} instructor(s) with reviews "
                f"for this course section choice."
            )
        else:
            avg_sim = 0.0
            avg_rating = 0.0
            avg_difficulty = 0.0
            course_score = 0.0
            explanation = "No instructor review data matched; this course contributes 0.00."

        sim_values.append(avg_sim)
        rating_values.append(avg_rating)
        difficulty_values.append(avg_difficulty)
        course_breakdown.append({
            "course_id": course.get("course_id", ""),
            "title": course.get("title", ""),
            "score": course_score,
            "matched_professors": len(instructor_components),
            "explanation": explanation,
        })

    if not course_breakdown:
        return 0.0, {
            "weights": weights,
            "components": {"similarity": 0.0, "rating": 0.0, "difficulty": 0.0},
            "weighted_components": {"similarity": 0.0, "rating": 0.0, "difficulty": 0.0},
            "explanation": "No scorable courses were found in this schedule.",
            "course_breakdown": [],
        }

    comp_sim = sum(sim_values) / len(sim_values)
    comp_rating = sum(rating_values) / len(rating_values)
    comp_difficulty = sum(difficulty_values) / len(difficulty_values)
    weighted = {
        "similarity": weights["similarity"] * comp_sim,
        "rating": weights["rating"] * comp_rating,
        "difficulty": weights["difficulty"] * comp_difficulty,
    }
    schedule_score = (
        sum(c["score"] for c in course_breakdown) / len(course_breakdown)
        if course_breakdown else 0.0
    )
    breakdown = {
        "weights": weights,
        "components": {
            "similarity": comp_sim,
            "rating": comp_rating,
            "difficulty": comp_difficulty,
        },
        "weighted_components": weighted,
        "explanation": (
            "Score is the average course score, where each course score combines "
            "review similarity, rating, and difficulty using your selected weights."
        ),
        "course_breakdown": course_breakdown,
    }
    return schedule_score, breakdown


def json_search(query):
    if not query or not query.strip():
        query = "Kardashian"
    results = db.session.query(Episode, Review).join(
        Review, Episode.id == Review.id
    ).filter(
        Episode.title.ilike(f'%{query}%')
    ).all()
    matches = []
    for episode, review in results:
        matches.append({
            'title': episode.title,
            'descr': episode.descr,
            'imdb_rating': review.imdb_rating
        })
    return matches


def register_routes(app):
    @app.route("/api/config")
    def config():
        return jsonify({"use_llm": USE_LLM})

    @app.route("/api/episodes")
    def episodes_search():
        text = request.args.get("title", "")
        return jsonify(json_search(text))

    @app.route("/api/courses/search")
    def courses_search():
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify([])
        catalog = _load_catalog()
        q_lower = q.lower()

        by_prefix = [] 
        by_cid = []
        by_title = []

        for c in catalog:
            cid = (c.get("course_id") or "").lower()
            title = (c.get("title") or "").lower()
            if cid.startswith(q_lower) or cid.startswith(q_lower + " "):
                by_prefix.append(_course_to_suggestion(c))
            elif q_lower in cid:
                by_cid.append(_course_to_suggestion(c))
            elif q_lower in title and len(by_prefix) + len(by_cid) + len(by_title) < 20:
                by_title.append(_course_to_suggestion(c))
        matches = by_prefix + by_cid + by_title[: 20 - len(by_prefix) - len(by_cid)]
        return jsonify(matches[:20])

    @app.route("/api/schedules", methods=["POST"])
    def generate_schedules_api():
        try:
            body = request.get_json() or {}
            required_ids = body.get("required_course_ids", [])
            distributions = body.get("distributions", [])
            query = body.get("query", "")
            top_n = body.get("top_n", 10)
            normalized_weights = _normalize_weights({
                "similarity": body.get("w_sim", _DEFAULT_WEIGHTS["similarity"]),
                "rating": body.get("w_rating", _DEFAULT_WEIGHTS["rating"]),
                "difficulty": body.get("w_difficulty", _DEFAULT_WEIGHTS["difficulty"]),
            })

            if len(required_ids) < 2:
                return jsonify({"error": "Add at least 2 required courses."}), 400

            catalog = _load_catalog()
            id_to_course = {c["course_id"]: c for c in catalog}
            required = [id_to_course[cid] for cid in required_ids if cid in id_to_course]
            if len(required) < 2:
                return jsonify({"error": "Could not find valid required courses."}), 400

            raw_schedules = generate_schedules(
                required, distributions, catalog=catalog, excluded_courses=[],
                max_results=300,
            )

            ranked_rows = []
            scoring_error = None
            if os.path.exists(_ratings_path):
                try:
                    from score_schedule import load_professors
                    df, prof_dict, vectorizer, tfidf_matrix = load_professors(_ratings_path)
                    for sched in raw_schedules:
                        selected_sections_by_course = _choose_non_overlapping_sections(sched)
                        schedule_courses = [
                            _course_to_schedule_course(
                                c,
                                selected_sections_by_course.get(c.get("course_id", ""), []),
                            )
                            for c in sched
                        ]
                        score, score_breakdown = _score_schedule_with_breakdown(
                            schedule_courses,
                            df,
                            prof_dict,
                            vectorizer,
                            tfidf_matrix,
                            query,
                            normalized_weights,
                        )
                        ranked_rows.append({
                            "score": score,
                            "score_breakdown": score_breakdown,
                            "raw_sched": sched,
                            "courses": schedule_courses,
                        })
                except Exception as e:
                    scoring_error = f"{type(e).__name__}: {e}"
                    ranked_rows = []
            else:
                scoring_error = f"ratings data not found at {_ratings_path}"
                ranked_rows = []

            if not ranked_rows:
                for sched in raw_schedules:
                    selected_sections_by_course = _choose_non_overlapping_sections(sched)
                    schedule_courses = [
                        _course_to_schedule_course(
                            c,
                            selected_sections_by_course.get(c.get("course_id", ""), []),
                        )
                        for c in sched
                    ]
                    ranked_rows.append({
                        "score": 0.5,
                        "score_breakdown": {
                            "weights": normalized_weights,
                            "components": {"similarity": 0.0, "rating": 0.0, "difficulty": 0.0},
                            "weighted_components": {"similarity": 0.0, "rating": 0.0, "difficulty": 0.0},
                            "explanation": (
                                "Professor rating data is unavailable; using neutral score."
                                + (f" ({scoring_error})" if scoring_error else "")
                            ),
                            "course_breakdown": [
                                {
                                    "course_id": c.get("course_id", ""),
                                    "title": c.get("title", ""),
                                    "score": 0.0,
                                    "matched_professors": 0,
                                    "explanation": "No rating data available for this course.",
                                }
                                for c in schedule_courses
                            ],
                        },
                        "raw_sched": sched,
                        "courses": schedule_courses,
                    })

            ranked_rows.sort(key=lambda x: x["score"], reverse=True)

            def _total_credits(sched):
                return sum(c.get("credits_min", c.get("credits_max", 0)) for c in sched)

            schedules = []
            for i, row in enumerate(ranked_rows[:top_n], 1):
                schedules.append({
                    "rank": i,
                    "score": row["score"],
                    "score_breakdown": row["score_breakdown"],
                    "total_credits": _total_credits(row["raw_sched"]),
                    "courses": row["courses"],
                })

            return jsonify({
                "schedules": schedules,
                "total": len(raw_schedules),
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if USE_LLM:
        from llm_routes import register_chat_route
        register_chat_route(app, json_search)

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')
