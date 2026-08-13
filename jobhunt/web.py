"""Local web control plane for the jobhunt agent.

The API intentionally exposes profile and search configuration, but never reads
or returns values from ``.env``. Run it on localhost unless you put it behind
authentication and TLS.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import Store

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
CONFIG_PATH = ROOT / "config.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing {path.name}") from exc
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid {path.name}: {exc}") from exc


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid {path.name}: {exc}") from exc


def _atomic_write(path: Path, text: str) -> None:
    """Replace a data file atomically so interrupted saves do not corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _config() -> dict[str, Any]:
    return _read_yaml(CONFIG_PATH)


def _configured_path(key: str, fallback: str) -> Path:
    configured = Path(str(_config().get(key, fallback)))
    return configured if configured.is_absolute() else ROOT / configured


def _clean_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if clean and clean.casefold() not in seen:
            result.append(clean)
            seen.add(clean.casefold())
    return result


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    current_title: str = Field(default="", max_length=140)
    years_experience: float = Field(default=0, ge=0, le=60)
    seniority: str = Field(default="entry", max_length=50)
    education: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=2000)
    core_skills: list[str] = Field(default_factory=list, max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=100)
    domains: list[str] = Field(default_factory=list, max_length=100)
    target_titles: list[str] = Field(default_factory=list, max_length=100)
    notable_projects: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("core_skills", "interests", "domains", "target_titles", "notable_projects")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class SearchSettingsPayload(BaseModel):
    include_titles: list[str] = Field(default_factory=list, max_length=100)
    exclude_titles: list[str] = Field(default_factory=list, max_length=100)
    locations: list[str] = Field(default_factory=list, max_length=100)
    allow_remote: bool = True
    max_age_days: int | None = Field(default=30, ge=1, le=365)
    score_threshold: float = Field(default=7, ge=0, le=10)
    max_per_digest: int = Field(default=5, ge=1, le=50)
    screen_batch_size: int = Field(default=8, ge=1, le=50)

    @field_validator("include_titles", "exclude_titles", "locations")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("include_titles", "exclude_titles")
    @classmethod
    def valid_regexes(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid pattern '{pattern}': {exc}") from exc
        return value


class CompanyPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    ats: Literal["greenhouse", "lever", "ashby"]
    slug: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)


class CompaniesPayload(BaseModel):
    companies: list[CompanyPayload] = Field(default_factory=list, max_length=250)

    @field_validator("companies")
    @classmethod
    def unique_boards(cls, companies: list[CompanyPayload]) -> list[CompanyPayload]:
        keys = [(company.ats, company.slug.casefold()) for company in companies]
        if len(keys) != len(set(keys)):
            raise ValueError("Each ATS and slug combination must be unique")
        return companies


class ApplicationPayload(BaseModel):
    applied: bool


class RunPayload(BaseModel):
    mock: bool = False
    keyword_scorer: bool = False
    no_draft: bool = False
    send_email: bool = False
    limit: int | None = Field(default=None, ge=1, le=500)


