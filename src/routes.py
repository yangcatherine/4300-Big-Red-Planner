"""
Routes: React app serving, course search, schedule generation, and episode search API.

To enable AI chat, set USE_LLM = True below. See llm_routes.py for AI code.
"""
import json
import os
from flask import send_from_directory, request, jsonify
from models import db, Episode, Review

# ── AI toggle ────────────────────────────────────────────────────────────────
USE_LLM = False
# USE_LLM = True
# ─────────────────────────────────────────────────────────────────────────────

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
_catalog_path = os.path.join(_project_root, "data", "cornell_FA25_courses.json")
_ratings_path = os.path.join(_project_root, "data", "ratings.jsonl")


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


def _course_to_schedule_course(course: dict) -> dict:
    """Convert full course dict to ScheduleCourse format."""
    instructors = []
    seen = set()
    meetings = []
    for sec in course.get("sections", []):
        sec_type = sec.get("type", "UNT")
        for inst in sec.get("instructors", []):
            if inst and inst not in seen:
                seen.add(inst)
                instructors.append(inst)
        for m in sec.get("meetings", []):
            meetings.append({
                "type": sec_type,
                "days": m.get("days", ""),
                "start": m.get("start", ""),
                "end": m.get("end", ""),
            })
    return {
        "course_id": course.get("course_id", ""),
        "title": course.get("title", ""),
        "credits": course.get("credits_min", course.get("credits_max", 0)),
        "distributions": course.get("distribution_requirements", []),
        "instructors": instructors,
        "meetings": meetings,
    }


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
            w_sim = body.get("w_sim", 0.5)
            w_rating = body.get("w_rating", 0.3)
            w_difficulty = body.get("w_difficulty", 0.2)
            difficulty_filter = body.get("difficulty_filter", None) 

            if len(required_ids) < 2:
                return jsonify({"error": "Add at least 2 required courses."}), 400

            catalog = _load_catalog()
            id_to_course = {c["course_id"]: c for c in catalog}
            required = [id_to_course[cid] for cid in required_ids if cid in id_to_course]
            if len(required) < 2:
                return jsonify({"error": "Could not find valid required courses."}), 400

            from schedule_generator import generate_schedules
            from score_schedule import rank_schedules_with_scores, load_professors, clean_name, get_course_instructors
            import pandas as pd

            raw_schedules = generate_schedules(
                required, distributions, catalog=catalog, excluded_courses=[],
                max_results=300,
            )

            ranked_pairs = []
            print(f"ratings path: {_ratings_path}")
            print(f"exists: {os.path.exists(_ratings_path)}")
            if os.path.exists(_ratings_path):
                try:
                    from score_schedule import rank_schedules_with_scores, load_professors
                    df, prof_dict, vectorizer, tfidf_matrix = load_professors(_ratings_path)
                    ranked_pairs = rank_schedules_with_scores(
                        raw_schedules, df, prof_dict, vectorizer, tfidf_matrix, query,  w_sim, w_rating, w_difficulty
                    )
                    if difficulty_filter:
                        def avg_difficulty(sched):
                            diffs = []
                            for course in sched:
                                for inst in get_course_instructors(course):
                                    idx = prof_dict.get(clean_name(inst))
                                    if idx is not None:
                                        d = df.iloc[idx]["Difficulty"]
                                        if not pd.isna(d):
                                            diffs.append(d)
                            return sum(diffs) / len(diffs) if diffs else 2.5

                        def difficulty_matches(sched):
                            avg = avg_difficulty(sched)
                            if difficulty_filter == "easy":
                                return avg < 2.5
                            elif difficulty_filter == "medium":
                                return 2.5 <= avg <= 3.5
                            elif difficulty_filter == "hard":
                                return avg > 3.5
                            return True

                        ranked_pairs = [(score, sched) for score, sched in ranked_pairs if difficulty_matches(sched)]

                except Exception:
                    ranked_pairs = [(0.5, s) for s in raw_schedules]
            else:
                #print("here")
                ranked_pairs = [(0.5, s) for s in raw_schedules]

            def _total_credits(sched):
                return sum(c.get("credits_min", c.get("credits_max", 0)) for c in sched)

            schedules = []
            for i, (score, sched) in enumerate(ranked_pairs[:top_n], 1):
                schedules.append({
                    "rank": i,
                    "score": score,
                    "total_credits": _total_credits(sched),
                    "courses": [_course_to_schedule_course(c) for c in sched],
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
