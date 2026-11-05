from datetime import date

import pytest

import database.db as db
from app import app as flask_app
from database.queries import insert_expense


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
    """Provide an isolated application database for each test."""
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )
    db.init_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id(app):
    connection = db.get_db()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            ("Expense User", "expense@example.com", "test-password-hash"),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


@pytest.fixture
def auth_client(client, user_id):
    """Return a client with a valid authenticated session."""
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["user_name"] = "Expense User"
    return client


def expense_rows(user_id):
    connection = db.get_db()
    try:
        return connection.execute(
            """
            SELECT user_id, amount, category, date, description
            FROM expenses
            WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    finally:
        connection.close()


def test_insert_expense_persists_all_supplied_values(user_id):
    insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

    rows = expense_rows(user_id)
    assert len(rows) == 1, "A valid expense should create one database row"
    assert dict(rows[0]) == {
        "user_id": user_id,
        "amount": 50.0,
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }, "The inserted row should preserve every supplied expense value"


def test_insert_expense_stores_missing_description_as_null(user_id):
    insert_expense(user_id, 50.0, "Food", "2026-03-20", None)

    rows = expense_rows(user_id)
    assert len(rows) == 1, "An expense without a description should still be inserted"
    assert rows[0]["description"] is None, "A missing description should be SQL NULL"


def test_get_add_expense_redirects_unauthenticated_user_to_login(client):
    response = client.get("/expenses/add")

    assert response.status_code == 302, "Unauthenticated GET requests should redirect"
    assert response.headers["Location"].endswith("/login"), "GET should redirect to login"


def test_post_add_expense_redirects_unauthenticated_user_to_login(client):
    response = client.post(
        "/expenses/add",
        data={"amount": "50.00", "category": "Food", "date": "2026-03-20"},
    )

    assert response.status_code == 302, "Unauthenticated POST requests should redirect"
    assert response.headers["Location"].endswith("/login"), "POST should redirect to login"


def test_get_add_expense_renders_form_with_fixed_categories_and_default_date(auth_client):
    response = auth_client.get("/expenses/add")
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Authenticated users should receive the add form"
    assert '<form method="POST"' in page, "The expense form should submit with POST"
    assert 'action="/expenses/add"' in page, "The form should submit to the add-expense route"
    assert 'name="amount"' in page, "The form should contain an amount field"
    assert 'name="date"' in page, "The form should contain a date field"
    assert 'name="description"' in page, "The form should contain a description field"
    assert f'value="{date.today().isoformat()}"' in page, "Date should default to today"
    for category in EXPENSE_CATEGORIES:
        assert f">{category}<" in page, f"The category list should include {category}"


def test_authenticated_navigation_exposes_add_expense_link(auth_client):
    response = auth_client.get("/profile")
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "An authenticated user should be able to view the profile"
    assert 'href="/expenses/add"' in page, "The profile should link to add expense"
    assert page.count('href="/expenses/add"') >= 1, "Navigation should expose an add-expense link"


def test_post_add_expense_saves_valid_data_and_redirects_to_profile(auth_client, user_id):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        },
    )

    assert response.status_code == 302, "Valid expense data should redirect after saving"
    assert response.headers["Location"].endswith("/profile"), "Success should redirect to profile"
    rows = expense_rows(user_id)
    assert len(rows) == 1, "A valid submission should create one expense"
    assert dict(rows[0]) == {
        "user_id": user_id,
        "amount": 50.0,
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }, "The database row should contain the submitted expense"


def test_post_add_expense_without_description_saves_null(auth_client, user_id):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "   ",
        },
    )

    assert response.status_code == 302, "A blank optional description should be accepted"
    assert response.headers["Location"].endswith("/profile"), "Successful save should redirect"
    rows = expense_rows(user_id)
    assert len(rows) == 1, "The expense should be inserted without a description"
    assert rows[0]["description"] is None, "Whitespace-only descriptions should become NULL"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", ""),
        ("amount", "0"),
        ("amount", "not-a-number"),
        ("category", "Invalid"),
        ("category", "Food'); DROP TABLE expenses; --"),
        ("date", "not-a-date"),
        ("date", "2026-02-30"),
    ],
)
def test_post_add_expense_invalid_value_rerenders_form_without_inserting(
    auth_client, user_id, field, value
):
    submitted = {
        "amount": "12.50",
        "category": "Food",
        "date": "2026-03-20",
        "description": "Dinner",
    }
    submitted[field] = value

    response = auth_client.post("/expenses/add", data=submitted)
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Invalid data should re-render the form"
    assert "error" in page.lower(), "The form should display a validation error"
    assert "Dinner" in page, "Previously submitted description should be retained"
    if field != "amount":
        assert "12.50" in page, "Previously submitted amount should be retained"
    elif value:
        assert value in page, "Previously submitted invalid amount should be retained"
    assert not expense_rows(user_id), "Invalid submissions must not create database rows"


def test_post_add_expense_rejects_description_longer_than_200_characters(auth_client, user_id):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "x" * 201,
        },
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "An overlong description should re-render the form"
    assert "200 characters or fewer" in page, "The response should explain the length violation"
    assert not expense_rows(user_id), "An invalid description must not be persisted"
