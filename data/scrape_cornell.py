import ratemyprofessor
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

school_id = 298 
school = ratemyprofessor.School(school_id)

print(f"Scraping data for Cornell University...")

professors = ratemyprofessor.get_professors_by_school_and_name(school, "")
data = []
count = 0
for prof in professors:
    if count >= 150:
        break

    if prof.num_ratings > 0:
        data.append(
            {
                "Professor": prof.name,
                "Department": prof.department,
                "Rating": prof.rating,
                "Difficulty": prof.difficulty,
                "Num_Ratings": prof.num_ratings,
                "Would_Take_Again": prof.would_take_again,
            }
        )
        count += 1
        print(f"Collected: {prof.name}")

df = pd.DataFrame(data)
df.to_csv("cornell_rmp_sample.csv", index=False)
print("CSV File Created: cornell_rmp_sample.csv")

plt.figure(figsize=(10, 6))
sns.histplot(df["Rating"], bins=10, kde=True, color="skyblue")
plt.title("Distribution of Cornell Professor Ratings")
plt.xlabel("Rating (1-5)")
plt.ylabel("Frequency")
plt.savefig("rating_distribution.png")

plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x="Difficulty", y="Rating", hue="Department", legend=False)
plt.title("Course Difficulty vs. Professor Quality")
plt.xlabel("Difficulty (1-5)")
plt.ylabel("Overall Rating (1-5)")
plt.savefig("difficulty_vs_rating.png")

print("Plots Created: rating_distribution.png and difficulty_vs_rating.png")
