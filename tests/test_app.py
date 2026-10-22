import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import EXAM_SECONDS, create_app


class QuizTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = {"TESTING": True, "DATABASE": self.temp.name + "/test.sqlite3", "SECRET_KEY": "test-secret-" * 6}
        self.app = create_app(self.settings)
        self.client = self.app.test_client()
        self.client.get("/api/config")

    def create(self, client=None, name="Người thử"):
        response = (client or self.client).post("/api/exams", json={"nickname": name})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["id"]

    def snapshot(self, exam_id):
        with sqlite3.connect(self.settings["DATABASE"]) as db:
            return json.loads(db.execute("SELECT questions FROM attempts WHERE id=?", (exam_id,)).fetchone()[0])

    def correct_answers(self, exam_id):
        return {q["id"]: q["answer"] for q in self.snapshot(exam_id)}

    def submit(self, exam_id, answers):
        return self.client.post(f"/api/exams/{exam_id}/submit", json={"answers": answers})

    def test_bank_and_random_exams_hide_answer_key(self):
        config = self.client.get("/api/config").json
        self.assertEqual(config["question_count"], 385)
        self.assertEqual(sum(t["count"] for t in config["topics"]), 385)
        first, second = self.create(), None
        one = self.client.get("/api/exams/" + first).json
        second = self.create()
        two = self.client.get("/api/exams/" + second).json
        self.assertEqual(len({q["id"] for q in one["questions"]}), 40)
        self.assertNotEqual([q["id"] for q in one["questions"]], [q["id"] for q in two["questions"]])
        self.assertEqual(two["deadline_at"] - two["started_at"], EXAM_SECONDS)
        for q in two["questions"]:
            self.assertFalse({"answer", "explain", "source"} & q.keys())
        self.assertEqual(self.client.get("/api/results/" + second).status_code, 404)
        self.assertEqual(self.client.get("/data/questions.json").status_code, 404)
        self.assertEqual(self.client.get("/on-thi-AICB.html").status_code, 404)
        self.assertEqual(self.client.get("/api/exams/" + first).status_code, 404)
        self.assertEqual(self.client.get("/api/history").json["total"], 0)

    def test_answers_resume_and_score_with_wrong_and_blank(self):
        exam_id = self.create()
        qs = self.snapshot(exam_id)
        first = qs[0]
        saved = self.client.put(f"/api/exams/{exam_id}/answers", json={"question_id": first["id"], "option": first["answer"]})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get("/api/exams/" + exam_id).json["answers"], {first["id"]: first["answer"]})
        answers = {q["id"]: q["answer"] for q in qs[:30]}
        answers.update({q["id"]: (q["answer"] + 1) % 4 for q in qs[30:35]})
        self.assertEqual(self.submit(exam_id, answers).status_code, 200)
        public = self.app.test_client().get("/api/results/" + exam_id).json
        self.assertEqual((public["correct"], public["unanswered"], public["score"]), (30, 5, 7.5))
        self.assertEqual(public["assessment"], "Cần củng cố")
        self.assertEqual(sum(t["total"] for t in public["topics"]), 40)
        self.assertEqual(sum(t["correct"] for t in public["topics"]), 30)
        self.assertTrue(all("answer" in q and "explain" in q and "source" in q for q in public["questions"]))
        self.assertFalse({"visitor_id", "ip_key", "nickname_key"} & public.keys())

    def test_another_browser_cannot_edit_or_resume(self):
        exam_id = self.create()
        other = self.app.test_client()
        self.assertEqual(other.get("/api/exams/" + exam_id).status_code, 404)
        self.assertEqual(other.post(f"/api/exams/{exam_id}/submit", json={"answers": self.correct_answers(exam_id)}).status_code, 404)
        q = self.snapshot(exam_id)[0]
        self.assertEqual(other.put(f"/api/exams/{exam_id}/answers", json={"question_id": q["id"], "option": 1}).status_code, 404)

    def test_validation_rejects_forged_answers_and_types(self):
        for value in (None, "", "a", "a" * 31, 123, "ab\u200bcd"):
            self.assertEqual(self.client.post("/api/exams", json={"nickname": value}).status_code, 400)
        exam_id = self.create()
        qid = self.snapshot(exam_id)[0]["id"]
        for data in ({"answers": {qid: True}}, {"answers": {qid: 4}}, {"answers": {qid: "1"}},
                     {"answers": {"unknown": 0}}, {"answers": []}, {"score": 10}, []):
            self.assertEqual(self.client.post(f"/api/exams/{exam_id}/submit", json=data).status_code, 400)
        for question_id in ([], {}, True, None, "fake"):
            self.assertEqual(self.client.put(f"/api/exams/{exam_id}/answers", json={"question_id": question_id, "option": 0}).status_code, 400)
        self.assertEqual(self.client.post("/api/exams", data="nickname=test").status_code, 415)

    def test_timeout_uses_only_predeadline_saved_answers(self):
        with patch("app.time.time", return_value=1_000_000):
            exam_id = self.create()
            qs = self.snapshot(exam_id)
            self.client.put(f"/api/exams/{exam_id}/answers", json={"question_id": qs[0]["id"], "option": qs[0]["answer"]})
        with patch("app.time.time", return_value=1_000_000 + EXAM_SECONDS):
            self.assertEqual(self.submit(exam_id, self.correct_answers(exam_id)).status_code, 200)
            output = self.client.get("/api/results/" + exam_id).json
        self.assertEqual((output["correct"], output["unanswered"], output["duration"]), (1, 39, EXAM_SECONDS))
        self.assertEqual(output["finish_reason"], "timeout")

    def test_history_settles_expired_attempts_without_scheduler(self):
        with patch("app.time.time", return_value=1_000_000):
            self.create()
        with patch("app.time.time", return_value=1_000_000 + EXAM_SECONDS + 100):
            history = self.client.get("/api/history").json
        self.assertEqual(history["total"], 1)
        self.assertEqual(history["items"][0]["correct"], 0)

    def test_submit_is_idempotent_and_answers_cannot_change_afterward(self):
        exam_id = self.create()
        self.submit(exam_id, self.correct_answers(exam_id))
        self.submit(exam_id, {})
        self.client.put(f"/api/exams/{exam_id}/answers", json={"question_id": self.snapshot(exam_id)[0]["id"], "option": None})
        self.assertEqual(self.client.get("/api/results/" + exam_id).json["correct"], 40)
        self.assertEqual(self.client.get("/api/history").json["total"], 1)

    def test_concurrent_submission_commits_once(self):
        exam_id = self.create()
        cookie = self.client.get_cookie("aicb_visitor").value
        answers = self.correct_answers(exam_id)
        def submit_as_owner(values):
            with self.app.test_client() as client:
                client.set_cookie("aicb_visitor", cookie)
                return client.post(f"/api/exams/{exam_id}/submit", json={"answers": values}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(submit_as_owner, [answers, {}]))
        self.assertEqual(codes, [200, 200])
        self.assertIn(self.client.get("/api/results/" + exam_id).json["correct"], (0, 40))
        self.assertEqual(self.client.get("/api/history").json["total"], 1)

    def test_public_ranking_ties_and_duplicate_nicknames(self):
        def attempt(start, duration, correct, client):
            with patch("app.time.time", return_value=start):
                exam_id = self.create(client, "Trùng tên")
            answers = dict(list(self.correct_answers(exam_id).items())[:correct])
            with patch("app.time.time", return_value=start + duration):
                client.post(f"/api/exams/{exam_id}/submit", json={"answers": answers})
            return exam_id
        first = attempt(1_000_000, 100, 35, self.client)
        second = attempt(1_000_200, 90, 35, self.app.test_client())
        third = attempt(1_000_400, 80, 30, self.app.test_client())
        board = self.app.test_client().get("/api/leaderboard").json
        self.assertEqual([r["id"] for r in board["items"]], [second, first, third])
        self.assertEqual(board["total"], 3)
        self.assertFalse(any("ip_key" in r or "visitor_id" in r for r in board["items"]))
        self.assertEqual(self.client.get("/api/history?q=TRÙNG").json["total"], 3)
        with sqlite3.connect(self.settings["DATABASE"]) as db:
            db.execute("UPDATE attempts SET nickname='Tên riêng', nickname_key='tên riêng' WHERE id=?", (first,))
        self.assertEqual(self.client.get("/api/leaderboard?q=riêng").json["items"][0]["rank"], 2)

    def test_restart_and_new_bank_preserve_historical_snapshot(self):
        exam_id = self.create()
        self.submit(exam_id, self.correct_answers(exam_id))
        with sqlite3.connect(self.settings["DATABASE"]) as db:
            db.execute("UPDATE attempts SET bank_version='older-bank' WHERE id=?", (exam_id,))
        restarted = create_app(self.settings).test_client()
        self.assertEqual(restarted.get("/api/results/" + exam_id).json["correct"], 40)
        self.assertEqual(restarted.get("/api/history").json["total"], 1)
        self.assertEqual(restarted.get("/api/leaderboard").json["total"], 0)

    def test_rate_limit_works_across_visitors_but_ignores_fake_forwarded_ip(self):
        self.app.config["IP_EXAMS_PER_HOUR"] = 2
        self.create()
        self.create(self.app.test_client())
        blocked = self.app.test_client().post("/api/exams", json={"nickname": "Spam"}, headers={"X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        allowed = self.app.test_client().post("/api/exams", json={"nickname": "Khác mạng"}, environ_overrides={"REMOTE_ADDR": "10.0.0.2"})
        self.assertEqual(allowed.status_code, 201)

    def test_cross_site_requests_and_security_headers(self):
        for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.client.post("/api/exams", json={"nickname": "Thử"}, headers=headers).status_code, 403)
        page = self.client.get("/")
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/api/config").headers["Cache-Control"], "no-store")
        cookie = self.client.get_cookie("aicb_visitor")
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "Lax")

    def test_pagination_and_query_validation(self):
        for page in ("0", "-1", "a", "1.2", "9" * 50):
            self.assertEqual(self.client.get("/api/history?page=" + page).status_code, 400)
        self.assertEqual(self.client.get("/api/history?q=" + "x" * 31).status_code, 400)
        self.assertEqual(self.client.get("/api/history?page=999").json["page"], 1)

    def test_generated_secret_is_private_and_survives_restart(self):
        self.settings["SECRET_KEY"] = None
        first = create_app(self.settings)
        second = create_app(self.settings)
        self.assertEqual(first.config["SECRET_KEY"], second.config["SECRET_KEY"])
        self.assertEqual(Path(self.temp.name, "secret.key").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
