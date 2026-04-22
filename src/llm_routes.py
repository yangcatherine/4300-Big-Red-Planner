"""
LLM chat route — only loaded when USE_LLM = True in routes.py.
Adds a POST /api/chat endpoint that performs LLM-driven RAG.

Setup:
  1. Add API_KEY=your_key to .env
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


"""
def extract_schedule_preferences(client, user_message):
    messages = [
        {
            "role": "system",
            "content": (
                "You extract scheduling preferences from a student's message.\n"
                "Return JSON ONLY with this schema:\n"
                "{\n"
                "  \"no_friday\": true/false,\n"
                "  \"no_morning\": true/false,\n"
                "  \"compact\": true/false,\n"
                "  \"no_monday\": true/false,\n"
                "  \"lunch_break\": true/false\n"
                "}\n"
                "Do NOT explain."
            )
        },
        {"role": "user", "content": user_message}
    ]

    response = client.chat(messages)
    try:
        return json.loads(response.get("content", "{}"))
    except:
        return {}
"""


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
            return jsonify({"error": "API_KEY not set — add it to your .env file"}), 500

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
