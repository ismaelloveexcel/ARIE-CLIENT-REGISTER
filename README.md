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
CRM_ADMIN_USERNAME=admin CRM_ADMIN_PASSWORD='strong-password' CRM_SECRET_KEY='replace-this' python app.py
```

Then open: `http://127.0.0.1:5000/login`

> For private/internal use, set strong values for `CRM_ADMIN_PASSWORD` and `CRM_SECRET_KEY`.

## Tests

```bash
python -m unittest tests/test_app.py -v
```
