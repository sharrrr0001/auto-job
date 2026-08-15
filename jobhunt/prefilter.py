"""Deterministic filter that runs BEFORE any LLM call.

This is the whole cost story: ~2000 raw jobs -> ~40 candidates for ~0 rupees,
so the model only reads jobs that already passed role + location + freshness.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .fetch import Job

REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed")


def _any_match(patterns: list[str] | list[str | None], text: str) -> bool:
    normalized = [p for p in (patterns or []) if isinstance(p, str) and p]
    return any(re.search(p, text, re.I) for p in normalized)


def _role_match(roles: list[str], title: str) -> bool:
    """Match user-entered role names without exposing regular expressions."""
    if not roles:
        return True

    def normalized(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9+#]+", value.casefold()))

    title_tokens = set(normalized(title).split())
    return any(
        bool(tokens := normalized(role).split()) and all(token in title_tokens for token in tokens)
        for role in roles
    )


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def prefilter(jobs: list[Job], cfg: dict) -> list[Job]:
    roles = [role for role in (cfg.get("role_filters") or []) if isinstance(role, str)]
    legacy_inc = cfg.get("include_titles") if "role_filters" not in cfg else None
    exc = cfg.get("exclude_titles") or []
    locs = [l.lower() for l in (cfg.get("locations") or [])]
    allow_remote = bool(cfg.get("allow_remote", True))
    max_age = cfg.get("max_age_days")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age) if max_age else None

    kept, stats = [], {"title": 0, "location": 0, "age": 0}
    for j in jobs:
        included = _role_match(roles, j.title) if legacy_inc is None else _any_match(legacy_inc or [r"."], j.title)
        if not included or (exc and _any_match(exc, j.title)):
            stats["title"] += 1
            continue

        if locs:
            hay = f"{j.location} {j.title}".lower()
            is_remote = allow_remote and any(h in hay for h in REMOTE_HINTS)
            if not is_remote and not any(l in hay for l in locs):
                stats["location"] += 1
                continue

        if cutoff:
            posted = _parse_date(j.posted_at)
            if posted and posted < cutoff:
                stats["age"] += 1
                continue

        kept.append(j)

    print(f"  prefilter: {len(jobs)} -> {len(kept)} "
          f"(dropped title={stats['title']} location={stats['location']} stale={stats['age']})")
    return kept
