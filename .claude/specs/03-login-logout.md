# Spec: Login and Logout

## Overview
Implement session-based authentication for existing Spendly accounts. Users can submit their email and password through the existing sign-in page, receive clear feedback for invalid credentials, and be redirected into the authenticated application after a successful login. Logged-in users can end their session through logout so later roadmap features can enforce access control.

## Depends on
- Step 1: Database Setup — provides the `users` table and database access helpers.
- Step 2: Registration — provides account creation and the stored Werkzeug password hashes that login verifies.

## Routes
- `GET /login` — render the sign-in form, redirect already-authenticated users as appropriate — public.
- `POST /login` — validate submitted credentials, establish the user session on success, and return an error on failure — public.
- `GET /logout` — clear the current session and redirect to the landing or sign-in page — logged-in.

## Database changes
No database changes. Authenticate against the existing `users` table in `database/db.py`; do not add a second authentication table or alter the existing schema.

## Templates
- **Create:** None.
- **Modify:**
  - `templates/login.html` — display login errors and preserve the existing POST form behavior as needed.
  - `templates/base.html` — show authenticated navigation (including logout) when a user session exists and public navigation otherwise.

## Files to change
- `app.py` — configure the Flask session, implement GET/POST login handling, verify password hashes, and implement logout.
- `templates/login.html` — support the authentication response and validation feedback.
- `templates/base.html` — make navigation conditional on authentication state.

## Files to create
- None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only.
- Passwords hashed with werkzeug; verify stored hashes with Werkzeug and never compare or store plaintext passwords.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Store only the minimum user identity needed for the session, such as the user ID and display name; never store the password or password hash in the session.
- Use a configured secret key suitable for signed Flask sessions and do not expose secrets in templates or source control.
- Use `get_db()` for database access and close connections reliably after each request.
- Keep credential failure responses generic so they do not reveal whether an email exists.
- Redirect after successful login and logout to avoid accidental form resubmission.

## Definition of done
- [ ] `GET /login` renders the existing sign-in page for an unauthenticated visitor.
- [ ] A valid registered email and password create a Flask session containing the authenticated user identity and redirect away from `/login`.
- [ ] An unknown email or incorrect password does not create a session and redisplays the login form with a clear, generic error.
- [ ] A logged-in visitor sees authenticated navigation with a working logout link instead of sign-in/register links.
- [ ] `GET /logout` clears the session and redirects to a public page.
- [ ] After logout, authenticated navigation is no longer shown and protected future routes would not see the prior user identity.
- [ ] Password verification uses the stored Werkzeug hash and never plaintext comparison.
- [ ] Existing registration, landing, terms, privacy, and database startup behavior continues to work without errors.
- [ ] The app starts successfully and login/logout can be exercised through Flask’s test client.
