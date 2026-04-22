"""Tests for no-review default scoring in routes."""

import sys

sys.path.insert(0, "src")

from routes import (
    _MID,
    _level_diff,
    _no_review_defaults,
    _score_schedule_with_breakdown,
)


def _approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def test_level_diff():
    assert _approx_equal(_level_diff("CS 1110"), 2.0 / 5.0)
    assert _approx_equal(_level_diff("MATH 2210"), 2.5 / 5.0)
    assert _approx_equal(_level_diff("INFO 3300"), 3.0 / 5.0)
    assert _approx_equal(_level_diff("AEP 4440"), 4.0 / 5.0)
    assert _approx_equal(_level_diff("CS 5110"), 4.5 / 5.0)

    # Unknown/malformed course IDs should use middle default.
    assert _approx_equal(_level_diff("BAD"), _MID)
    assert _approx_equal(_level_diff("PE"), _MID)


def test_no_review_defaults():
    weights = {"similarity": 0.5, "rating": 0.3, "difficulty": 0.2}
    sim, rating, difficulty, score = _no_review_defaults(
        {"course_id": "CS 5110"},
        weights,
    )

    assert _approx_equal(sim, _MID)
    assert _approx_equal(rating, _MID)
    assert _approx_equal(difficulty, 4.5 / 5.0)
    expected_score = 0.5 * _MID + 0.3 * _MID + 0.2 * (4.5 / 5.0)
    assert _approx_equal(score, expected_score)


def test_schedule_defaults_no_reviews():
    schedule_courses = [
        {"course_id": "CS 1110", "title": "Intro", "instructors": []},
        {"course_id": "CS 4110", "title": "PL", "instructors": []},
    ]
    weights = {"similarity": 0.5, "rating": 0.3, "difficulty": 0.2}

    score, breakdown = _score_schedule_with_breakdown(
        schedule_courses=schedule_courses,
        df=None,
        prof_dict={},
        tfidf_matrix=None,
        query_vec=None,
        weights=weights,
        use_svd=False,
        svd_data=None,
        query_latent=None,
    )

    expected_course1 = 0.5 * _MID + 0.3 * _MID + 0.2 * (2.0 / 5.0)
    expected_course2 = 0.5 * _MID + 0.3 * _MID + 0.2 * (4.0 / 5.0)
    expected_schedule = (expected_course1 + expected_course2) / 2.0

    assert _approx_equal(score, expected_schedule)
    assert _approx_equal(breakdown["components"]["similarity"], _MID)
    assert _approx_equal(breakdown["components"]["rating"], _MID)
    assert _approx_equal(
        breakdown["components"]["difficulty"], ((2.0 / 5.0) + (4.0 / 5.0)) / 2.0
    )
    assert len(breakdown["course_breakdown"]) == 2
    assert breakdown["course_breakdown"][0]["matched_professors"] == 0
    assert breakdown["course_breakdown"][1]["matched_professors"] == 0


if __name__ == "__main__":
    test_level_diff()
    test_no_review_defaults()
    test_schedule_defaults_no_reviews()
    print("All default scoring tests passed.")
