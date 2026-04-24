"""
LLM chat route — only loaded when USE_LLM = True in routes.py.
Adds a POST /api/chat endpoint that performs LLM-driven RAG.

Setup:
  1. Add SPARK_API_KEY=your_key to .env
  2. Set USE_LLM = True in routes.py
"""

import json
import os
import re
import logging
from flask import request, jsonify, Response, stream_with_context
from infosci_spark_client import LLMClient

logger = logging.getLogger(__name__)


def llm_search_decision(client, user_message):
    messages = [
        {
            "role": "system",
            "content": (
                "You have access to a database of Keeping Up with the Kardashians episode titles, "
                "descriptions, and IMDB ratings. Search is by a single word in the episode title. "
                "Reply with exactly: YES followed by one space and ONE word to search (e.g. YES wedding), "
                "or NO if the question does not need episode data."
            ),
        },
        {"role": "user", "content": user_message},
    ]
    response = client.chat(messages)
    content = (response.get("content") or "").strip().upper()
    logger.info(f"LLM search decision: {content}")
    if re.search(r"\bNO\b", content) and not re.search(r"\bYES\b", content):
        return False, None
    yes_match = re.search(r"\bYES\s+(\w+)", content)
    if yes_match:
        return True, yes_match.group(1).lower()
    if re.search(r"\bYES\b", content):
        return True, "Kardashian"
    return False, None


def llm_rewrite_query(client, user_message):
    messages = [
        {
            "role": "system",
            "content": (
                "You rewrite student course preference queries so they match the language "
                "used in professor reviews on sites like RateMyProfessor.\n\n"
                "Rules:\n"
                "- Output ONLY the rewritten query string. No explanation, no JSON, no punctuation.\n"
                "- Keep it to 5-10 words.\n"
                "- Use words that would actually appear in a student-written professor review.\n"
                "- Expand slang/informal phrases: "
                "'chill' -> 'relaxed easygoing lenient', "
                "'no essays' -> 'no essays minimal writing', "
                "'fun' -> 'engaging entertaining enjoyable', "
                "'easy A' -> 'easy grading high grades lenient'.\n"
                "- If the query has no professor preference content, output it unchanged."
            ),
        },
        {"role": "user", "content": user_message},
    ]
    response = client.chat(messages)
    rewritten = (response.get("content") or user_message).strip()
    rewritten = re.sub(r'^["\']|["\']$', "", rewritten).strip()
    logger.info(f"Query rewrite: '{user_message}' -> '{rewritten}'")
    return rewritten


