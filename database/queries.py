"""Database query helpers for the profile page."""

from datetime import datetime

from .db import get_db


def get_user_by_id(user_id):
    """Return public profile details for a user, or None when absent."""
    connection = get_db()
    try:
        row = connection.execute(
            """
            SELECT name, email, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    created_at = _parse_datetime(row["created_at"])
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created_at.strftime("%B %Y") if created_at else "—",
    }


def _build_date_where_clause(user_id, date_from=None, date_to=None):
    where_clause = "WHERE user_id = ?"
    params = [user_id]
    if date_from:
        where_clause += " AND date >= ?"
        params.append(date_from)
    if date_to:
        where_clause += " AND date <= ?"
        params.append(date_to)
    return where_clause, params


def get_summary_stats(user_id, date_from=None, date_to=None):
    """Return total spending, transaction count, and top category."""
    where_clause, params = _build_date_where_clause(user_id, date_from, date_to)
    connection = get_db()
    try:
        totals = connection.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS total_spent,
                   COUNT(*) AS transaction_count
            FROM expenses
            {where_clause}
            """,
            params,
        ).fetchone()
        top_category = connection.execute(
            f"""
            SELECT category
            FROM expenses
            {where_clause}
            GROUP BY category
            ORDER BY SUM(amount) DESC, category ASC
            LIMIT 1
            """,
            params,
        ).fetchone()
    finally:
        connection.close()

    return {
        "total_spent": float(totals["total_spent"] or 0),
        "transaction_count": int(totals["transaction_count"] or 0),
        "top_category": top_category["category"] if top_category else "—",
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """Return a user's most recent expenses, newest first."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a non-negative integer")

    where_clause, params = _build_date_where_clause(user_id, date_from, date_to)
    query_params = list(params) + [limit]

    connection = get_db()
    try:
        rows = connection.execute(
            f"""
            SELECT date, description, category, amount
            FROM expenses
            {where_clause}
            ORDER BY date DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            query_params,
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "date": row["date"],
            "description": row["description"] or "—",
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return category totals and integer percentages summing to 100."""
    where_clause, params = _build_date_where_clause(user_id, date_from, date_to)

    connection = get_db()
    try:
        rows = connection.execute(
            f"""
            SELECT category AS name, SUM(amount) AS amount
            FROM expenses
            {where_clause}
            GROUP BY category
            ORDER BY amount DESC, name ASC
            """,
            params,
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return []

    amounts = [float(row["amount"]) for row in rows]
    total = sum(amounts)
    if total <= 0:
        percentages = [0] * len(rows)
    else:
        percentages = [int(round(amount / total * 100)) for amount in amounts]
        percentages[0] += 100 - sum(percentages)

    return [
        {"name": row["name"], "amount": amount, "pct": pct}
        for row, amount, pct in zip(rows, amounts, percentages)
    ]


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
