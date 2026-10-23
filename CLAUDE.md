
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spendly is a small Flask expense-tracker scaffold. The current application is primarily a public landing/auth/legal UI: persistence, authentication, and expense CRUD are planned but not implemented yet.

## Development commands

Create and activate a virtual environment, then install the pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the development server on port 5001:

```bash
./.venv/bin/python app.py
```

The same command can be run as `python app.py` after activating `.venv`. Flask debug mode is enabled in `app.py`; do not treat this as a production server.

Run the test suite:

```bash
./.venv/bin/python -m pytest
```

Run one test file or one test:

```bash
./.venv/bin/python -m pytest tests/test_example.py
./.venv/bin/python -m pytest tests/test_example.py::test_name
```

There is currently no test directory, build system, or lint configuration in the repository. The pinned development/test dependencies are Flask, Werkzeug, pytest, and pytest-flask.

## Architecture

- `app.py` is the Flask entry point and route layer. It creates the module-level `app`, renders the landing, registration, login, terms, and privacy templates, and currently returns placeholder text for logout, profile, and expense add/edit/delete routes.
- `templates/base.html` is the shared Jinja layout. It owns the navigation, footer, global stylesheet/script includes, and the `content`/`scripts` blocks used by child templates.
- `templates/` contains server-rendered Jinja pages. `landing.html` is the public marketing page; `login.html` and `register.html` contain forms whose POST targets are not implemented yet; `terms.html` and `privacy.html` are informational pages.
- `static/css/style.css` provides shared site/auth styling, while `static/css/landing.css` contains landing-page-specific styling. `static/js/main.js` is the global JavaScript entry point and is currently only a placeholder; page-specific landing behavior is inline in `landing.html`.
- `database/` is reserved for persistence. `database/db.py` currently contains only a design note for future `get_db()`, `init_db()`, and `seed_db()` functions; no SQLite connection or schema is active. The intended database filename is `expense_tracker.db`, which is ignored by Git.

When adding backend functionality, keep route handling in `app.py` consistent with the existing module-level Flask app unless introducing a deliberate application-factory refactor. If implementing the forms, add the corresponding `POST` methods and connect them to the database/session design rather than treating the current form actions as working endpoints.
