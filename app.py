import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix


ROOT = Path(__file__).resolve().parent
EXAM_SIZE = 40
EXAM_SECONDS = 45 * 60
PAGE_SIZE = 20


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("QUIZ_DATABASE", str(ROOT / "instance" / "quiz.sqlite3")),
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SESSION_COOKIE_NAME="aicb_visitor",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=365 * 86400,
        MAX_CONTENT_LENGTH=16 * 1024,
        IP_EXAMS_PER_HOUR=120,
        VISITOR_EXAMS_PER_HOUR=10,
    )
    if test_config:
        app.config.update(test_config)
    database = Path(app.config["DATABASE"])
    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if database.parent == ROOT / "instance":
        database.parent.chmod(0o700)
    if not app.config["SECRET_KEY"]:
        keyfile = database.parent / "secret.key"
        try:
            with open(keyfile, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = keyfile.read_text().strip()
        if len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError("secret.key không hợp lệ; cần khóa bí mật bền vững ít nhất 32 ký tự.")
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("SECRET_KEY cần ít nhất 32 ký tự ngẫu nhiên.")
    if os.environ.get("TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    raw_bank = (ROOT / "data" / "questions.json").read_bytes()
    bank = json.loads(raw_bank)
    questions = bank["questions"]
    topic_names = {t["id"]: t["title"] for t in bank["topics"]}
    if (len(questions) < EXAM_SIZE or len({q["id"] for q in questions}) != len(questions)
            or any(len(q["options"]) != 4 or type(q["answer"]) is not int
                   or not 0 <= q["answer"] < 4 or q["day"] not in topic_names for q in questions)):
        raise RuntimeError("Ngân hàng câu hỏi không hợp lệ.")
    bank_version = hashlib.sha256(raw_bank).hexdigest()[:12]

    def connect():
        db = sqlite3.connect(app.config["DATABASE"], timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    with connect() as db:
        database.chmod(0o600)
        db.execute("PRAGMA journal_mode = WAL")
        if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
            raise RuntimeError("Phiên bản database không được hỗ trợ. Không tự ghi đè dữ liệu.")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                nickname TEXT NOT NULL,
                nickname_key TEXT NOT NULL,
                ip_key TEXT NOT NULL,
                bank_version TEXT NOT NULL,
                questions TEXT NOT NULL,
                answers TEXT NOT NULL DEFAULT '{}',
                started_at INTEGER NOT NULL,
                deadline_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'abandoned')),
                submitted_at INTEGER,
                duration INTEGER,
                correct_count INTEGER,
                finish_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS attempts_visitor ON attempts(visitor_id, started_at);
            CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip_key, started_at);
            CREATE INDEX IF NOT EXISTS attempts_expiry ON attempts(status, deadline_at);
            CREATE INDEX IF NOT EXISTS attempts_board
                ON attempts(bank_version, status, correct_count DESC, duration, submitted_at, id);
            PRAGMA user_version = 1;
        """)
    db.close()

    def get_db():
        if "db" not in g:
            g.db = connect()
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        if "db" in g:
            g.db.close()

    def error(message, code=400):
        return jsonify(error=message), code

    def visitor():
        if not re.fullmatch(r"[0-9a-f]{32}", session.get("visitor_id", "")):
            session["visitor_id"] = secrets.token_hex(16)
        session.permanent = True
        return session["visitor_id"]

    def payload():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None

    def public_question(q):
        return {"id": q["id"], "topic": q["topic"], "day": q["day"],
                "q": q["q"], "options": q["options"]}

    def summary(row):
        return {
            "id": row["id"], "nickname": row["nickname"],
            "correct": row["correct_count"], "total": EXAM_SIZE,
            "score": round(row["correct_count"] / EXAM_SIZE * 10, 2),
            "duration": row["duration"], "submitted_at": row["submitted_at"],
            "bank_version": row["bank_version"], "finish_reason": row["finish_reason"],
        }

    def finish(db, row, now, reason):
        qs, answers = json.loads(row["questions"]), json.loads(row["answers"])
        ended = min(now, row["deadline_at"])
        correct = sum(answers.get(q["id"]) == q["answer"] for q in qs)
        db.execute("""UPDATE attempts SET status='completed', submitted_at=?, duration=?,
                      correct_count=?, finish_reason=? WHERE id=? AND status='active'""",
                   (ended, max(0, ended - row["started_at"]), correct, reason, row["id"]))

    def settle_expired(db, now):
        # Lazy finalization avoids a background scheduler; the deadline still decides the score.
        for row in db.execute("SELECT * FROM attempts WHERE status='active' AND deadline_at<=?", (now,)).fetchall():
            finish(db, row, now, "timeout")

    def result(row):
        output = summary(row)
        answers = json.loads(row["answers"])
        details, topics = [], {}
        for q in json.loads(row["questions"]):
            selected = answers.get(q["id"])
            right = selected == q["answer"]
            details.append({**q, "selected": selected, "correct": right})
            stats = topics.setdefault(q["day"], {"title": q["topic"], "total": 0, "correct": 0})
            stats["total"] += 1
            stats["correct"] += int(right)
        output.update(questions=details, topics=list(topics.values()),
                      unanswered=sum(q["selected"] is None for q in details))
        output["assessment"] = ("Nắm khá vững" if output["score"] >= 8 else
                                "Cần củng cố" if output["score"] >= 5 else "Cần ôn lại")
        return output

    @app.before_request
    def protect_writes():
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE"):
            if not request.is_json:
                return error("Yêu cầu phải dùng JSON.", 415)
            origin = request.headers.get("Origin")
            if origin:
                source = urlsplit(origin)
                target = urlsplit(request.host_url)
                if (source.scheme, source.netloc) != (target.scheme, target.netloc):
                    return error("Nguồn yêu cầu không hợp lệ.", 403)
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return error("Không chấp nhận yêu cầu từ website khác.", 403)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def too_large(_error):
        return error("Dữ liệu gửi lên quá lớn.", 413)

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(exc):
        app.logger.exception("Database unavailable: %s", exc)
        return error("Chưa lưu được vì máy chủ đang bận. Vui lòng thử lại.", 503)

    @app.get("/")
    def home():
        visitor()
        return render_template("index.html")

    @app.get("/api/config")
    def config():
        visitor()
        return jsonify(bank_version=bank_version, question_count=len(questions),
                       exam_size=EXAM_SIZE, exam_seconds=EXAM_SECONDS,
                       topics=[{**t, "count": sum(q["day"] == t["id"] for q in questions)}
                               for t in bank["topics"]])

    @app.post("/api/exams")
    def create_exam():
        data = payload()
        name = data.get("nickname") if data else None
        if not isinstance(name, str):
            return error("Vui lòng nhập biệt danh từ 2–30 ký tự.")
        name = " ".join(unicodedata.normalize("NFC", name).split())
        if not 2 <= len(name) <= 30 or any(unicodedata.category(c).startswith("C") for c in name):
            return error("Biệt danh cần 2–30 ký tự, không chứa ký tự điều khiển.")
        uid, now = visitor(), int(time.time())
        ip_key = hmac.new(str(app.config["SECRET_KEY"]).encode(),
                          (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            for column, value, limit in (
                ("visitor_id", uid, app.config["VISITOR_EXAMS_PER_HOUR"]),
                ("ip_key", ip_key, app.config["IP_EXAMS_PER_HOUR"]),
            ):
                count = db.execute(f"SELECT count(*) FROM attempts WHERE {column}=? AND started_at>?",
                                   (value, now - 3600)).fetchone()[0]
                if count >= limit:
                    response, status = error("Đã tạo nhiều đề trong một giờ. Vui lòng thử lại sau.", 429)
                    response.headers["Retry-After"] = "3600"
                    return response, status
            settle_expired(db, now)
            db.execute("UPDATE attempts SET status='abandoned' WHERE visitor_id=? AND status='active'", (uid,))
            chosen = [{**q, "topic": topic_names[q["day"]]} for q in secrets.SystemRandom().sample(questions, EXAM_SIZE)]
            exam_id = secrets.token_hex(16)
            db.execute("""INSERT INTO attempts
                (id,visitor_id,nickname,nickname_key,ip_key,bank_version,questions,started_at,deadline_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (exam_id, uid, name, name.casefold(), ip_key, bank_version,
                                             json.dumps(chosen, ensure_ascii=False), now, now + EXAM_SECONDS))
        return jsonify(id=exam_id), 201

    @app.get("/api/exams/<exam_id>")
    def get_exam(exam_id):
        db, now = get_db(), int(time.time())
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=? AND visitor_id=?",
                             (exam_id, visitor())).fetchone()
            if row is None or row["status"] == "abandoned":
                return error("Không tìm thấy bài đang làm trên trình duyệt này.", 404)
            if row["status"] == "active" and row["deadline_at"] <= now:
                finish(db, row, now, "timeout")
                row = db.execute("SELECT * FROM attempts WHERE id=?", (exam_id,)).fetchone()
        if row["status"] == "completed":
            return jsonify(status="completed", id=exam_id)
        return jsonify(id=exam_id, status="active", nickname=row["nickname"], server_now=now,
                       deadline_at=row["deadline_at"], started_at=row["started_at"],
                       answers=json.loads(row["answers"]),
                       questions=[public_question(q) for q in json.loads(row["questions"])])

    def mutate_exam(exam_id, submit):
        data = payload()
        if data is None:
            return error("Dữ liệu câu trả lời không hợp lệ.")
        db, now = get_db(), int(time.time())
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=? AND visitor_id=?",
                             (exam_id, visitor())).fetchone()
            if row is None or row["status"] == "abandoned":
                return error("Bạn không có quyền sửa lượt thi này.", 404)
            if row["status"] == "active" and row["deadline_at"] <= now:
                finish(db, row, now, "timeout")
                row = db.execute("SELECT * FROM attempts WHERE id=?", (exam_id,)).fetchone()
            if row["status"] == "completed":
                return jsonify(status="completed", id=exam_id)
            ids = {q["id"] for q in json.loads(row["questions"])}
            if submit:
                answers = data.get("answers")
            else:
                if not isinstance(data.get("question_id"), str) or data["question_id"] not in ids:
                    return error("Câu hỏi không thuộc đề thi.")
                answers = {**json.loads(row["answers"]), data["question_id"]: data.get("option")}
            if (not isinstance(answers, dict) or not answers.keys() <= ids
                    or any(v is not None and (type(v) is not int or not 0 <= v < 4)
                           for v in answers.values())):
                return error("Câu trả lời phải thuộc đề và có lựa chọn hợp lệ.")
            db.execute("UPDATE attempts SET answers=? WHERE id=?", (json.dumps(answers), exam_id))
            if submit:
                row = db.execute("SELECT * FROM attempts WHERE id=?", (exam_id,)).fetchone()
                finish(db, row, now, "submitted")
        return jsonify(status="completed" if submit else "active", id=exam_id, saved_at=now)

    @app.put("/api/exams/<exam_id>/answers")
    def save_answer(exam_id):
        return mutate_exam(exam_id, False)

    @app.post("/api/exams/<exam_id>/submit")
    def submit_exam(exam_id):
        return mutate_exam(exam_id, True)

    @app.get("/api/results/<exam_id>")
    def get_result(exam_id):
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=?", (exam_id,)).fetchone()
            if row and row["status"] == "active" and row["deadline_at"] <= int(time.time()):
                finish(db, row, int(time.time()), "timeout")
                row = db.execute("SELECT * FROM attempts WHERE id=?", (exam_id,)).fetchone()
        if row is None or row["status"] != "completed":
            return error("Kết quả chưa được công khai hoặc không tồn tại.", 404)
        return jsonify(result(row))

    @app.get("/api/leaderboard")
    @app.get("/api/history")
    def list_results():
        raw_page = request.args.get("page", "1")
        if not raw_page.isascii() or not raw_page.isdigit() or len(raw_page) > 6 or int(raw_page) < 1:
            return error("Trang không hợp lệ.")
        page = int(raw_page)
        query = request.args.get("q", "").strip()
        if len(query) > 30:
            return error("Từ khóa tối đa 30 ký tự.")
        board = request.path.endswith("leaderboard")
        # Only current-bank results compete; historical snapshots remain publicly readable.
        where = "status='completed'" + (" AND bank_version=?" if board else "")
        args = [bank_version] if board else []
        if query:
            where += " AND instr(nickname_key, ?) > 0"
            args.append(unicodedata.normalize("NFC", query).casefold())
        order = "correct_count DESC, duration, submitted_at, id" if board else "submitted_at DESC, id DESC"
        db = get_db()
        with db:
            db.execute("BEGIN IMMEDIATE")
            settle_expired(db, int(time.time()))
            total = db.execute(f"SELECT count(*) FROM attempts WHERE {where}", args).fetchone()[0]
            pages = max(1, math.ceil(total / PAGE_SIZE))
            page = min(page, pages)
            if board:
                ranked = f"""SELECT *, ROW_NUMBER() OVER (ORDER BY {order}) AS rank
                             FROM attempts WHERE status='completed' AND bank_version=?"""
                filtered = " WHERE instr(nickname_key, ?) > 0" if query else ""
                rows = db.execute(f"SELECT * FROM ({ranked}){filtered} ORDER BY rank LIMIT ? OFFSET ?",
                                  (*args, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            else:
                rows = db.execute(f"SELECT * FROM attempts WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                                  (*args, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
        return jsonify(items=[{**summary(r), **({"rank": r["rank"]} if board else {})} for r in rows], page=page, pages=pages, total=total,
                       page_size=PAGE_SIZE, bank_version=bank_version)

    return app
