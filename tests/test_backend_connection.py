from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import database.db as db
from app import app
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


@pytest.fixture
def database_path(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    db.init_db()
    return db.DATABASE_PATH


@pytest.fixture
def users(database_path):
    connection = db.get_db()
    try:
        primary_user = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 09:30:00"),
        )
        empty_user = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("Empty User", "empty@spendly.com", generate_password_hash("empty123"), "2026-02-01 09:30:00"),
        )
        other_user = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("Other User", "other@spendly.com", generate_password_hash("other123"), "2026-03-01 09:30:00"),
        )
        connection.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (primary_user.lastrowid, 100.00, "Food", "2026-01-01", "Groceries"),
                (primary_user.lastrowid, 50.00, "Food", "2026-01-10", "Lunch"),
                (primary_user.lastrowid, 120.00, "Bills", "2026-01-15", "Electricity bill"),
                (primary_user.lastrowid, 30.00, "Transport", "2026-01-20", "Ride to work"),
                (other_user.lastrowid, 999.00, "Other", "2026-01-25", "Private expense"),
            ],
        )
        connection.commit()
        return {
            "primary": primary_user.lastrowid,
            "empty": empty_user.lastrowid,
            "other": other_user.lastrowid,
        }
    finally:
        connection.close()


@pytest.fixture
def client(database_path):
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with app.test_client() as test_client:
        yield test_client


def test_get_user_by_id_returns_public_profile_details(users):
    assert get_user_by_id(users["primary"]) == {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "member_since": "January 2026",
    }


def test_get_user_by_id_returns_none_for_unknown_user(users):
    assert get_user_by_id(9999) is None


def test_get_summary_stats_returns_user_scoped_totals(users):
    assert get_summary_stats(users["primary"]) == {
        "total_spent": 300.0,
        "transaction_count": 4,
        "top_category": "Food",
    }


def test_get_summary_stats_returns_empty_values_for_user_without_expenses(users):
    assert get_summary_stats(users["empty"]) == {
        "total_spent": 0.0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_get_recent_transactions_orders_newest_first_and_limits_results(users):
    transactions = get_recent_transactions(users["primary"], limit=2)

    assert [item["date"] for item in transactions] == ["2026-01-20", "2026-01-15"]
    assert transactions[0] == {
        "date": "2026-01-20",
        "description": "Ride to work",
        "category": "Transport",
        "amount": 30.0,
    }


def test_get_recent_transactions_returns_empty_list_for_user_without_expenses(users):
    assert get_recent_transactions(users["empty"]) == []


def test_get_category_breakdown_orders_totals_and_percentages_sum_to_100(users):
    breakdown = get_category_breakdown(users["primary"])

    assert [item["name"] for item in breakdown] == ["Food", "Bills", "Transport"]
    assert [item["amount"] for item in breakdown] == [150.0, 120.0, 30.0]
    assert all(isinstance(item["pct"], int) for item in breakdown)
    assert sum(item["pct"] for item in breakdown) == 100


def test_get_category_breakdown_returns_empty_list_for_user_without_expenses(users):
    assert get_category_breakdown(users["empty"]) == []


def test_profile_redirects_anonymous_visitors_to_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_renders_live_user_data(client, users):
    with client.session_transaction() as session:
        session["user_id"] = users["primary"]
        session["user_name"] = "Demo User"

    response = client.get("/profile")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo User" in page
    assert "demo@spendly.com" in page
    assert "January 2026" in page
    assert "₹300.00" in page
    assert "Food" in page
    assert page.index("20 Jan 2026") < page.index("15 Jan 2026")
    assert "Private expense" not in page


def test_profile_renders_zero_safe_empty_state(client, users):
    with client.session_transaction() as session:
        session["user_id"] = users["empty"]
        session["user_name"] = "Empty User"

    response = client.get("/profile")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹0.00" in page
    assert "No expenses recorded yet." in page
    assert "Add an expense to see your category breakdown." in page
