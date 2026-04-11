import csv
import json
import os
from dotenv import load_dotenv
from flask import Flask

load_dotenv()
from flask_cors import CORS
from models import db, Professor
from routes import register_routes

current_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_directory)

app = Flask(__name__,
    static_folder=os.path.join(project_root, 'frontend', 'dist'),
    static_url_path='')
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


def _clean_name(name):
    if not isinstance(name, str):
        return ""
    return name.strip().lower().replace(".", "")


def init_db():
    with app.app_context():
        db.create_all()

        if Professor.query.count() == 0:
            csv_path = os.path.join(project_root, 'data', 'cornell_ratings_data.csv')
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        prof = Professor(
                            name=row.get('Professor') or '',
                            department=row.get('Department') or '',
                            rating=float(row['Rating']) if row.get('Rating') else 0.0,
                            difficulty=float(row['Difficulty']) if row.get('Difficulty') else 0.0,
                            num_ratings=int(row['Num_Ratings']) if row.get('Num_Ratings') else 0,
                            review=row.get('Review_Example') or '',
                        )
                        db.session.add(prof)
                    except (ValueError, TypeError):
                        continue
            db.session.commit()
            print(f"Database initialized with {Professor.query.count()} professors")


def build_tfidf_index():
    """Build TF-IDF matrix and professor name lookup for schedule scoring."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    with app.app_context():
        professors = Professor.query.order_by(Professor.id).all()
        reviews = [p.review or "" for p in professors]
        prof_ids = [p.id for p in professors]

        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(reviews)

        id_to_idx = {pid: idx for idx, pid in enumerate(prof_ids)}

        # Map clean professor names -> DB id for instructor matching
        name_to_id = {}
        for p in professors:
            clean = _clean_name(p.name)
            if clean:
                name_to_id[clean] = p.id

    app.config['TFIDF_VECTORIZER'] = vectorizer
    app.config['TFIDF_MATRIX'] = tfidf_matrix
    app.config['TFIDF_ID_MAP'] = id_to_idx
    app.config['PROF_NAME_MAP'] = name_to_id
    print(f"TF-IDF index built over {len(prof_ids)} professors")


def load_catalog():
    catalog_path = os.path.join(project_root, 'data', 'cornell_FA25_courses.json')
    with open(catalog_path, encoding='utf-8') as f:
        catalog = json.load(f)
    app.config['COURSE_CATALOG'] = catalog

    course_by_id = {c['course_id']: c for c in catalog}
    app.config['COURSE_BY_ID'] = course_by_id
    print(f"Course catalog loaded: {len(catalog)} courses")


init_db()
build_tfidf_index()
load_catalog()
register_routes(app)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)
