# ARIE-CLIENT-REGISTER

Standalone private CRM/client register for Onboarda/RegMind.

## Features

- Client/company register
- Contact person management
- Lead/client status tracking
- Notes and follow-up task tracking
- KYC/onboarding stage tracking
- Document checklist status tracking
- Search and filtering
- Simple dashboard (pipeline + task overview)
- Secure login (session-based, hashed password)
- Audit-friendly activity history per client and global recent activity

## Tech

- Python + Flask
- SQLite database (`instance/crm.db`)
- No dependency on existing `onboarda` repository

## Run locally

```bash
python -m pip install -r requirements.txt
CRM_ADMIN_USERNAME=admin CRM_ADMIN_PASSWORD='strong-password' CRM_SECRET_KEY='replace-this' CRM_SESSION_COOKIE_SECURE=0 python app.py
```

Then open: `http://127.0.0.1:5000/login`

`CRM_ADMIN_PASSWORD` and `CRM_SECRET_KEY` are required at runtime (except in tests) and must be set to strong values.
Set `CRM_SESSION_COOKIE_SECURE=1` in HTTPS environments.
Login protection defaults to a 15 minute window with a 15 minute lockout after 5 failed attempts per username/IP pair. Override with `CRM_LOGIN_MAX_ATTEMPTS`, `CRM_LOGIN_RATE_WINDOW_SECONDS`, and `CRM_LOGIN_LOCKOUT_SECONDS` if needed.

## Security defaults

- Session cookies are `HttpOnly`, `SameSite=Lax`, and secure by default outside tests.
- All mutating form POST routes, including login/logout, require a session-backed CSRF token.
- SQLite foreign keys are enabled for every connection.
- Runtime startup fails outside tests unless `CRM_SECRET_KEY` and `CRM_ADMIN_PASSWORD` are explicitly configured.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
CRM_ADMIN_USERNAME=admin \
CRM_ADMIN_PASSWORD='change-this-before-real-use' \
CRM_SECRET_KEY='replace-with-a-long-random-secret' \
CRM_SESSION_COOKIE_SECURE=0 \
python app.py
```

## Tests

```bash
python -m unittest -v
```

## CI

GitHub Actions runs the test suite on every push and pull request with the repository's pinned dependencies.
