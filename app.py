import os
import secrets
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


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
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    summary = get_summary_stats(user_id)
    transactions = [_format_transaction(item) for item in get_recent_transactions(user_id)]
    raw_categories = get_category_breakdown(user_id)
    category_breakdown = [_format_category(item) for item in raw_categories]
    category_totals = {item["name"]: item["amount"] for item in raw_categories}
    profile_user = {
        **user,
        "initials": _initials(user["name"]),
    }
    summary_stats = [
        {
            "label": "Total spent",
            "value": _format_currency(summary["total_spent"]),
            "detail": "All recorded expenses",
        },
        {
            "label": "Transactions",
            "value": str(summary["transaction_count"]),
            "detail": "All recorded expenses",
        },
        {
            "label": "Top category",
            "value": summary["top_category"],
            "detail": (
                f"{_format_currency(category_totals[summary['top_category']])} spent"
                if summary["top_category"] != "—"
                else "No expenses yet"
            ),
        },
    ]

    return render_template(
        "profile.html",
        profile_user=profile_user,
        summary_stats=summary_stats,
        transactions=transactions,
        category_breakdown=category_breakdown,
    )


def _format_currency(amount):
    return f"₹{amount:,.2f}"


def _initials(name):
    parts = name.split()
    return "".join(part[0] for part in parts[:2]).upper()


def _category_class(category):
    return category.lower().replace(" ", "-")


def _format_transaction(transaction):
    try:
        transaction_date = datetime.strptime(transaction["date"], "%Y-%m-%d")
        display_date = transaction_date.strftime("%d %b %Y")
    except (TypeError, ValueError):
        display_date = transaction["date"]
    return {
        **transaction,
        "date": display_date,
        "category_class": _category_class(transaction["category"]),
        "amount": _format_currency(transaction["amount"]),
    }


def _format_category(category):
    return {
        "category": category["name"],
        "category_class": _category_class(category["name"]),
        "total": _format_currency(category["amount"]),
        "pct": category["pct"],
        "progress_class": f"profile-progress-{round(category['pct'] / 5) * 5}",
    }


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
