import json
import os
import secrets
from datetime import datetime
import sqlite3
import base64

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, send_file
import io
import zipfile

import phonenumbers
from phonenumbers import geocoder, carrier
from werkzeug.security import generate_password_hash, check_password_hash
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_FILE = os.path.join(DB_DIR, "app.db")


def ensure_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','viewer')),
                created_at TEXT NOT NULL
            )
            """
        )
        # Migration: add 'phone' column to users if missing
        c.execute("PRAGMA table_info(users)")
        user_cols = [row[1] for row in c.fetchall()]
        if "phone" not in user_cols:
            c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT,
                imei TEXT UNIQUE,
                phone TEXT UNIQUE,
                carrier TEXT,
                region TEXT,
                api_token TEXT NOT NULL,
                last_update TEXT,
                last_lat REAL,
                last_lng REAL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                ts TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def db_connect():
    ensure_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_device_db(imei=None, phone=None):
    conn = db_connect()
    try:
        c = conn.cursor()
        if imei:
            c.execute("SELECT * FROM devices WHERE imei = ?", (imei,))
        elif phone:
            c.execute("SELECT * FROM devices WHERE phone = ?", (phone,))
        else:
            return None
        row = c.fetchone()
        if not row:
            return None
        device = dict(row)
        c.execute("SELECT lat, lng, ts FROM locations WHERE device_id = ? ORDER BY ts ASC", (row["id"],))
        locs = [dict(r) for r in c.fetchall()]
        device["locations"] = locs
        if device.get("last_lat") is not None and device.get("last_lng") is not None:
            device["last_location"] = {"lat": device["last_lat"], "lng": device["last_lng"]}
        else:
            device["last_location"] = None
        return device
    finally:
        conn.close()


def get_user_by_username_db(username):
    conn = db_connect()
    try:
        c = conn.cursor()
        c.execute("SELECT username, password_hash, role, phone FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def ensure_initial_admin():
    conn = db_connect()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(1) AS cnt FROM users")
        cnt = c.fetchone()["cnt"]
        if cnt == 0:
            from werkzeug.security import generate_password_hash
            admin_username = os.environ.get("ADMIN_USERNAME", "admin")
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
            password_hash = generate_password_hash(admin_password)
            c.execute(
                "INSERT INTO users (username, password_hash, role, phone, created_at) VALUES (?, ?, 'admin', NULL, ?)",
                (admin_username, password_hash, datetime.utcnow().isoformat()),
            )
            conn.commit()
    finally:
        conn.close()


def send_2fa_code(phone, code):
    if not (VONAGE_API_KEY and VONAGE_API_SECRET and VONAGE_FROM_NUMBER):
        raise RuntimeError("Vonage not configured for 2FA")
    payload = {
        "api_key": VONAGE_API_KEY,
        "api_secret": VONAGE_API_SECRET,
        "from": (VONAGE_FROM_NUMBER or "").replace(" ", ""),
        "to": phone,
        "text": f"Your verification code is: {code}",
    }
    r = requests.post("https://rest.nexmo.com/sms/json", data=payload, timeout=10)
    r.raise_for_status()
    resp = r.json()
    messages = resp.get("messages", [])
    if not messages or messages[0].get("status") != "0":
        raise Exception(f"Vonage send failed: {messages[0].get('error-text') if messages else 'unknown'}")


# Initialize DB and seed admin at import time
ensure_db()
ensure_initial_admin()
AGENT_DOWNLOAD_URL = os.environ.get("AGENT_DOWNLOAD_URL")
# Hardcoded Vonage credentials per user request; env vars still override if set
VONAGE_API_KEY = os.environ.get("VONAGE_API_KEY") or "TzjCqBi6z4VtzNOp"
VONAGE_API_SECRET = os.environ.get("VONAGE_API_SECRET") or "5OAQwcgoX89WG3Q62yc1j8ZtRJ3WPlxzjbvX9kvoBG3kuVR3Yb"
VONAGE_FROM_NUMBER = os.environ.get("VONAGE_FROM_NUMBER") or "+263 77 111 2812"


def is_imei(candidate: str) -> bool:
    s = candidate.strip()
    if not s.isdigit():
        return False
    # IMEI is typically 15 digits and uses Luhn checksum
    if len(s) != 15:
        return False
    return luhn_check(s)


def luhn_check(number: str) -> bool:
    total = 0
    reverse_digits = number[::-1]
    for i, ch in enumerate(reverse_digits):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def normalize_phone(number_str: str):
    try:
        pn = phonenumbers.parse(number_str, None)
        if not phonenumbers.is_valid_number(pn):
            return None
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None


def require_login():
    if not session.get("user"):
        flash("Please log in.", "error")
        return redirect(url_for("login", next=request.path))
    return None


def require_role(role):
    user = session.get("user")
    if not user:
        flash("Please log in.", "error")
        return redirect(url_for("login", next=request.path))
    if user.get("role") != role:
        flash("Insufficient privileges.", "error")
        return redirect(url_for("index"))
    return None


@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))

@app.context_processor
def inject_year():
    return {'current_year': datetime.utcnow().year}


@app.route("/add", methods=["GET", "POST"])
def add_device():
    gate = require_login()
    if gate:
        return gate
    if request.method == "POST":
        owner = request.form.get("owner", "").strip()
        imei = request.form.get("imei", "").strip()
        phone = request.form.get("phone", "").strip()

        errors = []
        if imei:
            if not is_imei(imei):
                errors.append("IMEI must be a valid 15-digit number.")
        if phone:
            normalized = normalize_phone(phone)
            if not normalized:
                errors.append("Phone number must be valid and include country code.")
            else:
                phone = normalized

        if not imei and not phone:
            errors.append("Provide at least IMEI or phone number.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("add.html", form={"owner": owner, "imei": imei, "phone": phone})

        # Insert into SQLite
        conn = db_connect()
        try:
            c = conn.cursor()
            # Check unique constraints
            if imei:
                c.execute("SELECT 1 FROM devices WHERE imei = ?", (imei,))
                if c.fetchone():
                    flash("A device with the same IMEI already exists.", "error")
                    return render_template("add.html", form={"owner": owner, "imei": imei, "phone": phone})
            if phone:
                c.execute("SELECT 1 FROM devices WHERE phone = ?", (phone,))
                if c.fetchone():
                    flash("A device with the same phone already exists.", "error")
                    return render_template("add.html", form={"owner": owner, "imei": imei, "phone": phone})

            carrier_name = carrier.name_for_number(phonenumbers.parse(phone), "en") if phone else None
            region_name = geocoder.description_for_number(phonenumbers.parse(phone), "en") if phone else None
            api_token = secrets.token_urlsafe(24)
            c.execute(
                "INSERT INTO devices (owner, imei, phone, carrier, region, api_token, last_update, last_lat, last_lng) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (owner or None, imei or None, phone or None, carrier_name, region_name, api_token),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Device added.", "success")
        return redirect(url_for("index"))

    return render_template("add.html", form={})


@app.route("/search", methods=["POST"])
def search():
    gate = require_login()
    if gate:
        return gate
    query = request.form.get("query", "").strip()
    if not query:
        flash("Enter IMEI or phone number.", "error")
        return redirect(url_for("index"))

    context = {"query": query, "result": None, "coarse": None, "is_imei": False, "user": session.get("user")}

    if is_imei(query):
        context["is_imei"] = True
        result = lookup_device_db(imei=query)
        context["result"] = result
    else:
        normalized = normalize_phone(query)
        if normalized:
            result = lookup_device_db(phone=normalized)
            context["result"] = result
            # Coarse region and carrier for phone numbers
            parsed = phonenumbers.parse(normalized)
            context["coarse"] = {
                "region": geocoder.description_for_number(parsed, "en"),
                "carrier": carrier.name_for_number(parsed, "en"),
            }
        else:
            flash("Invalid IMEI or phone number.", "error")
            return redirect(url_for("index"))

    return render_template("index.html", **context)

@app.route("/api/validate_device", methods=["POST"])
def validate_device():
    payload = request.get_json(silent=True) or {}
    imei = payload.get("imei")
    phone = payload.get("phone")
    token = payload.get("token")

    # Basic validation
    if not token or (not imei and not phone):
        return jsonify({"ok": False, "error": "missing parameters"}), 400

    conn = db_connect()
    try:
        c = conn.cursor()

        # Select device by IMEI or phone
        if imei:
            c.execute("SELECT api_token FROM devices WHERE imei = ?", (imei,))
        else:
            c.execute("SELECT api_token FROM devices WHERE phone = ?", (phone,))

        row = c.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "device not found"}), 404

        if token != row["api_token"]:
            return jsonify({"ok": False, "error": "invalid token"}), 401

        return jsonify({"ok": True, "valid": True}), 200

    except Exception as e:
        print("ERROR in /api/validate_device:", e)
        return jsonify({"ok": False, "error": "internal error"}), 500
    finally:
        conn.close()

@app.route("/api/location_update", methods=["POST"], strict_slashes=False)
def location_update():
    payload = request.get_json(silent=True) or {}
    imei = payload.get("imei")
    phone = payload.get("phone")
    lat = payload.get("lat")
    lng = payload.get("lng")
    token = payload.get("token")

    # Required fields
    if not token or (not imei and not phone) or lat is None or lng is None:
        return jsonify({"ok": False, "error": "missing parameters"}), 400

    conn = db_connect()
    try:
        c = conn.cursor()

        # Fetch device
        if imei:
            c.execute("SELECT id, api_token FROM devices WHERE imei = ?", (imei,))
        else:
            c.execute("SELECT id, api_token FROM devices WHERE phone = ?", (phone,))

        device = c.fetchone()
        if not device:
            return jsonify({"ok": False, "error": "device not found"}), 404

        if token != device["api_token"]:
            return jsonify({"ok": False, "error": "invalid token"}), 401

        device_id = device["id"]

        # Insert history entry
        c.execute("""
            INSERT INTO locations (device_id, lat, lng, ts)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (device_id, lat, lng))

        # Update last known location
        c.execute("""
            UPDATE devices
            SET last_lat = ?, last_lng = ?, last_update = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (lat, lng, device_id))

        conn.commit()

        return jsonify({"ok": True, "updated": True})

    except Exception as e:
        print("ERROR in /api/location_update:", e)
        return jsonify({"ok": False, "error": "internal error"}), 500
    finally:
        conn.close()

@app.route("/device/token", methods=["GET", "POST"])
def device_token():
    gate = require_role("admin")
    if gate:
        return gate
    context = {"device": None}
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        conn = db_connect()
        try:
            c = conn.cursor()
            device_row = None
            if is_imei(query):
                c.execute("SELECT * FROM devices WHERE imei = ?", (query,))
                device_row = c.fetchone()
            else:
                normalized = normalize_phone(query)
                if normalized:
                    c.execute("SELECT * FROM devices WHERE phone = ?", (normalized,))
                    device_row = c.fetchone()
            if not device_row:
                flash("Device not found.", "error")
            else:
                if request.form.get("regen") == "1":
                    new_token = secrets.token_urlsafe(24)
                    c.execute("UPDATE devices SET api_token = ? WHERE id = ?", (new_token, device_row["id"]))
                    conn.commit()
                    device_row = dict(device_row)
                    device_row["api_token"] = new_token
                    flash("Token regenerated.", "success")
                context["device"] = dict(device_row)
        finally:
            conn.close()
    return render_template("device_token.html", **context)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_username_db(username)
        if not user or not check_password_hash(user.get("password_hash", ""), password):
            flash("Invalid credentials.", "error")
            return render_template("login.html")
        # If user has phone configured, require 2FA
        user_phone = user.get("phone")
        if user_phone:
            code = f"{secrets.randbelow(1000000):06d}"
            try:
                normalized = normalize_phone(user_phone)
                if not normalized:
                    raise RuntimeError("User phone invalid for 2FA")
                send_2fa_code(normalized, code)
            except Exception as e:
                flash(f"2FA SMS failed: {e}", "error")
                return render_template("login.html")
            # Store pending user and code in session
            session["pending_user"] = {"username": user["username"], "role": user.get("role", "viewer")}
            session["twofa_code"] = code
            session["twofa_expires"] = (datetime.utcnow().timestamp() + 300)  # 5 minutes
            return redirect(url_for("login_verify"))
        # No phone: allow login (viewer) or warn for admin
        if user.get("role") == "admin":
            flash("Admin login without 2FA phone configured. Please set your phone.", "warning")
        session["user"] = {"username": user["username"], "role": user.get("role", "viewer")}
        flash("Logged in.", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("index"))
    return render_template("login.html")


@app.route("/login/verify", methods=["GET", "POST"])
def login_verify():
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        expected = session.get("twofa_code")
        expires = session.get("twofa_expires", 0)
        if not expected or datetime.utcnow().timestamp() > float(expires):
            flash("Verification code expired. Please log in again.", "error")
            return redirect(url_for("login"))
        if code != expected:
            flash("Invalid verification code.", "error")
            return render_template("twofa.html")
        user = session.get("pending_user")
        if not user:
            flash("No pending login session.", "error")
            return redirect(url_for("login"))
        # finalize login
        session.pop("pending_user", None)
        session.pop("twofa_code", None)
        session.pop("twofa_expires", None)
        session["user"] = user
        flash("Logged in.", "success")
        return redirect(url_for("index"))
    return render_template("twofa.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/users/create", methods=["GET", "POST"])
def create_user():
    gate = require_role("admin")
    if gate:
        return gate
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "viewer")
        phone = request.form.get("phone", "").strip() or None
        conn = db_connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if c.fetchone():
                flash("User already exists.", "error")
                return render_template("user_create.html")
            c.execute(
                "INSERT INTO users (username, password_hash, role, phone, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, phone, datetime.utcnow().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        flash("User created.", "success")
        return redirect(url_for("index"))
    return render_template("user_create.html")


@app.route("/onboard/sms", methods=["GET", "POST"])
def onboard_sms():
    gate = require_login()
    if gate:
        return gate
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        normalized = normalize_phone(phone)
        if not normalized:
            flash("Enter a valid phone number including country code.", "error")
            # Fallback agent URL
            fallback_url = (AGENT_DOWNLOAD_URL or (request.url_root.rstrip('/') + url_for('agent_download')))
            return render_template("onboard.html", agent_url=fallback_url)
        if not (VONAGE_API_KEY and VONAGE_API_SECRET and VONAGE_FROM_NUMBER):
            flash("Vonage is not configured. Set environment variables.", "error")
            fallback_url = (AGENT_DOWNLOAD_URL or (request.url_root.rstrip('/') + url_for('agent_download')))
            return render_template("onboard.html", agent_url=fallback_url)
        try:
            agent_link = (AGENT_DOWNLOAD_URL or (request.url_root.rstrip('/') + url_for('agent_download')))
            body = f"Install the tracking companion app: {agent_link}"
            payload = {
                "api_key": VONAGE_API_KEY,
                "api_secret": VONAGE_API_SECRET,
                "from": (VONAGE_FROM_NUMBER or "").replace(" ", ""),
                "to": normalized,
                "text": body,
            }
            r = requests.post("https://rest.nexmo.com/sms/json", data=payload, timeout=10)
            r.raise_for_status()
            resp = r.json()
            messages = resp.get("messages", [])
            if not messages or messages[0].get("status") != "0":
                raise Exception(f"Vonage send failed: {messages[0].get('error-text') if messages else 'unknown'}")
            flash("Onboarding SMS sent.", "success")
        except Exception as e:
            flash(f"Failed to send SMS: {e}", "error")
        return redirect(url_for("onboard_sms"))
    fallback_url = (AGENT_DOWNLOAD_URL or (request.url_root.rstrip('/') + url_for('agent_download')))
    return render_template("onboard.html", agent_url=fallback_url)


@app.route("/agent/download")
def agent_download():
    # Zip the Android agent example directory and return as attachment
    base_dir = os.path.join(os.path.dirname(__file__), "agent_examples", "android")
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(base_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                arcname = os.path.relpath(full_path, base_dir)
                zf.write(full_path, arcname)
    mem_zip.seek(0)
    return send_file(mem_zip, as_attachment=True, download_name="android_agent_example.zip")


@app.route("/export")
def export():
    gate = require_login()
    if gate:
        return gate
    conn = db_connect()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM devices")
        devices = [dict(r) for r in c.fetchall()]
        for d in devices:
            c.execute("SELECT lat, lng, ts FROM locations WHERE device_id = ? ORDER BY ts ASC", (d["id"],))
            d["locations"] = [dict(r) for r in c.fetchall()]
            d["last_location"] = {"lat": d["last_lat"], "lng": d["last_lng"]} if d.get(
                "last_lat") is not None and d.get("last_lng") is not None else None
        export_data = {"devices": devices}
        return jsonify(export_data)
    finally:
        conn.close()


@app.route("/import", methods=["GET", "POST"])
def import_data():
    gate = require_role("admin")
    if gate:
        return gate
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            flash("Select a JSON file.", "error")
            return render_template("import.html")
        try:
            incoming = json.load(file)
        except Exception:
            flash("Invalid JSON.", "error")
            return render_template("import.html")
        conn = db_connect()
        try:
            c = conn.cursor()
            inc_devices = incoming.get("devices", [])
            for d in inc_devices:
                imei = d.get("imei")
                phone = d.get("phone")
                if imei:
                    c.execute("SELECT 1 FROM devices WHERE imei = ?", (imei,))
                    if c.fetchone():
                        continue
                if phone:
                    c.execute("SELECT 1 FROM devices WHERE phone = ?", (phone,))
                    if c.fetchone():
                        continue
                c.execute(
                    "INSERT INTO devices (owner, imei, phone, carrier, region, api_token, last_update, last_lat, last_lng) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        d.get("owner"),
                        imei,
                        phone,
                        d.get("carrier"),
                        d.get("region"),
                        d.get("api_token") or secrets.token_urlsafe(24),
                        d.get("last_update"),
                        (d.get("last_location") or {}).get("lat"),
                        (d.get("last_location") or {}).get("lng"),
                    ),
                )
                conn.commit()
                # Insert locations history if present
                new_id = c.lastrowid
                for loc in d.get("locations", []) or []:
                    c.execute(
                        "INSERT INTO locations (device_id, lat, lng, ts) VALUES (?, ?, ?, ?)",
                        (new_id, float(loc.get("lat")), float(loc.get("lng")), loc.get("ts")),
                    )
                conn.commit()
        finally:
            conn.close()
        flash("Import completed.", "success")
        return redirect(url_for("index"))
    return render_template("import.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