def _parse_json_object_from_llm(text: str) -> dict:
    """Parse JSON from an LLM reply; tolerate ```json fences and surrounding text."""
    t = (text or "").strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if m:
        t = m.group(0)
    t = re.sub(r"^```\w*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    return json.loads(t)


def extract_schedule_preferences(client, user_message: str) -> dict:
    """Use the LLM to turn natural language into a fixed boolean-preference JSON schema."""
    messages = [
        {
            "role": "system",
            "content": (
                "You extract scheduling and weekly-layout preferences from a student's message. "
                "Return JSON ONLY (no markdown, no explanation) with exactly these keys, all booleans:\n"
                "{\n"
                '  "no_friday": true or false — avoid class meetings on Friday\n'
                '  "no_morning": true or false — avoid early starts (e.g. before 10:00) when the student says so\n'
                '  "compact": true or false — want fewer long gaps or classes clustered, not spread across the week\n'
                '  "no_monday": true or false\n'
                '  "lunch_break": true or false — want a break around lunch (roughly 12:00–14:00) on at least one day\n'
                "}\n"
                "If not mentioned, use false. Output valid JSON only."
            ),
        },
        {"role": "user", "content": user_message},
    ]
    response = client.chat(messages)
    raw = (response.get("content") or "").strip()
    try:
        data = _parse_json_object_from_llm(raw)
        for key in (
            "no_friday",
            "no_morning",
            "compact",
            "no_monday",
            "lunch_break",
        ):
            if key not in data:
                data[key] = False
            else:
                data[key] = bool(data[key])
        return data
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(
            f"extract_schedule_preferences parse failed: {e!s}; raw={repr(raw)[:300]}"
        )
        return {
            "no_friday": False,
            "no_morning": False,
            "compact": False,
            "no_monday": False,
            "lunch_break": False,
        }


def match_schedule_to_time_preferences(
    client, user_message: str, extracted_prefs: dict, schedules: list
) -> dict:
    """
    After preferences are extracted, ask the LLM to pick the single schedule rank
    that best matches those preferences, using full meeting time data.
    """
    if not schedules:
        return {
            "best_rank": 0,
            "explanation": "No schedules to compare.",
        }
    valid_ranks = [s.get("rank") for s in schedules if s.get("rank") is not None]
    sched_payload = []
    for s in (schedules or [])[:20]:
        sched_payload.append(
            {
                "rank": s.get("rank"),
                "total_credits": s.get("total_credits"),
                "ir_score": round(float(s.get("score", 0) or 0), 4),
                "courses": [
                    {
                        "course_id": c.get("course_id"),
                        "title": c.get("title"),
                        "meetings": c.get("meetings", []),
                    }
                    for c in s.get("courses", [])
                ],
            }
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Cornell course scheduling assistant. You receive: (1) the student's message, "
                "(2) boolean scheduling preferences parsed from that message, and (3) candidate "
                "schedules with per-section meeting times. Days use M T W R F (one letter per day); "
                "start/end are 24h HH:MM when present.\n"
                "Choose exactly ONE schedule that best matches the time/layout preferences. Use the IR score "
                "as a minor tie-breaker when two options fit timing equally well.\n"
                "Reply with JSON only, no markdown:\n"
                '{ "best_rank": <integer rank from the input>, '
                '"explanation": "<2-4 sentences; mention specific days or times when useful>" }'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "original_message": user_message,
                    "extracted_preferences": extracted_prefs,
                    "schedules": sched_payload,
                },
                ensure_ascii=False,
            ),
        },
    ]
    response = client.chat(messages)
    raw = (response.get("content") or "").strip()
    try:
        out = _parse_json_object_from_llm(raw)
        br = int(out.get("best_rank", 0))
        expl = (out.get("explanation") or "").strip() or "No explanation returned."
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(
            f"match_schedule_to_time_preferences parse failed: {e!s}; raw={repr(raw)[:300]}"
        )
        br = valid_ranks[0] if valid_ranks else 0
        expl = raw or "The model did not return valid JSON; showing raw text above if any."

    if valid_ranks and br not in valid_ranks:
        nearest = min(valid_ranks, key=lambda r: abs(int(r) - int(br or 0)))
        expl = f"(Adjusted invalid rank to nearest.) {expl}"
        br = nearest

    return {"best_rank": br, "explanation": expl}

def llm_generate_summary(client, user_message, rewritten_query, schedules):
    top_schedules = schedules[:10]
    if not top_schedules:
        return None
    
    prompt_schedules = [
        {
            "rank": s.get("rank"),
            "score": round(s.get("score", 0), 4),
            "courses": [
                {
                    "course_id": c.get("course_id"),
                    "title": c.get("title"),
                    "instructors": c.get("instructors", []),
                }
                for c in s.get("courses", [])
            ],
        }
        for s in top_schedules
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Cornell schedule advisor. "
                "Given the student's original request and the top IR-ranked schedules "
                "(scored by professor review similarity to the rewritten query), "
                "write 2-3 sentences explaining which schedule best matches their "
                "preference and why. Be specific about professors or courses."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "original_query": user_message,
                    "rewritten_ir_query": rewritten_query,
                    "top_schedules": prompt_schedules,
                }
            ),
        },
    ]
    response = client.chat(messages)
    return (response.get("content") or "").strip()


