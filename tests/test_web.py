import json
import time

import yaml
from fastapi.testclient import TestClient

from jobhunt import web


ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct-horse-battery-staple"


def web_client(tmp_path, monkeypatch, *, legacy_cp1252=False):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "filters": {
            "role_filters": ["Software Engineer"],
            "exclude_titles": [r"\bsenior\b"],
            "locations": ["bengaluru"],
            "allow_remote": True,
            "max_age_days": 30,
        },
        "score_threshold": 7,
        "max_per_digest": 5,
        "screen_batch_size": 8,
        "profile_file": str(tmp_path / "profile.json"),
        "companies_file": str(tmp_path / "companies.yaml"),
        "seen_file": str(tmp_path / "seen.json"),
    }), encoding="utf-8")
    (tmp_path / "profile.json").write_text(json.dumps({
        "name": "Test Candidate",
        "current_title": "Engineer",
        "years_experience": 1,
        "seniority": "entry",
        "education": "B.Tech",
        "core_skills": ["Python"],
        "domains": [],
        "notable_projects": [],
        "target_titles": ["Software Engineer"],
    }), encoding="utf-8")
    (tmp_path / "companies.yaml").write_text("companies: []\n", encoding="utf-8")
    tracker = {
        "greenhouse:test:1": {
            "first_seen": "2026-08-01T00:00:00+00:00",
            "company": "Test Co",
            "title": "Software Engineer",
            "location": "Türkiye" if legacy_cp1252 else "Bengaluru",
            "url": "https://example.com/job",
            "score": 8,
            "reason": "Strong match",
            "emailed": False,
            "applied": False,
            "applied_on": None,
        }
    }
    if legacy_cp1252:
        (tmp_path / "seen.json").write_bytes(json.dumps(tracker, ensure_ascii=False).encode("cp1252"))
    else:
        (tmp_path / "seen.json").write_text(json.dumps(tracker), encoding="utf-8")

    monkeypatch.setattr(web, "CONFIG_PATH", config_path)
    monkeypatch.setenv("JOBHUNT_DB_PATH", str(tmp_path / "jobhunt.sqlite3"))
    for key in ("DATABASE_URL", "VERCEL", "JOBHUNT_ADMIN_EMAIL", "JOBHUNT_ADMIN_PASSWORD", "JOBHUNT_SETUP_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    web._DATABASES.clear()

    client = TestClient(web.app)
    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["setup_required"] is True
    setup = client.post("/api/auth/setup", json={
        "name": "Test Admin",
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "setup_token": "",
    })
    assert setup.status_code == 200
    return client


def test_bootstrap_requires_login_and_never_exposes_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-leak")
    client = web_client(tmp_path, monkeypatch)

    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["profile"]["name"] == "Test Candidate"
    assert "must-not-leak" not in response.text

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/bootstrap").status_code == 401


def test_profile_save_is_persisted_in_database(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    payload = {
        "name": "Test Candidate",
        "current_title": "Engineer",
        "years_experience": 1,
        "seniority": "entry",
        "education": "B.Tech",
        "summary": "Builds useful things.",
        "core_skills": ["Python", "Python", "  React  "],
        "interests": ["AI agents"],
        "domains": ["Automation"],
        "notable_projects": ["Built an agent"],
        "target_titles": ["AI Engineer"],
    }

    response = client.put("/api/profile", json=payload)
    assert response.status_code == 200
    assert response.json()["profile"]["core_skills"] == ["Python", "React"]
    assert client.get("/api/bootstrap").json()["profile"]["interests"] == ["AI agents"]


def test_role_filters_are_plain_text_and_exclusion_regex_is_validated(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["role_filters"] = [r"\bBackend Engineer\b"]

    accepted = client.put("/api/settings", json=settings)
    assert accepted.status_code == 200
    assert accepted.json()["settings"]["role_filters"] == [r"\bBackend Engineer\b"]

    settings["exclude_titles"] = ["[broken"]
    rejected = client.put("/api/settings", json=settings)
    assert rejected.status_code == 422
    assert "Invalid exclusion pattern" in rejected.text


def test_application_can_be_checked_and_unchecked(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    path = "/api/applications/greenhouse%3Atest%3A1"

    applied = client.patch(path, json={"applied": True})
    reverted = client.patch(path, json={"applied": False})

    assert applied.status_code == 200
    assert applied.json()["stats"]["applied"] == 1
    assert reverted.status_code == 200
    assert reverted.json()["job"]["applied"] is False
    assert reverted.json()["job"]["applied_on"] is None


def test_first_admin_imports_legacy_windows_tracker_encoding(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch, legacy_cp1252=True)
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["applications"][0]["location"] == "Türkiye"


def test_admin_manages_login_and_user_data_is_isolated(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    created = client.post("/api/admin/users", json={
        "name": "Second User",
        "email": "user@example.com",
        "password": "another-secure-password",
        "role": "user",
    })
    assert created.status_code == 201
    user_id = created.json()["user"]["id"]

    users = client.get("/api/admin/users").json()["users"]
    second = next(user for user in users if user["id"] == user_id)
    assert second["data"] == {"tracked": 0, "applied": 0, "companies": 0, "last_run": None}

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "user@example.com", "password": "another-secure-password"}).status_code == 200
    user_bootstrap = client.get("/api/bootstrap").json()
    assert user_bootstrap["profile"]["name"] == ""
    assert user_bootstrap["applications"] == []

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert client.patch(f"/api/admin/users/{user_id}", json={"active": False}).status_code == 200
    client.post("/api/auth/logout")
    disabled = client.post("/api/auth/login", json={"email": "user@example.com", "password": "another-secure-password"})
    assert disabled.status_code == 401


def test_new_run_resets_a_finished_run(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    user_id = client.get("/api/auth/session").json()["user"]["id"]
    web._database().update_user_data(user_id, "run", {
        "status": "failed",
        "started_at": "2026-08-15T00:00:00+00:00",
        "finished_at": "2026-08-15T00:01:00+00:00",
        "exit_code": 1,
        "logs": ["network unavailable"],
    })
    web.runner._states.pop(user_id, None)

    response = client.post("/api/run/new")
    assert response.status_code == 200
    assert response.json() == web._idle_run()


def test_mock_run_completes_in_process_and_persists_results(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    started = client.post("/api/run", json={
        "mock": True,
        "keyword_scorer": True,
        "no_draft": True,
        "send_email": False,
        "limit": None,
    })
    assert started.status_code == 202

    state = started.json()
    for _ in range(100):
        state = client.get("/api/run").json()
        if state["status"] != "running":
            break
        time.sleep(0.03)

    assert state["status"] == "succeeded"
    assert any("funnel:" in line for line in state["logs"])
    assert client.get("/api/bootstrap").json()["stats"]["tracked"] > 0
    assert client.post("/api/run/new").json()["status"] == "idle"


def test_vercel_without_database_returns_actionable_setup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JOBHUNT_DB_PATH", raising=False)
    web._DATABASES.clear()
    client = TestClient(web.app)

    health = client.get("/api/health")
    session = client.get("/api/auth/session")

    assert health.status_code == 200
    assert health.json()["storage"] == "not_configured"
    assert session.status_code == 503
    assert session.json()["code"] == "storage_not_configured"
    assert "DATABASE_URL" in session.json()["detail"]
