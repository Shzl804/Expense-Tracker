import os
import secrets
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
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


def _subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    last_day = (date(year, month % 12 + 1, 1) - date.resolution).day if month != 12 else 31
    return date(year, month, min(value.day, last_day))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    # A date filter is valid only when both bounds are present and well formed.
    if not date_from or not date_to:
        date_from = date_to = None
    else:
        try:
            parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            date_from = date_to = None
        else:
            if parsed_from > parsed_to:
                flash("Start date must be before end date.")
                date_from = date_to = None

    today = date.today()
    preset_ranges = {
        "this-month": (today.replace(day=1), today),
        "last-3-months": (_subtract_months(today, 3), today),
        "last-6-months": (_subtract_months(today, 6), today),
    }
    active_preset = next(
        (
            name
            for name, (preset_from, preset_to) in preset_ranges.items()
            if date_from == preset_from.isoformat() and date_to == preset_to.isoformat()
        ),
        "all-time" if not date_from and not date_to else None,
    )
    custom_range_active = bool(date_from and date_to and not active_preset)

    summary = get_summary_stats(user_id, date_from, date_to)
    transactions = [_format_transaction(item) for item in get_recent_transactions(user_id, date_from=date_from, date_to=date_to)]
    raw_categories = get_category_breakdown(user_id, date_from, date_to)
    category_breakdown = [_format_category(item) for item in raw_categories]
    category_totals = {item["name"]: item["amount"] for item in raw_categories}
    profile_user = {
        **user,
        "initials": _initials(user["name"]),
    }

    # helper to build detail string
    def _detail_text(date_f, date_t):
        if not date_f and not date_t:
            return "All recorded expenses"
        if date_f and date_t:
            return f"From {date_f} to {date_t}"
        if date_f:
            return f"From {date_f}"
        return f"Until {date_t}"

    detail_text = _detail_text(date_from, date_to)

    summary_stats = [
        {
            "label": "Total spent",
            "value": _format_currency(summary["total_spent"]),
            "detail": detail_text,
        },
        {
            "label": "Transactions",
            "value": str(summary["transaction_count"]),
            "detail": detail_text,
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
        date_from=date_from,
        date_to=date_to,
        active_preset=active_preset,
        custom_range_active=custom_range_active,
        preset_ranges={
            name: (preset_from.isoformat(), preset_to.isoformat())
            for name, (preset_from, preset_to) in preset_ranges.items()
        },
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
