from datetime import date
import pytest
from app import app
import database.db as db

@pytest.fixture
def database_path(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "expense_tracker.db")
    db.init_db()
    return db.DATABASE_PATH

@pytest.fixture
def client(database_path):
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with app.test_client() as test_client:
        # Create a user and seed some expenses
        connection = db.get_db()
        cursor = connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Filter User", "filter@spendly.com", "hash")
        )
        user_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food", "2026-01-05", "Early Jan"),
                (user_id, 200.0, "Bills", "2026-01-15", "Mid Jan"),
                (user_id, 300.0, "Transport", "2026-02-10", "Early Feb"),
            ]
        )
        connection.commit()
        connection.close()

        with test_client.session_transaction() as session:
            session["user_id"] = user_id
            session["user_name"] = "Filter User"

        yield test_client

def test_profile_date_filter_range(client):
    response = client.get("/profile?start_date=2026-01-01&end_date=2026-01-31")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₨300.00" in page
    assert "Early Jan" in page
    assert "Mid Jan" in page
    assert "Early Feb" not in page

def test_profile_date_filter_invalid_dates(client):
    response = client.get("/profile?start_date=not-a-date&end_date=2026-01-31")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    # Should fall back to unfiltered view
    assert "₨600.00" in page or "Early Feb" in page

def test_profile_date_filter_start_after_end(client):
    response = client.get("/profile?start_date=2026-02-01&end_date=2026-01-01")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    # Should fall back to unfiltered view
    assert "Early Feb" in page
