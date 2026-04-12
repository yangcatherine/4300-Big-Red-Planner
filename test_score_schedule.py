import json
import sys

sys.path.insert(0, "src")

from schedule_generator import generate_schedules
from score_schedule import rank_schedules_with_scores, get_course_instructors, load_professors

if __name__ == "__main__":
    #PROFESSOR_CSV = "cornell_rmp_sample.csv"

    # Load professor TF-IDF and dictionary
    df, prof_dict, vectorizer, tfidf_matrix = load_professors("data/ratings.jsonl")

    # Example query
    query = "super easy and fun and chill"

    # Load course catalog
    with open("data/cornell_FA25_courses.json") as f:
        catalog = json.load(f)

    # Example required courses
    required = [c for c in catalog if c["course_id"] in ["CS 1110", "CS 2800"]]

    # Generate schedules
    schedules = generate_schedules(
        required,
        ["ALC", "BIO", "ETM"],
        catalog=catalog,
        excluded_courses=[],
    )

    # Rank schedules based on professor reviews and query
    ranked_with_scores = rank_schedules_with_scores(
        schedules, df, prof_dict, vectorizer, tfidf_matrix, query
    )

    # Print top 20 schedules
    print("Top 20 schedules:")
    for i, (score, sched) in enumerate(ranked_with_scores[:20], 1):
        print(f"\nRank {i} - Score: {score:.3f}")
        for course in sched:
            course_id = course.get("course_id", "Unknown")
            instructors = ", ".join(get_course_instructors(course))
            print(f"  {course_id} - Instructors: {instructors}")