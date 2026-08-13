import json

import yaml
from fastapi.testclient import TestClient

from jobhunt import web


def web_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "filters": {
            "include_titles": ["software engineer"],
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
    (tmp_path / "seen.json").write_text(json.dumps({
        "greenhouse:test:1": {
            "first_seen": "2026-08-01T00:00:00+00:00",
            "company": "Test Co",
            "title": "Software Engineer",
            "location": "Bengaluru",
            "url": "https://example.com/job",
            "score": 8,
            "reason": "Strong match",
            "emailed": False,
            "applied": False,
            "applied_on": None,
        }
    }), encoding="utf-8")
    monkeypatch.setattr(web, "CONFIG_PATH", config_path)
    return TestClient(web.app)


def test_bootstrap_never_exposes_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-leak")
    client = web_client(tmp_path, monkeypatch)

    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json()["profile"]["name"] == "Test Candidate"
    assert "must-not-leak" not in response.text


def test_profile_save_adds_editable_interests(tmp_path, monkeypatch):
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
    assert json.loads((tmp_path / "profile.json").read_text())["interests"] == ["AI agents"]


def test_settings_reject_invalid_regex(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["include_titles"] = ["[broken"]

    response = client.put("/api/settings", json=settings)

    assert response.status_code == 422
    assert "Invalid pattern" in response.text


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


def test_bootstrap_reads_legacy_windows_tracker_encoding(tmp_path, monkeypatch):
    client = web_client(tmp_path, monkeypatch)
    seen_path = tmp_path / "seen.json"
    legacy = json.loads(seen_path.read_text(encoding="utf-8"))
    legacy["greenhouse:test:1"]["location"] = "Türkiye"
    seen_path.write_bytes(json.dumps(legacy, ensure_ascii=False).encode("cp1252"))

    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json()["applications"][0]["location"] == "Türkiye"
