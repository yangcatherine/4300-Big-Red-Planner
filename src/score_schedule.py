import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json
import os

def clean_name(name):
    if not isinstance(name, str):
        return ""
    return name.strip().lower().replace(".", "")

def load_professors(data_path):
    records = []

    is_csv = data_path.lower().endswith(".csv")
    if is_csv:
        csv_df = pd.read_csv(data_path)
        for _, row in csv_df.iterrows():
            name = row.get("Professor", "")
            department = row.get("Department", "")
            rating = row.get("Rating", 0)
            difficulty = row.get("Difficulty", 0)
            num_ratings = row.get("Num_Ratings", 0)
            review_text = row.get("Review_Text", row.get("Review_Example", ""))
            records.append({
                "Professor": str(name) if pd.notna(name) else "",
                "Department": str(department) if pd.notna(department) else "",
                "Rating": float(rating) if pd.notna(rating) else 0.0,
                "Difficulty": float(difficulty) if pd.notna(difficulty) else 0.0,
                "Num_Ratings": int(num_ratings) if pd.notna(num_ratings) else 0,
                "Review_Text": str(review_text) if pd.notna(review_text) else "",
            })
    else:
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)

                name = record.get("name", "")
                department = record.get("department", "")
                rating = record.get("rating", 0)
                difficulty = record.get("difficulty", 0)
                num_ratings = record.get("num_ratings", 0)

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
    if df.empty:
        raise ValueError(f"No professor records found in {data_path}")

    df["clean_name"] = df["Professor"].apply(clean_name)

    df["Review_Text"] = df["Review_Text"].fillna("")
    if (df["Review_Text"].str.strip() == "").all():
        # Avoid empty TF-IDF vocabulary by providing minimal text.
        df["Review_Text"] = df["Professor"].fillna("").astype(str)

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
