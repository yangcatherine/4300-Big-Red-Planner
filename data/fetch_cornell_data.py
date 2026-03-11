import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

input_file = "ratings.jsonl"
output_file = "cornell_rmp_sample.csv"


def main():
    data = []
    print("Reading Kaggle Cornell ratings data...")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx >= 500:
                    break

                record = json.loads(line)

                comment = "No text provided."
                if record.get("ratings") and len(record["ratings"]) > 0:
                    comment = record["ratings"][0].get("comment", comment)

                data.append(
                    {
                        "Professor": record.get("name", "Unknown"),
                        "Department": record.get("department", "Unknown"),
                        "Rating": float(record.get("rating", 0.0)),
                        "Difficulty": float(record.get("difficulty", 0.0)),
                        "Num_Ratings": int(record.get("num_ratings", 0)),
                        "Review_Example": comment,
                    }
                )

        df = pd.DataFrame(data)
        df = df[df["Num_Ratings"] > 0]

        df.to_csv(output_file, index=False)

        # 2. Rating distribution plot
        plt.figure(figsize=(10, 6))
        sns.histplot(df["Rating"], bins=10, color="#B31B1B", kde=True)
        plt.title("Cornell University: Distribution of Professor Ratings")
        plt.xlabel("Overall Quality Rating (1-5)")
        plt.savefig("rating_distribution.png")

        # Difficulty vs quality plot
        plt.figure(figsize=(10, 6))
        sns.scatterplot(data=df, x="Difficulty", y="Rating", alpha=0.6, color="#B31B1B")
        plt.title("Cornell: Course Difficulty vs. Quality Rating")
        plt.savefig("difficulty_vs_rating.png")

    except Exception as e:
        print(f"Error processing the file: {e}")


if __name__ == "__main__":
    main()
