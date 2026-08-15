"""Authenticated web control plane for the jobhunt agent."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import cli
from .database import Database, SESSION_DAYS, StorageNotConfigured, verify_password

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
CONFIG_PATH = ROOT / "config.yaml"
SESSION_COOKIE = "jobhunt_session"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LOGGER = logging.getLogger("jobhunt.web")

_DATABASES: dict[tuple[str, str, str], Database] = {}
_DATABASES_LOCK = threading.Lock()


def _database() -> Database:
    key = (
        os.getenv("DATABASE_URL", ""),
        os.getenv("JOBHUNT_DB_PATH", ""),
        os.getenv("VERCEL", ""),
    )
    with _DATABASES_LOCK:
        if key not in _DATABASES:
            _DATABASES[key] = Database(ROOT)
        return _DATABASES[key]


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


def _config() -> dict[str, Any]:
    return _read_yaml(CONFIG_PATH)


def _configured_path(config: dict[str, Any], key: str, fallback: str) -> Path:
    configured = Path(str(config.get(key, fallback)))
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


def _clean_email(value: str) -> str:
    value = value.strip().casefold()
    if not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


def _idle_run() -> dict[str, Any]:
    return {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "logs": [],
    }


def _blank_profile() -> dict[str, Any]:
    return {
        "name": "",
        "current_title": "",
        "years_experience": 0,
        "seniority": "entry",
        "education": "",
        "summary": "",
        "core_skills": [],
        "interests": [],
        "domains": [],
        "target_titles": [],
        "notable_projects": [],
    }


def _settings_view(config: dict[str, Any]) -> dict[str, Any]:
    filters = config.get("filters") or {}
    return {
        "role_filters": filters.get("role_filters") or [],
        "exclude_titles": filters.get("exclude_titles") or [],
        "locations": filters.get("locations") or [],
        "allow_remote": bool(filters.get("allow_remote", True)),
        "max_age_days": filters.get("max_age_days"),
        "score_threshold": float(config.get("score_threshold", 7)),
        "max_per_digest": int(config.get("max_per_digest", 5)),
        "screen_batch_size": int(config.get("screen_batch_size", 8)),
    }


def _default_state(*, legacy: bool) -> dict[str, Any]:
    config = _config()
    profile = _blank_profile()
    applications: dict[str, Any] = {}
    if legacy:
        profile.update(_read_json(_configured_path(config, "profile_file", "profile.json"), {}))
        applications = _read_json(_configured_path(config, "seen_file", "seen.json"), {})
    companies_path = _configured_path(config, "companies_file", "companies.yaml")
    companies = _read_yaml(companies_path).get("companies") or []
    return {
        "profile": profile,
        "settings": _settings_view(config),
        "companies": companies,
        "applications": applications if isinstance(applications, dict) else {},
        "run": _idle_run(),
    }


def _application_list(rows: dict[str, Any]) -> list[dict[str, Any]]:
    result = [{"job_id": job_id, **row} for job_id, row in rows.items()]
    return sorted(result, key=lambda row: row.get("first_seen") or "", reverse=True)


def _stats(rows: dict[str, Any]) -> dict[str, int]:
    return {
        "tracked": len(rows),
        "emailed": sum(1 for value in rows.values() if value.get("emailed")),
        "applied": sum(1 for value in rows.values() if value.get("applied")),
    }


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
    role_filters: list[str] = Field(default_factory=list, max_length=100)
    exclude_titles: list[str] = Field(default_factory=list, max_length=100)
    locations: list[str] = Field(default_factory=list, max_length=100)
    allow_remote: bool = True
    max_age_days: int | None = Field(default=30, ge=1, le=365)
    score_threshold: float = Field(default=7, ge=0, le=10)
    max_per_digest: int = Field(default=5, ge=1, le=50)
    screen_batch_size: int = Field(default=8, ge=1, le=50)

    @field_validator("role_filters", "exclude_titles", "locations")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("role_filters")
    @classmethod
    def plain_role_names(cls, value: list[str]) -> list[str]:
        for role in value:
            if len(role) > 120:
                raise ValueError("Role filters must be 120 characters or fewer")
        return value

    @field_validator("exclude_titles")
    @classmethod
    def valid_exclusion_regexes(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid exclusion pattern '{pattern}': {exc}") from exc
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


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return _clean_email(value)


class SetupPayload(LoginPayload):
    name: str = Field(min_length=1, max_length=100)
    setup_token: str = Field(default="", max_length=300)
    password: str = Field(min_length=10, max_length=200)


class AdminUserCreate(LoginPayload):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "user"] = "user"
    password: str = Field(min_length=10, max_length=200)


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    role: Literal["admin", "user"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        return _clean_email(value) if value is not None else None


def _create_user_or_conflict(**kwargs: Any) -> dict[str, Any]:
    try:
        return _database().create_user(**kwargs)
    except Exception as exc:
        message = str(exc).casefold()
        if "unique" in message or "duplicate" in message:
            raise HTTPException(status_code=409, detail="That email address is already in use") from exc
        raise


def _ensure_environment_admin() -> None:
    database = _database()
    if database.user_count():
        return
    email = os.getenv("JOBHUNT_ADMIN_EMAIL", "").strip()
    password = os.getenv("JOBHUNT_ADMIN_PASSWORD", "")
    if email and password:
        if len(password) < 10:
            raise StorageNotConfigured("JOBHUNT_ADMIN_PASSWORD must contain at least 10 characters")
        database.create_user(
            email=_clean_email(email),
            name=os.getenv("JOBHUNT_ADMIN_NAME", "Administrator").strip() or "Administrator",
            password=password,
            role="admin",
            defaults=_default_state(legacy=True),
        )


def _session_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    return _database().user_for_session(token) if token else None


def require_user(request: Request) -> dict[str, Any]:
    user = _session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https" or bool(os.getenv("VERCEL")),
        samesite="lax",
        path="/",
    )


class _LogWriter(io.TextIOBase):
    def __init__(self, callback):
        self.callback = callback
        self.pending = ""

    def write(self, value: str) -> int:
        self.pending += value
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.callback(line)
        return len(value)

    def flush(self) -> None:
        if self.pending.strip():
            self.callback(self.pending)
        self.pending = ""


class PipelineRunner:
    """Run the CLI in-process and persist a separate state for each user."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, dict[str, Any]] = {}

    def snapshot(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(user_id)
            if state is not None:
                return {**state, "logs": list(state["logs"])}
        stored = _database().get_user_data(user_id).get("run") or _idle_run()
        return {**stored, "logs": list(stored.get("logs") or [])}

    def _store(self, user_id: str, state: dict[str, Any]) -> None:
        _database().update_user_data(user_id, "run", state)

    def _append(self, user_id: str, line: str) -> None:
        with self._lock:
            state = self._states[user_id]
            state["logs"] = (state["logs"] + [line.rstrip()])[-500:]

    def start(self, user_id: str, payload: RunPayload) -> bool:
        with self._lock:
            current = self._states.get(user_id)
            if current and current["status"] == "running":
                return False
            persisted = _database().get_user_data(user_id).get("run") or _idle_run()
            if persisted.get("status") == "running" and not self._is_stale(persisted):
                return False
            state = {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "finished_at": None,
                "exit_code": None,
                "logs": ["Starting job discovery pipeline…"],
            }
            self._states[user_id] = state
        self._store(user_id, state)
        if os.getenv("VERCEL"):
            self._execute(user_id, payload)
        else:
            threading.Thread(target=self._execute, args=(user_id, payload), daemon=True).start()
        return True

    @staticmethod
    def _is_stale(state: dict[str, Any]) -> bool:
        try:
            started = datetime.fromisoformat(str(state.get("started_at")))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - started > timedelta(minutes=30)
        except (TypeError, ValueError):
            return True

    def reset(self, user_id: str) -> dict[str, Any]:
        current = self.snapshot(user_id)
        if current["status"] == "running" and not self._is_stale(current):
            raise HTTPException(status_code=409, detail="Wait for the active run to finish")
        state = _idle_run()
        with self._lock:
            self._states[user_id] = state
        self._store(user_id, state)
        return state

    def _execute(self, user_id: str, payload: RunPayload) -> None:
        exit_code = 1
        writer = _LogWriter(lambda line: self._append(user_id, line))
        try:
            data = _database().get_user_data(user_id)
            with tempfile.TemporaryDirectory(prefix="jobhunt-") as temporary:
                workdir = Path(temporary)
                profile_path = workdir / "profile.json"
                companies_path = workdir / "companies.yaml"
                seen_path = workdir / "seen.json"
                config_path = workdir / "config.yaml"
                profile_path.write_text(json.dumps(data["profile"], ensure_ascii=False), encoding="utf-8")
                companies_path.write_text(
                    yaml.safe_dump({"companies": data["companies"]}, sort_keys=False), encoding="utf-8"
                )
                seen_path.write_text(json.dumps(data["applications"], ensure_ascii=False), encoding="utf-8")
                settings = data["settings"]
                run_config = _config()
                run_config["filters"] = {
                    "role_filters": settings["role_filters"],
                    "exclude_titles": settings["exclude_titles"],
                    "locations": settings["locations"],
                    "allow_remote": settings["allow_remote"],
                    "max_age_days": settings["max_age_days"],
                }
                run_config.update({
                    "score_threshold": settings["score_threshold"],
                    "max_per_digest": settings["max_per_digest"],
                    "screen_batch_size": settings["screen_batch_size"],
                    "profile_file": str(profile_path),
                    "companies_file": str(companies_path),
                    "seen_file": str(seen_path),
                    "digest_file": str(workdir / "digest.html"),
                    "tracker_csv": str(workdir / "tracker.csv"),
                })
                config_path.write_text(
                    yaml.safe_dump(run_config, sort_keys=False, allow_unicode=True), encoding="utf-8"
                )
                arguments = ["--config", str(config_path), "run"]
                if payload.mock:
                    arguments.append("--mock")
                if payload.keyword_scorer:
                    arguments.extend(("--scorer", "keyword"))
                if payload.no_draft:
                    arguments.append("--no-draft")
                if payload.send_email:
                    arguments.append("--send")
                if payload.limit:
                    arguments.extend(("--limit", str(payload.limit)))
                from contextlib import redirect_stderr, redirect_stdout
                with redirect_stdout(writer), redirect_stderr(writer):
                    exit_code = cli.main(arguments)
                writer.flush()
                if seen_path.exists():
                    _database().update_user_data(user_id, "applications", _read_json(seen_path, {}))
        except Exception as exc:  # pragma: no cover - OS/provider failures
            LOGGER.exception("Pipeline failed for user %s", user_id)
            writer.write(f"Unable to run pipeline: {type(exc).__name__}: {exc}\n")
            writer.flush()
        finally:
            with self._lock:
                state = self._states[user_id]
                state["status"] = "succeeded" if exit_code == 0 else "failed"
                state["exit_code"] = exit_code
                state["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                finished = {**state, "logs": list(state["logs"])}
            self._store(user_id, finished)


runner = PipelineRunner()
app = FastAPI(title="Jobhunt Control Room", version="2.0.0", docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(SESSION_COOKIE):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse(status_code=403, content={"detail": "Cross-origin request blocked"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(StorageNotConfigured)
async def storage_error(_request: Request, exc: StorageNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(exc), "code": "storage_not_configured"})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    LOGGER.exception("Unhandled request error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Request failed. Check the server logs for the underlying error."},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        storage = _database().kind
    except StorageNotConfigured:
        storage = "not_configured"
    return {"status": "ok" if storage != "not_configured" else "setup_required", "version": app.version, "storage": storage}


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, Any]:
    _ensure_environment_admin()
    user = _session_user(request)
    database = _database()
    return {
        "authenticated": bool(user),
        "setup_required": database.user_count() == 0,
        "setup_token_required": bool(os.getenv("VERCEL")) and not bool(os.getenv("JOBHUNT_ADMIN_PASSWORD")),
        "user": database.public_user(user) if user else None,
    }


@app.post("/api/auth/setup")
def setup(payload: SetupPayload, request: Request, response: Response) -> dict[str, Any]:
    database = _database()
    if database.user_count():
        raise HTTPException(status_code=409, detail="The first administrator already exists")
    if os.getenv("VERCEL"):
        expected = os.getenv("JOBHUNT_SETUP_TOKEN", "")
        if not expected or not secrets.compare_digest(payload.setup_token, expected):
            raise HTTPException(status_code=403, detail="A valid JOBHUNT_SETUP_TOKEN is required")
    user = _create_user_or_conflict(
        email=payload.email,
        name=payload.name,
        password=payload.password,
        role="admin",
        defaults=_default_state(legacy=True),
    )
    token = database.create_session(user["id"])
    _set_session_cookie(response, token, request)
    return {"authenticated": True, "setup_required": False, "setup_token_required": False, "user": database.public_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginPayload, request: Request, response: Response) -> dict[str, Any]:
    database = _database()
    user = database.get_user_by_email(payload.email)
    if not user or not user["active"] or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    token = database.create_session(user["id"])
    _set_session_cookie(response, token, request)
    return {"authenticated": True, "setup_required": False, "setup_token_required": False, "user": database.public_user(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _database().delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "Signed out"}


@app.get("/api/bootstrap")
def bootstrap(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    data = _database().get_user_data(user["id"])
    applications = data.get("applications", {})
    return {
        "profile": data.get("profile", {}),
        "settings": data.get("settings", _settings_view(_config())),
        "companies": data.get("companies", []),
        "applications": _application_list(applications),
        "stats": _stats(applications),
        "run": runner.snapshot(user["id"]),
    }


@app.put("/api/profile")
def save_profile(payload: ProfilePayload, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    profile = payload.model_dump(mode="json")
    _database().update_user_data(user["id"], "profile", profile)
    return {"profile": profile, "message": "Profile saved"}


@app.put("/api/settings")
def save_settings(payload: SearchSettingsPayload, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    settings = payload.model_dump(mode="json")
    _database().update_user_data(user["id"], "settings", settings)
    return {"settings": settings, "message": "Search preferences saved"}


@app.put("/api/companies")
def save_companies(payload: CompaniesPayload, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    companies = [company.model_dump() for company in payload.companies]
    _database().update_user_data(user["id"], "companies", companies)
    return {"companies": companies, "message": "Company watchlist saved"}


@app.patch("/api/applications/{job_id:path}")
def update_application(job_id: str, payload: ApplicationPayload, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    database = _database()
    applications = database.get_user_data(user["id"]).get("applications", {})
    if job_id not in applications:
        raise HTTPException(status_code=404, detail="Unknown job")
    applications[job_id]["applied"] = payload.applied
    applications[job_id]["applied_on"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if payload.applied else None
    )
    database.update_user_data(user["id"], "applications", applications)
    return {"job": {"job_id": job_id, **applications[job_id]}, "stats": _stats(applications)}


@app.post("/api/run", status_code=status.HTTP_202_ACCEPTED)
def start_run(payload: RunPayload, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not runner.start(user["id"], payload):
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    return runner.snapshot(user["id"])


@app.get("/api/run")
def run_status(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return runner.snapshot(user["id"])


@app.post("/api/run/new")
def new_run(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return runner.reset(user["id"])


@app.get("/api/admin/users")
def admin_users(_admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"users": _database().list_users()}


@app.post("/api/admin/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(payload: AdminUserCreate, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    user = _create_user_or_conflict(
        email=payload.email,
        name=payload.name,
        password=payload.password,
        role=payload.role,
        defaults=_default_state(legacy=False),
    )
    return {"user": _database().public_user(user), "message": "User created"}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: AdminUserUpdate, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if not _database().get_user(user_id):
        raise HTTPException(status_code=404, detail="Unknown user")
    changes = payload.model_dump(exclude_unset=True)
    if user_id == admin["id"] and (changes.get("active") is False or changes.get("role") == "user"):
        raise HTTPException(status_code=400, detail="You cannot disable or demote your own account")
    user = _database().update_user(user_id, changes)
    if changes.get("active") is False or changes.get("password"):
        _database().delete_user_sessions(user_id)
    return {"user": _database().public_user(user or {}), "message": "User updated"}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if not _database().delete_user(user_id):
        raise HTTPException(status_code=404, detail="Unknown user")
    return {"message": "User and associated data deleted"}


@app.post("/api/admin/users/{user_id}/reset-data")
def admin_reset_user_data(user_id: str, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if not _database().get_user(user_id):
        raise HTTPException(status_code=404, detail="Unknown user")
    _database().reset_user_data(user_id, _default_state(legacy=False))
    return {"message": "User data reset"}


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
