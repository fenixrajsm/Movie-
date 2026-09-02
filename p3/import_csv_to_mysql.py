import csv
import os
import mysql.connector
from db_config import DB_CONFIG

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "movies.csv")

INSERT_SQL = """
    INSERT INTO movies (title, genre, year, director, rating, poster, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    rows_inserted = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute(INSERT_SQL, (
                row["title"],
                row["genre"],
                int(row["year"]),
                row["director"],
                float(row["rating"]),
                row["poster"],
                row.get("description", ""),
            ))
            rows_inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Imported {rows_inserted} movies into '{DB_CONFIG['database']}.movies'")


if __name__ == "__main__":
    main()