def register_schedule_matcher_route(app):
    """
    POST /api/schedule-matcher
    Body: { "message": "<natural language time/layout prefs>", "schedules": [<same shape as /api/schedules response>] }
    """
    @app.route("/api/schedule-matcher", methods=["POST"])
    def schedule_matcher():
        data = request.get_json() or {}
        user_message = (data.get("message") or "").strip()
        schedules = data.get("schedules") or []
        if not user_message:
            return jsonify({"error": "message is required"}), 400
        if not schedules:
            return jsonify(
                {"error": "schedules is required; generate schedules first, then try again."}
            ), 400
        api_key = os.getenv("SPARK_API_KEY")
        if not api_key:
            return jsonify({"error": "SPARK_API_KEY not set — add it to your .env file"}), 500
        client = LLMClient(api_key=api_key)
        try:
            prefs = extract_schedule_preferences(client, user_message)
            result = match_schedule_to_time_preferences(
                client, user_message, prefs, schedules
            )
        except Exception as e:
            logger.exception("schedule_matcher failed: %s", e)
            return jsonify({"error": str(e)}), 500
        return jsonify(
            {
                "extracted_preferences": prefs,
                "best_rank": result["best_rank"],
                "explanation": result["explanation"],
            }
        )


def register_chat_route(app, json_search):
    """Register the /api/chat SSE endpoint. Called from routes.py."""

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json() or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        api_key = os.getenv("SPARK_API_KEY")
        if not api_key:
            return jsonify({"error": "SPARK_API_KEY not set — add it to your .env file"}), 500

        client = LLMClient(api_key=api_key)

        rewritten_query = llm_rewrite_query(client, user_message)

        schedules = data.get("schedules", [])

        top_schedules = schedules[:10]
        summary = None
        if top_schedules:
            prompt_schedules = [
                {
                    "rank": s.get("rank"),
                    "score": round(s.get("score", 0), 4),
                    "courses": [
                        {
                            "course_id": c.get("course_id"),
                            "title": c.get("title"),
                            "instructors": c.get("instructors", []),
                        }
                        for c in s.get("courses", [])
                    ],
                }
                for s in top_schedules
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a Cornell schedule advisor. "
                        "Given the student's original request and the top IR-ranked schedules "
                        "(scored by professor review similarity to the rewritten query), "
                        "write 2-3 sentences explaining which schedule best matches their "
                        "preference and why. Be specific about professors or courses."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "original_query": user_message,
                            "rewritten_ir_query": rewritten_query,
                            "top_schedules": prompt_schedules,
                        }
                    ),
                },
            ]
            response = client.chat(messages)
            summary = (response.get("content") or "").strip()

        return jsonify(
            {
                "original_query": user_message,
                "rewritten_query": rewritten_query,  # display this in UI as the IR query used
                "summary": summary,
            }
        )

        """
        use_search, search_term = llm_search_decision(client, user_message)

        if use_search:
            episodes = json_search(search_term or "Kardashian")
            context_text = "\n\n---\n\n".join(
                f"Title: {ep['title']}\nDescription: {ep['descr']}\nIMDB Rating: {ep['imdb_rating']}"
                for ep in episodes
            ) or "No matching episodes found."
            messages = [
                {"role": "system", "content": "Answer questions about Keeping Up with the Kardashians using only the episode information provided."},
                {"role": "user", "content": f"Episode information:\n\n{context_text}\n\nUser question: {user_message}"},
            ]
        else:
            messages = [
                {"role": "system", "content": "You are a helpful assistant for Keeping Up with the Kardashians questions."},
                {"role": "user", "content": user_message},
            ]

        def generate():
            if use_search and search_term:
                yield f"data: {json.dumps({'search_term': search_term})}\n\n"
            try:
                for chunk in client.chat(messages, stream=True):
                    if chunk.get("content"):
                        yield f"data: {json.dumps({'content': chunk['content']})}\n\n"
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': 'Streaming error occurred'})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        """
