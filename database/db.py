from calendar import monthrange
from datetime import date
from pathlib import Path
import sqlite3

from werkzeug.security import generate_password_hash


DATABASE_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"


def get_db():
    """Return a SQLite connection configured for application queries."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    """Create the application tables if they do not already exist."""
    connection = get_db()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def seed_db():
    """Insert the development user and sample expenses once."""
    connection = get_db()
    try:
        existing_user = connection.execute("SELECT id FROM users LIMIT 1").fetchone()
        if existing_user is not None:
            return

        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        today = date.today()
        last_day = monthrange(today.year, today.month)[1]
        sample_days = [min(day, last_day) for day in (1, 3, 5, 7, 9, 11, 13, 15)]
        sample_expenses = [
            (user_id, 850.00, "Food", sample_days[0], "Groceries"),
            (user_id, 320.00, "Transport", sample_days[1], "Ride to work"),
            (user_id, 4500.00, "Bills", sample_days[2], "Electricity bill"),
            (user_id, 1200.00, "Health", sample_days[3], "Pharmacy"),
            (user_id, 1500.00, "Entertainment", sample_days[4], "Movie tickets"),
            (user_id, 2800.00, "Shopping", sample_days[5], "Household items"),
            (user_id, 600.00, "Other", sample_days[6], "Miscellaneous"),
            (user_id, 500.00, "Food", sample_days[7], "Lunch"),
        ]
        connection.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (user_id, amount, category, f"{today.year:04d}-{today.month:02d}-{day:02d}", description)
                for user_id, amount, category, day, description in sample_expenses
            ],
        )
        connection.commit()
    finally:
        connection.close()
