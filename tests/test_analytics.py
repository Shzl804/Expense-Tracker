import re

import pytest

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
    registration = client.post(
        "/register",
        data={
            "name": "Analytics User",
            "email": "analytics@example.com",
            "password": "test-password",
        },
    )
    assert registration.status_code == 302

    login = client.post(
        "/login",
        data={"email": "analytics@example.com", "password": "test-password"},
    )
    assert login.status_code == 302
    return client


def test_analytics_requires_authentication(client):
    response = client.get("/analytics")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_anonymous_navigation_does_not_expose_analytics(client):
    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/analytics"' not in page
    assert ">Analytics<" not in page


def test_authenticated_analytics_page_renders_and_highlights_nav(auth_client):
    response = auth_client.get("/analytics")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<title>Analytics — Spendly</title>" in page
    assert "Coming soon" in page
    assert "Advanced Analytics" in page
    assert "powerful insights and visualizations" in page
    assert "We're crafting something special" in page
    assert 'href="/analytics"' in page

    analytics_link = re.search(
        r'<a href="/analytics"[^>]*>Analytics</a>', page
    )
    assert analytics_link is not None
    assert "nav-active" in analytics_link.group(0)
    assert 'aria-current="page"' in analytics_link.group(0)
