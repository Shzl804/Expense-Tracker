from calendar import monthrange
from datetime import date
import re
from urllib.parse import parse_qs, urlparse

import pytest
from flask import url_for

from app import app as flask_app
from database import db
from database.db import init_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )
    init_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Return a client authenticated through the public registration/login flow."""
    registration = client.post(
        "/register",
        data={
            "name": "Filter User",
            "email": "filter@example.com",
            "password": "test-password",
        },
    )
    assert registration.status_code == 302, "Test user registration should succeed"

    login = client.post(
        "/login",
        data={"email": "filter@example.com", "password": "test-password"},
    )
    assert login.status_code == 302, "Test user login should succeed"
    return client


def _user_id():
    connection = db.get_db()
    try:
        row = connection.execute(
            "SELECT id FROM users WHERE email = ?", ("filter@example.com",)
        ).fetchone()
        return row["id"]
    finally:
        connection.close()


def _add_expenses(expenses):
    connection = db.get_db()
    try:
        connection.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(_user_id(), amount, category, expense_date, description)
             for amount, category, expense_date, description in expenses],
        )
        connection.commit()
    finally:
        connection.close()


def _profile_url(app, **query):
    with app.test_request_context():
        return url_for("profile", **query)


def _hrefs_for_text(page, text):
    """Return href values from links whose rendered label contains text."""
    pattern = rf'<a\b[^>]*href="([^"]*)"[^>]*>\s*{re.escape(text)}\s*</a>'
    return [href.replace("&amp;", "&") for href in re.findall(pattern, page)]


def _subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def test_profile_requires_authentication(client, app):
    response = client.get(_profile_url(app))

    assert response.status_code == 302, "Unauthenticated profile access should redirect"
    assert response.headers["Location"].endswith("/login"), "Profile should redirect to login"


def test_profile_without_filter_shows_all_sections_and_all_expenses(auth_client, app):
    _add_expenses(
        [
            (1000, "Food", "2026-01-01", "January groceries"),
            (2500, "Bills", "2026-05-15", "Electricity"),
            (700, "Food", "2026-10-29", "October lunch"),
        ]
    )

    response = auth_client.get(_profile_url(app))
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Unfiltered profile should render successfully"
    assert "Total spent" in page and "Transactions" in page, "Summary stats should render"
    assert "Category breakdown" in page, "Category breakdown should render"
    assert all(description in page for description in ("January groceries", "Electricity", "October lunch"))
    assert "₹4,200.00" in page, "All expenses should be included"


def test_custom_date_range_is_inclusive_across_summary_transactions_and_categories(
    auth_client, app
):
    _add_expenses(
        [
            (100, "Food", "2026-03-01", "Lower boundary"),
            (200, "Bills", "2026-03-15", "Inside range"),
            (300, "Transport", "2026-03-31", "Upper boundary"),
            (400, "Food", "2026-04-01", "Outside range"),
        ]
    )

    response = auth_client.get(
        _profile_url(app, date_from="2026-03-01", date_to="2026-03-31")
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "A valid custom range should render"
    assert all(description in page for description in ("Lower boundary", "Inside range", "Upper boundary"))
    assert "Outside range" not in page, "Expenses after date_to must be excluded"
    assert "₹600.00" in page, "Summary should include only filtered expenses"
    assert "Transport" in page and "Bills" in page, "Filtered categories should be displayed"
    assert 'name="date_from"' in page and 'value="2026-03-01"' in page
    assert 'name="date_to"' in page and 'value="2026-03-31"' in page


def test_profile_filter_does_not_mutate_expense_records(auth_client, app):
    _add_expenses([(125, "Food", "2026-06-10", "Persistent expense")])

    response = auth_client.get(
        _profile_url(app, date_from="2026-06-01", date_to="2026-06-30")
    )
    assert response.status_code == 200, "Filtering should complete without changing data"

    connection = db.get_db()
    try:
        rows = connection.execute(
            "SELECT amount, category, date, description FROM expenses WHERE user_id = ?",
            (_user_id(),),
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1, "Filtering must not create or delete expenses"
    assert rows[0]["description"] == "Persistent expense"


def test_profile_this_month_preset_filters_to_current_calendar_month(auth_client, app):
    today = date.today()
    current_month_start = today.replace(day=1).isoformat()
    _add_expenses(
        [
            (100, "Food", current_month_start, "This month expense"),
            (200, "Bills", today.isoformat(), "Today expense"),
            (300, "Travel", _subtract_months(today, 1), "Previous month expense"),
        ]
    )

    response = auth_client.get(
        _profile_url(app, date_from=current_month_start, date_to=today.isoformat())
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "This month expense" in page and "Today expense" in page
    assert "Previous month expense" not in page


def test_profile_preset_links_use_expected_ranges_and_all_time_is_clean(auth_client, app):
    response = auth_client.get(_profile_url(app))
    page = response.get_data(as_text=True)
    today = date.today()

    expected = {
        "This Month": (today.replace(day=1).isoformat(), today.isoformat()),
        "Last 3 Months": (_subtract_months(today, 3), today.isoformat()),
        "Last 6 Months": (_subtract_months(today, 6), today.isoformat()),
    }
    for label, (start, end) in expected.items():
        hrefs = _hrefs_for_text(page, label)
        assert hrefs, f"{label} preset link should be rendered"
        query = parse_qs(urlparse(hrefs[0]).query)
        assert query == {"date_from": [start], "date_to": [end]}, (
            f"{label} should link to its computed date range"
        )

    all_time_hrefs = _hrefs_for_text(page, "All Time")
    assert all_time_hrefs, "All Time preset link should be rendered"
    assert urlparse(all_time_hrefs[0]).query == "", "All Time should use a clean profile URL"


def test_profile_active_preset_is_highlighted(auth_client, app):
    today = date.today()
    start = today.replace(day=1).isoformat()
    response = auth_client.get(_profile_url(app, date_from=start, date_to=today.isoformat()))
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    this_month_fragment = next(
        fragment for fragment in page.split("<a ")[1:] if ">This Month<" in fragment
    )
    assert "active" in this_month_fragment.lower(), "The active preset should be highlighted"


def test_profile_all_time_preset_removes_active_filter(auth_client, app):
    _add_expenses(
        [
            (100, "Food", "2026-01-01", "Old expense"),
            (200, "Bills", date.today().isoformat(), "Current expense"),
        ]
    )

    response = auth_client.get(_profile_url(app))
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Old expense" in page and "Current expense" in page
    assert "All recorded expenses" in page, "All Time should restore the unfiltered detail"


def test_profile_reversed_range_flashes_error_and_falls_back_to_all_time(auth_client, app):
    _add_expenses([(100, "Food", "2026-01-01", "Earlier expense")])

    response = auth_client.get(
        _profile_url(app, date_from="2026-02-01", date_to="2026-01-01")
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Start date must be before end date." in page, "Reversed ranges should explain the error"
    assert "Earlier expense" in page, "Reversed ranges should fall back to all expenses"


@pytest.mark.parametrize(
    "query",
    [
        {"date_from": "not-a-date", "date_to": "2026-01-31"},
        {"date_from": "2026-01-01", "date_to": "not-a-date"},
        {"date_from": "2026-01-01"},
        {"date_to": "2026-01-31"},
    ],
)
def test_profile_malformed_or_incomplete_dates_fall_back_without_error(
    auth_client, app, query
):
    _add_expenses([(100, "Food", "2026-01-15", "Unfiltered expense")])

    response = auth_client.get(_profile_url(app, **query))
    page = response.get_data(as_text=True)

    assert response.status_code == 200, "Invalid date input must not crash the profile"
    assert "Unfiltered expense" in page, "Invalid or incomplete dates should show all expenses"
    assert "All recorded expenses" in page


def test_profile_empty_selected_range_shows_zero_and_empty_categories(auth_client, app):
    _add_expenses([(100, "Food", "2026-01-15", "Existing expense")])

    response = auth_client.get(
        _profile_url(app, date_from="2026-02-01", date_to="2026-02-28")
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹0.00" in page, "Empty ranges should show zero spending"
    assert "Existing expense" not in page
    assert "Food" not in page, "Empty ranges should have no category breakdown"
    assert "No expenses yet" in page, "Empty ranges should have no top category"


def test_profile_amounts_keep_rupee_symbol_when_filter_is_active(auth_client, app):
    _add_expenses([(1234.5, "Food", "2026-07-04", "Filtered amount")])

    response = auth_client.get(
        _profile_url(app, date_from="2026-07-01", date_to="2026-07-31")
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹1,234.50" in page, (
        "Filtered monetary values should retain the rupee symbol"
    )
