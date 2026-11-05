import pytest

import database.db as db
from app import app
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
def database_path(tmp_path, monkeypatch):
    """Give each test a fresh SQLite database."""
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    db.init_db()
    return db.DATABASE_PATH


@pytest.fixture
def client(database_path):
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user(database_path):
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
def auth_client(client, user):
    """A test client with a valid logged-in user session."""
    with client.session_transaction() as session:
        session["user_id"] = user
        session["user_name"] = "Expense User"
    return client


def _expense_rows(user_id):
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


def test_insert_expense_inserts_valid_expense(user):
    insert_expense(user, 50.0, "Food", "2026-03-20", "Lunch")

    rows = _expense_rows(user)
    assert len(rows) == 1, "Expected one inserted expense"
    assert dict(rows[0]) == {
        "user_id": user,
        "amount": 50.0,
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }, "Inserted expense should contain all supplied values"


def test_insert_expense_stores_none_description_as_null(user):
    insert_expense(user, 50.0, "Food", "2026-03-20", None)

    rows = _expense_rows(user)
    assert len(rows) == 1, "Expected one inserted expense"
    assert rows[0]["description"] is None, "A missing description must be stored as SQL NULL"


def test_get_add_expense_redirects_anonymous_visitor_to_login(client):
    response = client.get("/expenses/add")

    assert response.status_code == 302, "Unauthenticated users should be redirected"
    assert response.headers["Location"].endswith("/login"), "Redirect should target the login page"


def test_post_add_expense_redirects_anonymous_visitor_to_login(client):
    response = client.post(
        "/expenses/add",
        data={"amount": "50.00", "category": "Food", "date": "2026-03-20"},
    )

    assert response.status_code == 302, "Unauthenticated POST requests should be redirected"
    assert response.headers["Location"].endswith("/login"), "Redirect should target the login page"


def test_get_add_expense_renders_form_with_all_categories(auth_client):
    response = auth_client.get("/expenses/add")
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Authenticated users should see the add-expense form"
    assert '<form method="POST"' in page or '<form method="post"' in page, "Form must submit with POST"
    assert 'name="amount"' in page, "Form should contain an amount field"
    assert 'name="date"' in page, "Form should contain a date field"
    assert 'name="description"' in page, "Form should contain an optional description field"
    assert all(f">{category}<" in page for category in EXPENSE_CATEGORIES), (
        "Category select should contain every fixed category"
    )


def test_post_add_expense_inserts_valid_data_and_redirects_to_profile(auth_client, user):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        },
    )

    assert response.status_code == 302, "Valid expense submission should redirect"
    assert response.headers["Location"].endswith("/profile"), "Successful save should return to profile"
    rows = _expense_rows(user)
    assert len(rows) == 1, "Valid submission should create one database row"
    assert rows[0]["amount"] == 50.0
    assert rows[0]["category"] == "Food"
    assert rows[0]["date"] == "2026-03-20"
    assert rows[0]["description"] == "Lunch"


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("amount", "", "amount"),
        ("amount", "0", "amount"),
        ("amount", "-5", "amount"),
        ("amount", "not-a-number", "amount"),
        ("category", "Invalid", "category"),
        ("date", "not-a-date", "date"),
    ],
)
def test_post_add_expense_validation_failure_rerenders_error_and_preserves_values(
    auth_client, user, field, value, expected_error
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

    assert response.status_code == 200, "Invalid expense data should re-render the form"
    assert "error" in page.lower() or expected_error in page.lower(), "Response should show a validation error"
    if field == "amount":
        if value:
            assert value in page, "Previously submitted amount should be retained"
    else:
        assert "12.50" in page, "Previously submitted amount should be retained"

    if field != "category":
        assert value in page or (field == "amount" and value == ""), (
            "Previously submitted field value should be retained"
        )
    else:
        assert 'name="category"' in page, "Category field should remain available after validation"
    assert "Dinner" in page, "Previously submitted description should be retained"
    assert not _expense_rows(user), "Invalid data must not create an expense"


def test_post_add_expense_rejects_overlong_description(auth_client, user):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "x" * 201,
        },
    )

    assert response.status_code == 200
    assert "200 characters or fewer" in response.get_data(as_text=True)
    assert not _expense_rows(user)


def test_post_add_expense_without_description_saves_null_description(auth_client, user):
    response = auth_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "   ",
        },
    )

    assert response.status_code == 302, "Description is optional and should not cause validation failure"
    assert response.headers["Location"].endswith("/profile"), "Successful save should return to profile"
    rows = _expense_rows(user)
    assert len(rows) == 1, "Submission without a description should still insert an expense"
    assert rows[0]["description"] is None, "Blank descriptions should be stored as SQL NULL"
