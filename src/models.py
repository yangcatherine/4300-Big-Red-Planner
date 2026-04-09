from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Professor(db.Model):
    __tablename__ = 'professors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    department = db.Column(db.String(128), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    difficulty = db.Column(db.Float, nullable=False)
    num_ratings = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'Professor {self.id}: {self.name}'
