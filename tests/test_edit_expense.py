import pytest

import database.db as db
from app import app as flask_app
from database.queries import get_expense_by_id, update_expense
from flask import url_for


EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Provide a fresh SQLite database for every edit-expense test."""
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )
    db.init_db()
    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def expenses(app):
    """Create an owner, another user, and one expense for each user."""
    connection = db.get_db()
    try:
        owner = connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Expense Owner", "owner@example.com", "password-hash"),
        )
        other = connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other User", "other@example.com", "password-hash"),
        )
        owner_expense = connection.execute(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (owner.lastrowid, 45.50, "Food", "2026-04-10", "Original lunch"),
        )
        other_expense = connection.execute(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (other.lastrowid, 90.00, "Bills", "2026-04-11", "Other user's bill"),
        )
        connection.commit()
        return {
            "owner": owner.lastrowid,
            "other": other.lastrowid,
            "owner_expense": owner_expense.lastrowid,
            "other_expense": other_expense.lastrowid,
        }
    finally:
        connection.close()


@pytest.fixture
def auth_client(client, expenses):
    with client.session_transaction() as session:
        session["user_id"] = expenses["owner"]
        session["user_name"] = "Expense Owner"
    return client


def _row(expense_id):
    connection = db.get_db()
    try:
        return connection.execute(
            "SELECT id, user_id, amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
    finally:
        connection.close()


def _edit_url(expense_id):
    return url_for("edit_expense", id=expense_id)


def test_get_expense_by_id_returns_owned_expense_as_dict(expenses):
    expense = get_expense_by_id(expenses["owner_expense"], expenses["owner"])

    assert expense == {
        "id": expenses["owner_expense"],
        "user_id": expenses["owner"],
        "amount": 45.5,
        "category": "Food",
        "date": "2026-04-10",
        "description": "Original lunch",
    }, "The query helper should return all fields for an owned expense"


@pytest.mark.parametrize("expense_key,user_key", [("other_expense", "owner"), ("owner_expense", "other")])
def test_get_expense_by_id_returns_none_for_expense_not_owned_by_user(expenses, expense_key, user_key):
    assert get_expense_by_id(expenses[expense_key], expenses[user_key]) is None, (
        "An expense lookup must be scoped to the requesting user"
    )


def test_get_expense_by_id_returns_none_for_nonexistent_expense(expenses):
    assert get_expense_by_id(999999, expenses["owner"]) is None, (
        "A missing expense should not produce a database row"
    )


def test_update_expense_changes_owned_row(expenses):
    update_expense(
        expenses["owner_expense"],
        expenses["owner"],
        99.0,
        "Transport",
        "2026-05-01",
        "Updated commute",
    )

    row = _row(expenses["owner_expense"])
    assert dict(row) == {
        "id": expenses["owner_expense"],
        "user_id": expenses["owner"],
        "amount": 99.0,
        "category": "Transport",
        "date": "2026-05-01",
        "description": "Updated commute",
    }, "Updating an owned expense should replace its editable values"


def test_update_expense_does_not_change_row_for_wrong_user(expenses):
    update_expense(
        expenses["owner_expense"], expenses["other"], 999.0, "Other", "2026-06-01", "Unauthorized"
    )

    row = _row(expenses["owner_expense"])
    assert row["amount"] == 45.5 and row["category"] == "Food", (
        "An update from a different user must affect zero rows"
    )


@pytest.mark.parametrize("method", ["get", "post"])
def test_edit_expense_redirects_anonymous_user_to_login(client, expenses, method):
    request = getattr(client, method)
    response = request(_edit_url(expenses["owner_expense"]), data={} if method == "post" else None)

    assert response.status_code == 302, "Unauthenticated edit requests should redirect"
    assert response.headers["Location"].endswith(url_for("login")), "Redirect should target login"


def test_get_edit_expense_prefills_owned_expense(auth_client, expenses):
    response = auth_client.get(_edit_url(expenses["owner_expense"]))
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "An owner should receive the edit form"
    assert 'method="POST"' in page, "The edit form should submit with POST"
    assert f'action="{_edit_url(expenses["owner_expense"])}"' in page, "Form action should identify the expense"
    assert 'value="45.5"' in page, "The current amount should be pre-filled"
    assert 'value="2026-04-10"' in page, "The current date should be pre-filled"
    assert "Original lunch" in page, "The current description should be pre-filled"
    assert 'value="Food"' in page and "selected" in page, "The current category should be selected"


@pytest.mark.parametrize("expense_key", ["other_expense"])
def test_edit_expense_returns_404_for_foreign_expense(auth_client, expenses, expense_key):
    response = auth_client.get(_edit_url(expenses[expense_key]))

    assert response.status_code == 404, "Users must not view another user's edit form"


def test_edit_expense_returns_404_for_nonexistent_expense(auth_client):
    response = auth_client.get(_edit_url(999999))

    assert response.status_code == 404, "A missing expense should return not found"


def test_post_edit_expense_returns_404_for_foreign_expense(auth_client, expenses):
    response = auth_client.post(
        _edit_url(expenses["other_expense"]),
        data={"amount": "10", "category": "Food", "date": "2026-05-01", "description": "Nope"},
    )

    assert response.status_code == 404, "Users must not update another user's expense"
    assert _row(expenses["other_expense"])["amount"] == 90.0, "Foreign rows must remain unchanged"


def test_post_edit_expense_updates_valid_data_and_redirects_to_profile(auth_client, expenses):
    response = auth_client.post(
        _edit_url(expenses["owner_expense"]),
        data={
            "amount": "125.75",
            "category": "Shopping",
            "date": "2026-05-02",
            "description": "Updated groceries",
        },
    )

    assert response.status_code == 302, "Valid edit data should redirect"
    assert response.headers["Location"].endswith(url_for("profile")), "Success should return to profile"
    row = _row(expenses["owner_expense"])
    assert row["amount"] == 125.75 and row["category"] == "Shopping"
    assert row["date"] == "2026-05-02" and row["description"] == "Updated groceries"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", ""),
        ("amount", "0"),
        ("amount", "not-a-number"),
        ("category", "Invalid"),
        ("date", "not-a-date"),
    ],
)
def test_post_edit_expense_validation_rerenders_and_preserves_submitted_values(
    auth_client, expenses, field, value
):
    submitted = {
        "amount": "12.50",
        "category": "Transport",
        "date": "2026-06-15",
        "description": "Submitted replacement",
    }
    submitted[field] = value

    response = auth_client.post(_edit_url(expenses["owner_expense"]), data=submitted)
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Invalid edit data should re-render the form"
    assert "error" in page.lower(), "The response should explain the validation failure"
    assert "Submitted replacement" in page, "Submitted description should be retained"
    if field != "date":
        assert "2026-06-15" in page, "Submitted date should be retained"
    if field == "amount" and value:
        assert value in page, "Submitted invalid amount should be retained"
    elif field == "date":
        assert value in page, "Submitted invalid date should be retained"
    elif field == "category":
        assert 'name="category"' in page, "The category field should remain available"
    row = _row(expenses["owner_expense"])
    assert row["amount"] == 45.5 and row["description"] == "Original lunch", (
        "Validation failure must not update the existing row"
    )


def test_post_edit_expense_with_blank_description_stores_null(auth_client, expenses):
    response = auth_client.post(
        _edit_url(expenses["owner_expense"]),
        data={
            "amount": "80.00",
            "category": "Bills",
            "date": "2026-07-01",
            "description": "   ",
        },
    )

    assert response.status_code == 302, "A blank optional description should be accepted"
    assert _row(expenses["owner_expense"])["description"] is None, (
        "Whitespace-only descriptions should be stored as SQL NULL"
    )
