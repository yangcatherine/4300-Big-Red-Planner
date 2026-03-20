import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json

def clean_name(name):
    if not isinstance(name, str):
        return ""
    return name.strip().lower().replace(".", "")

def load_professors(jsonl_path):
    records = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)

            name = record.get("name", "")
            department = record.get("department", "")
            rating = record.get("rating", 0)
            difficulty = record.get("difficulty", 0)
            num_ratings = record.get("num_ratings", 0)

            # Combine review comments into one string
            reviews = []
            for r in record.get("ratings", []):
                comment = r.get("comment", "")
                if comment:
                    reviews.append(comment)

            combined_reviews = " ".join(reviews)

            records.append({
                "Professor": name,
                "Department": department,
                "Rating": float(rating) if rating else 0.0,
                "Difficulty": float(difficulty) if difficulty else 0.0,
                "Num_Ratings": int(num_ratings) if num_ratings else 0,
                "Review_Text": combined_reviews
            })
    df = pd.DataFrame(records)
    df["clean_name"] = df["Professor"].apply(clean_name)

    df["Review_Text"] = df["Review_Text"].fillna("")

    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(df["Review_Text"])

    prof_dict = {
        row["clean_name"]: idx
        for idx, row in df.iterrows()
    }
    return df, prof_dict, vectorizer, tfidf_matrix

def get_course_instructors(course):
    instructors = set()
    for section in course.get("sections", []):
        for inst in section.get("instructors", []):
            if inst:
                instructors.add(inst.lower().strip())
    return list(instructors)

def score_professor(prof_idx, df, query_vec, tfidf_matrix, query):
    if prof_idx is None:
        return None # or put an average? 

    # TF-IDF similarity
    prof_vec = tfidf_matrix[prof_idx]
    sim = cosine_similarity(query_vec, prof_vec)[0][0]

    rating = df.iloc[prof_idx]["Rating"]
    difficulty = df.iloc[prof_idx]["Difficulty"]
    num_ratings = df.iloc[prof_idx]["Num_Ratings"]

    if pd.isna(rating) or num_ratings == 0: 
        return None
    
    rating_score = rating / 5 #if pd.notna(rating) else 0.2
    difficulty_score = difficulty / 5 #if pd.notna(difficulty) else 0.2

    #query_lower = query.lower()

    #confidence = min((num_ratings or 0) / 10, 1)

    final_score = (
        0.5 * sim +
        0.3 * rating_score +
        0.2 * difficulty_score
    )
    #print("sim, rating, difficulty, final score for professor", sim, rating_score, difficulty_score, final_score*confidence)
    #return final_score * confidence
    return final_score

def score_course(course, df, prof_dict, query_vec, tfidf_matrix, query):
    instructors = get_course_instructors(course)

    scores = []

    for inst in instructors:
        prof_idx = prof_dict.get(clean_name(inst))  
        score = score_professor(prof_idx, df, query_vec, tfidf_matrix, query)
        if score is not None: 
            scores.append(score)

    if not scores: #no ratings
        return 0.0
    #print("course score:", sum(scores)/len(scores))
    return sum(scores) / len(scores)

def score_schedule(schedule, df, prof_dict, query_vec, tfidf_matrix, query):
    course_scores = []

    for course in schedule:
        course_scores.append(
            score_course(course, df, prof_dict, query_vec, tfidf_matrix, query)
        )

    return sum(course_scores) / len(course_scores)


def rank_schedules_with_scores(schedules, df, prof_dict, vectorizer, tfidf_matrix, query):
    query_vec = vectorizer.transform([query])
    results = []

    for schedule in schedules:
        score = score_schedule(schedule, df, prof_dict, query_vec, tfidf_matrix, query)
        results.append((score, schedule))

    results.sort(key=lambda x: x[0], reverse=True)
    return results
