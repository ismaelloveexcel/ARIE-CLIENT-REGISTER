import os
import sqlite3
import secrets
from datetime import date
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


DEFAULT_STATUS = "lead"
DEFAULT_KYC_STAGE = "not_started"
DEFAULT_DOC_STATUS = "not_started"
INSECURE_SECRET_KEY = "dev-change-me"
INSECURE_ADMIN_PASSWORD = "ChangeMe123!"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CRM_SECRET_KEY", INSECURE_SECRET_KEY),
        DATABASE=os.path.join(app.instance_path, "crm.db"),
        ADMIN_USERNAME=os.environ.get("CRM_ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("CRM_ADMIN_PASSWORD", INSECURE_ADMIN_PASSWORD),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CRM_SESSION_COOKIE_SECURE", "1") == "1",
    )

    if test_config:
        app.config.update(test_config)

    if app.config.get("TESTING"):
        app.config["SESSION_COOKIE_SECURE"] = False
    else:
        if app.config["SECRET_KEY"] == INSECURE_SECRET_KEY:
            raise RuntimeError("CRM_SECRET_KEY must be set to a strong secret key.")
        if app.config["ADMIN_PASSWORD"] == INSECURE_ADMIN_PASSWORD:
            raise RuntimeError("CRM_ADMIN_PASSWORD must be set to a strong admin password.")

    os.makedirs(app.instance_path, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    def close_db(_=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    app.teardown_appcontext(close_db)

    def init_db():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                kyc_stage TEXT NOT NULL,
                document_status TEXT NOT NULL,
                is_lead INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                role TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                follow_up_date TEXT,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )

        existing = db.execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (app.config["ADMIN_USERNAME"],),
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (app.config["ADMIN_USERNAME"], generate_password_hash(app.config["ADMIN_PASSWORD"])),
            )
        elif not check_password_hash(existing["password_hash"], app.config["ADMIN_PASSWORD"]):
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(app.config["ADMIN_PASSWORD"]), existing["id"]),
            )
        db.commit()

    with app.app_context():
        init_db()

    def log_activity(event_type, entity, entity_id, details):
        db = get_db()
        db.execute(
            "INSERT INTO activities (user_id, event_type, entity, entity_id, details) VALUES (?, ?, ?, ?, ?)",
            (session.get("user_id"), event_type, entity, entity_id, details),
        )
        db.commit()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    def get_csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def validate_csrf():
        form_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        return bool(form_token and session_token and secrets.compare_digest(form_token, session_token))

    def csrf_protect(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method == "POST" and not validate_csrf():
                return "Invalid CSRF token", 400
            return view(*args, **kwargs)

        return wrapped

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": get_csrf_token()}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if not validate_csrf():
                return "Invalid CSRF token", 400
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    @csrf_protect
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        db = get_db()
        stats = {
            "leads": db.execute("SELECT COUNT(*) AS c FROM clients WHERE is_lead = 1").fetchone()["c"],
            "clients": db.execute("SELECT COUNT(*) AS c FROM clients WHERE is_lead = 0").fetchone()["c"],
            "open_tasks": db.execute("SELECT COUNT(*) AS c FROM notes WHERE done = 0").fetchone()["c"],
            "overdue_tasks": db.execute(
                "SELECT COUNT(*) AS c FROM notes WHERE done = 0 AND follow_up_date IS NOT NULL AND follow_up_date < ?",
                (date.today().isoformat(),),
            ).fetchone()["c"],
        }
        status_breakdown = db.execute(
            "SELECT status, COUNT(*) AS count FROM clients GROUP BY status ORDER BY count DESC"
        ).fetchall()
        recent_activity = db.execute(
            """
            SELECT a.created_at, a.details, a.event_type, a.entity, u.username
            FROM activities a
            LEFT JOIN users u ON u.id = a.user_id
            ORDER BY a.id DESC
            LIMIT 20
            """
        ).fetchall()
        return render_template(
            "dashboard.html",
            stats=stats,
            status_breakdown=status_breakdown,
            recent_activity=recent_activity,
        )

    @app.route("/clients")
    @login_required
    def clients_list():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        kyc_stage = request.args.get("kyc_stage", "").strip()
        document_status = request.args.get("document_status", "").strip()
        kind = request.args.get("kind", "all")

        query = "SELECT * FROM clients WHERE 1=1"
        params = []
        if q:
            query += " AND name LIKE ?"
            params.append(f"%{q}%")
        if status:
            query += " AND status = ?"
            params.append(status)
        if kyc_stage:
            query += " AND kyc_stage = ?"
            params.append(kyc_stage)
        if document_status:
            query += " AND document_status = ?"
            params.append(document_status)
        if kind == "lead":
            query += " AND is_lead = 1"
        elif kind == "client":
            query += " AND is_lead = 0"

        query += " ORDER BY updated_at DESC, id DESC"
        clients = get_db().execute(query, tuple(params)).fetchall()
        return render_template("clients.html", clients=clients)

    @app.route("/clients/new", methods=["GET", "POST"])
    @login_required
    @csrf_protect
    def create_client():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            status = request.form.get("status", DEFAULT_STATUS).strip() or DEFAULT_STATUS
            kyc_stage = request.form.get("kyc_stage", DEFAULT_KYC_STAGE).strip() or DEFAULT_KYC_STAGE
            document_status = request.form.get("document_status", DEFAULT_DOC_STATUS).strip() or DEFAULT_DOC_STATUS
            kind = request.form.get("kind", "lead")
            if kind not in {"lead", "client"}:
                flash("Type must be either lead or client", "error")
                return render_template("client_form.html")
            is_lead = 1 if kind == "lead" else 0

            if not name:
                flash("Company/client name is required", "error")
                return render_template("client_form.html")

            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO clients (name, status, kyc_stage, document_status, is_lead, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (name, status, kyc_stage, document_status, is_lead),
            )
            db.commit()
            client_id = cursor.lastrowid
            log_activity("create", "client", client_id, f"Created client record for {name}")
            return redirect(url_for("client_detail", client_id=client_id))

        return render_template("client_form.html")

    @app.route("/clients/<int:client_id>")
    @login_required
    def client_detail(client_id):
        db = get_db()
        client = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            return "Not found", 404

        contacts = db.execute(
            "SELECT * FROM contacts WHERE client_id = ? ORDER BY id DESC", (client_id,)
        ).fetchall()
        notes = db.execute(
            "SELECT * FROM notes WHERE client_id = ? ORDER BY done ASC, follow_up_date ASC, id DESC", (client_id,)
        ).fetchall()
        activities = db.execute(
            """
            SELECT a.*, u.username
            FROM activities a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE entity = 'client' AND entity_id = ?
            ORDER BY a.id DESC
            LIMIT 100
            """,
            (client_id,),
        ).fetchall()
        return render_template(
            "client_detail.html",
            client=client,
            contacts=contacts,
            notes=notes,
            activities=activities,
        )

    @app.route("/clients/<int:client_id>/edit", methods=["POST"])
    @login_required
    @csrf_protect
    def update_client(client_id):
        db = get_db()
        client = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            return "Not found", 404

        name = request.form.get("name", "").strip()
        status = request.form.get("status", client["status"]).strip() or client["status"]
        kyc_stage = (
            request.form.get("kyc_stage", client["kyc_stage"]).strip() or client["kyc_stage"]
        )
        document_status = (
            request.form.get("document_status", client["document_status"]).strip()
            or client["document_status"]
        )
        kind = request.form.get("kind", "lead")
        if kind not in {"lead", "client"}:
            flash("Type must be either lead or client", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        is_lead = 1 if kind == "lead" else 0

        if not name:
            flash("Name is required", "error")
            return redirect(url_for("client_detail", client_id=client_id))

        db.execute(
            """
            UPDATE clients
            SET name = ?, status = ?, kyc_stage = ?, document_status = ?, is_lead = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, status, kyc_stage, document_status, is_lead, client_id),
        )
        db.commit()
        log_activity("update", "client", client_id, f"Updated profile and pipeline state for {name}")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.route("/clients/<int:client_id>/contacts", methods=["POST"])
    @login_required
    @csrf_protect
    def add_contact(client_id):
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "").strip()

        if not name:
            flash("Contact person name is required", "error")
            return redirect(url_for("client_detail", client_id=client_id))

        db = get_db()
        client = db.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            return "Not found", 404
        db.execute(
            "INSERT INTO contacts (client_id, name, email, phone, role) VALUES (?, ?, ?, ?, ?)",
            (client_id, name, email, phone, role),
        )
        db.commit()
        log_activity("create", "client", client_id, f"Added contact person {name}")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.route("/clients/<int:client_id>/notes", methods=["POST"])
    @login_required
    @csrf_protect
    def add_note(client_id):
        content = request.form.get("content", "").strip()
        follow_up_date = request.form.get("follow_up_date", "").strip() or None
        done = 1 if request.form.get("done") == "on" else 0

        if not content:
            flash("Note/task content is required", "error")
            return redirect(url_for("client_detail", client_id=client_id))

        db = get_db()
        client = db.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            return "Not found", 404
        db.execute(
            "INSERT INTO notes (client_id, content, follow_up_date, done) VALUES (?, ?, ?, ?)",
            (client_id, content, follow_up_date, done),
        )
        db.commit()
        log_activity("create", "client", client_id, "Added note/follow-up task")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.route("/clients/<int:client_id>/notes/<int:note_id>/toggle", methods=["POST"])
    @login_required
    @csrf_protect
    def toggle_note(client_id, note_id):
        db = get_db()
        note = db.execute("SELECT done FROM notes WHERE id = ? AND client_id = ?", (note_id, client_id)).fetchone()
        if not note:
            return "Not found", 404
        new_done = 0 if note["done"] else 1
        db.execute("UPDATE notes SET done = ? WHERE id = ?", (new_done, note_id))
        db.commit()
        log_activity("update", "client", client_id, f"Marked task #{note_id} as {'done' if new_done else 'open'}")
        return redirect(url_for("client_detail", client_id=client_id))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=False)