class PipelineRunner:
    """Run one CLI pipeline at a time and retain a bounded in-memory log."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "logs": [],
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {**self._state, "logs": list(self._state["logs"])}

    def start(self, payload: RunPayload) -> bool:
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._state = {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "finished_at": None,
                "exit_code": None,
                "logs": ["Starting job discovery pipeline…"],
            }
        threading.Thread(target=self._execute, args=(payload,), daemon=True).start()
        return True

    def _append(self, line: str) -> None:
        with self._lock:
            self._state["logs"] = (self._state["logs"] + [line.rstrip()])[-500:]

    def _execute(self, payload: RunPayload) -> None:
        # ``-u`` keeps stdout unbuffered so the dashboard console is genuinely live.
        command = [sys.executable, "-u", "-m", "jobhunt", "run"]
        if payload.mock:
            command.append("--mock")
        if payload.keyword_scorer:
            command.extend(["--scorer", "keyword"])
        if payload.no_draft:
            command.append("--no-draft")
        if payload.send_email:
            command.append("--send")
        if payload.limit:
            command.extend(["--limit", str(payload.limit)])

        exit_code = 1
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                if line.rstrip():
                    self._append(line)
            exit_code = process.wait()
        except Exception as exc:  # pragma: no cover - OS-level failure
            self._append(f"Unable to start pipeline: {type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._state["status"] = "succeeded" if exit_code == 0 else "failed"
                self._state["exit_code"] = exit_code
                self._state["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


runner = PipelineRunner()
app = FastAPI(
    title="Jobhunt Control Room",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception):
    # Avoid leaking filesystem paths or credentials in unexpected errors.
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: request failed"})


def _settings_view(config: dict[str, Any]) -> dict[str, Any]:
    filters = config.get("filters") or {}
    return {
        "include_titles": filters.get("include_titles") or [],
        "exclude_titles": filters.get("exclude_titles") or [],
        "locations": filters.get("locations") or [],
        "allow_remote": bool(filters.get("allow_remote", True)),
        "max_age_days": filters.get("max_age_days"),
        "score_threshold": float(config.get("score_threshold", 7)),
        "max_per_digest": int(config.get("max_per_digest", 5)),
        "screen_batch_size": int(config.get("screen_batch_size", 8)),
    }


def _applications() -> list[dict[str, Any]]:
    rows = _read_json(_configured_path("seen_file", "seen.json"), {})
    if not isinstance(rows, dict):
        raise HTTPException(status_code=500, detail="seen.json must contain an object")
    result = [{"job_id": job_id, **row} for job_id, row in rows.items()]
    return sorted(result, key=lambda row: row.get("first_seen") or "", reverse=True)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    config = _config()
    profile_path = _configured_path("profile_file", "profile.json")
    companies_path = _configured_path("companies_file", "companies.yaml")
    store = Store(_configured_path("seen_file", "seen.json"))
    return {
        "profile": _read_json(profile_path, {}),
        "settings": _settings_view(config),
        "companies": _read_yaml(companies_path).get("companies") or [],
        "applications": _applications(),
        "stats": store.stats(),
        "run": runner.snapshot(),
    }


@app.put("/api/profile")
def save_profile(payload: ProfilePayload) -> dict[str, Any]:
    path = _configured_path("profile_file", "profile.json")
    profile = payload.model_dump(mode="json")
    _atomic_write(path, json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
    return {"profile": profile, "message": "Profile saved"}


@app.put("/api/settings")
def save_settings(payload: SearchSettingsPayload) -> dict[str, Any]:
    config = _config()
    filters = config.setdefault("filters", {})
    filters.update({
        "include_titles": payload.include_titles,
        "exclude_titles": payload.exclude_titles,
        "locations": payload.locations,
        "allow_remote": payload.allow_remote,
        "max_age_days": payload.max_age_days,
    })
    config.update({
        "score_threshold": payload.score_threshold,
        "max_per_digest": payload.max_per_digest,
        "screen_batch_size": payload.screen_batch_size,
    })
    _atomic_write(CONFIG_PATH, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    return {"settings": _settings_view(config), "message": "Search preferences saved"}


@app.put("/api/companies")
def save_companies(payload: CompaniesPayload) -> dict[str, Any]:
    path = _configured_path("companies_file", "companies.yaml")
    companies = [company.model_dump() for company in payload.companies]
    _atomic_write(path, yaml.safe_dump({"companies": companies}, sort_keys=False, allow_unicode=True))
    return {"companies": companies, "message": "Company watchlist saved"}


@app.patch("/api/applications/{job_id:path}")
def update_application(job_id: str, payload: ApplicationPayload) -> dict[str, Any]:
    store = Store(_configured_path("seen_file", "seen.json"))
    if not store.set_applied(job_id, payload.applied):
        raise HTTPException(status_code=404, detail="Unknown job")
    return {"job": {"job_id": job_id, **store.data[job_id]}, "stats": store.stats()}


@app.post("/api/run", status_code=status.HTTP_202_ACCEPTED)
def start_run(payload: RunPayload) -> dict[str, Any]:
    if not runner.start(payload):
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    return runner.snapshot()


@app.get("/api/run")
def run_status() -> dict[str, Any]:
    return runner.snapshot()


@app.get("/{full_path:path}", include_in_schema=False)
def frontend(full_path: str):
    """Serve the compiled SPA in production and fall back to its index."""
    if not DIST.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend is not built. Run `cd frontend && npm install && npm run build`.",
        )
    candidate = (DIST / full_path).resolve()
    if full_path and candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(DIST / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "jobhunt.web:app",
        host=os.getenv("JOBHUNT_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("JOBHUNT_WEB_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
