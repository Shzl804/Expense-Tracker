import os
import secrets
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db


app = Flask(__name__)
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", secrets.token_hex(32))


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or len(password) < 8:
        return render_template(
            "register.html",
            error="Enter your name, a valid email, and a password of at least 8 characters.",
            name=name,
            email=email,
        )

    connection = get_db()
    try:
        connection.execute(
            """
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (name, email, generate_password_hash(password)),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="An account with that email already exists.",
            name=name,
            email=email,
        )
    finally:
        connection.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("landing"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    connection = get_db()
    try:
        user = connection.execute(
            """
            SELECT id, name, password_hash
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
    finally:
        connection.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email or password.",
            email=email,
        )

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    profile_user = {
        "initials": "DU",
        "name": "Demo User",
        "email": "demo@spendly.com",
        "member_since": "January 2026",
    }
    summary_stats = [
        {"label": "Total spent", "value": "PKR 18,240", "detail": "This month"},
        {"label": "Transactions", "value": "34", "detail": "This month"},
        {"label": "Top category", "value": "Food", "detail": "PKR 6,850 spent"},
    ]
    transactions = [
        {
            "date": "15 Jan 2026",
            "description": "Weekly groceries",
            "category": "Food",
            "category_class": "food",
            "amount": "PKR 2,450",
        },
        {
            "date": "13 Jan 2026",
            "description": "Electricity bill",
            "category": "Bills",
            "category_class": "bills",
            "amount": "PKR 4,500",
        },
        {
            "date": "11 Jan 2026",
            "description": "Ride to work",
            "category": "Transport",
            "category_class": "transport",
            "amount": "PKR 320",
        },
        {
            "date": "09 Jan 2026",
            "description": "Movie tickets",
            "category": "Entertainment",
            "category_class": "entertainment",
            "amount": "PKR 1,500",
        },
    ]
    category_breakdown = [
        {
            "category": "Food",
            "category_class": "food",
            "total": "PKR 6,850",
            "progress_class": "profile-progress-100",
        },
        {
            "category": "Bills",
            "category_class": "bills",
            "total": "PKR 4,500",
            "progress_class": "profile-progress-66",
        },
        {
            "category": "Shopping",
            "category_class": "shopping",
            "total": "PKR 2,800",
            "progress_class": "profile-progress-41",
        },
        {
            "category": "Entertainment",
            "category_class": "entertainment",
            "total": "PKR 1,500",
            "progress_class": "profile-progress-22",
        },
    ]

    return render_template(
        "profile.html",
        profile_user=profile_user,
        summary_stats=summary_stats,
        transactions=transactions,
        category_breakdown=category_breakdown,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
