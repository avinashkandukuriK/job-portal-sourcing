"""GitHub source adapter.

Uses the public GitHub REST API. With a personal access token (PAT) you get
5,000 requests/hour; unauthenticated is 60/hr. Set GITHUB_TOKEN in .env.

Search strategy:
- Build a `users` search query from the parsed JD (location:US + language:X).
- For each hit, fetch the user record + a small slice of their repos to
  derive a skill set from repo languages and topics.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from app.config import get_settings
from app.models import Candidate, ContactInfo, ParsedJD

from .base import SourceAdapter
from .capabilities import (
    AdapterAccessMode,
    AdapterCapability,
    AdapterMetadata,
    AdapterTier,
    RoleType,
)
from .registry import register_adapter

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


# Map common JD skills to a primary GitHub `language:` filter (only one allowed).
PRIMARY_LANGUAGE_MAP = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "kotlin": "Kotlin",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "c++": "C++",
    "c#": "C#",
    "ruby": "Ruby",
    "php": "PHP",
    "scala": "Scala",
    "swift": "Swift",
    "dart": "Dart",
    "elixir": "Elixir",
}


@register_adapter
class GitHubAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="github",
        display_name="GitHub",
        version="1.0.0",
        description="Search public GitHub profiles and infer skills from repositories.",
        homepage="https://github.com",
        tier=AdapterTier.NON_PREMIUM,
        access_mode=AdapterAccessMode.PUBLIC_API,
        capabilities=[AdapterCapability.SEARCH],
        supported_role_types=[RoleType.TECH, RoleType.PROFESSIONAL, RoleType.GENERAL],
        supported_regions=["US", "GLOBAL"],
        rate_limit_per_min=30,
        optional_env_vars=["GITHUB_TOKEN"],
        pii_returned=False,
    )
    name = "github"
    display_name = "GitHub"
    requires_paid_key = False

    def __init__(self) -> None:
        self._settings = get_settings()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        self._client = httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=30.0)

    async def is_enabled(self) -> bool:
        # Always enabled — works unauthenticated too, just heavily rate-limited.
        return True

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        query = self._build_query(jd)
        logger.info("GitHub search: %s", query)
        params: dict[str, str | int] = {
            "q": query,
            "per_page": min(limit, 50),
            "sort": "followers",
            "order": "desc",
        }
        try:
            r = await self._client.get("/search/users", params=params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("GitHub search failed: %s", exc)
            return []

        items = r.json().get("items", [])
        # Hydrate each user (capped concurrency)
        sem = asyncio.Semaphore(5)

        async def _hydrate(login: str) -> Optional[Candidate]:
            async with sem:
                return await self._fetch_candidate(login, jd)

        results = await asyncio.gather(*[_hydrate(it["login"]) for it in items])
        return [c for c in results if c is not None]

    async def aclose(self) -> None:
        await self._client.aclose()

    # -------------------- internals --------------------

    def _build_query(self, jd: ParsedJD) -> str:
        parts: list[str] = []

        # Primary language
        for s in jd.required_skills + jd.nice_to_have_skills:
            lang = PRIMARY_LANGUAGE_MAP.get(s.lower())
            if lang:
                parts.append(f"language:{lang}")
                break

        # Location — GitHub's location: filter is a free-text substring match
        if jd.remote_ok or not jd.location:
            parts.append('location:"United States"')
        else:
            # take just the city/state piece
            loc = jd.location.split(",")[0].strip()
            parts.append(f'location:"{loc}"')

        # Add up to 2 free-text skill keywords (matches bio + repos)
        free_text = [s for s in jd.required_skills if s.lower() not in PRIMARY_LANGUAGE_MAP][:2]
        for kw in free_text:
            parts.append(f'"{kw}"')

        # Activity floor — tweak as needed
        parts.append("followers:>=5")

        return " ".join(parts)

    async def _fetch_candidate(self, login: str, jd: ParsedJD) -> Optional[Candidate]:
        try:
            user_r = await self._client.get(f"/users/{login}")
            user_r.raise_for_status()
            user = user_r.json()

            repos_r = await self._client.get(
                f"/users/{login}/repos",
                params={"per_page": 30, "sort": "pushed", "type": "owner"},
            )
            repos = repos_r.json() if repos_r.status_code == 200 else []
        except httpx.HTTPError as exc:
            logger.debug("Failed to hydrate %s: %s", login, exc)
            return None

        # Skills = languages + topics (deduped)
        skills: list[str] = []
        seen: set[str] = set()
        for repo in repos:
            lang = repo.get("language")
            if lang and lang.lower() not in seen:
                seen.add(lang.lower())
                skills.append(lang)
            for topic in repo.get("topics") or []:
                if topic and topic.lower() not in seen:
                    seen.add(topic.lower())
                    skills.append(topic)
        skills = skills[:30]

        years = _years_from_account_age(user.get("created_at"))
        location = user.get("location")
        country = "US" if location and _looks_us(location) else None

        contact = ContactInfo(
            email=user.get("email"),
            github_url=user.get("html_url"),
            twitter_url=(
                f"https://twitter.com/{user['twitter_username']}"
                if user.get("twitter_username")
                else None
            ),
            personal_url=user.get("blog") or None,
        )

        headline = user.get("bio") or ""
        # Heuristic: pull a job title from the bio if obvious
        current_title = _title_from_bio(headline)
        current_company = (user.get("company") or "").lstrip("@") or None

        return Candidate(
            source=self.name,
            source_id=str(user["id"]),
            profile_url=user.get("html_url"),
            name=user.get("name") or user.get("login") or "Unknown",
            headline=headline[:200] if headline else None,
            current_title=current_title,
            current_company=current_company,
            location=location,
            country=country,
            skills=skills,
            years_experience=years,
            contact=contact,
            raw={
                "login": user.get("login"),
                "followers": user.get("followers"),
                "public_repos": user.get("public_repos"),
            },
        )


# ----------------- helpers -----------------

def _years_from_account_age(created_at: Optional[str]) -> Optional[float]:
    """Heuristic — GitHub account age is a *very* rough proxy for years coding.
    Used only when no other signal is available; the scorer treats it as soft.
    """
    if not created_at:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = datetime.now(timezone.utc) - dt
    return round(delta.days / 365.25, 1)


_US_HINTS = {
    "usa", "us", "united states", "u.s.", "u.s.a.",
    # State abbrevs
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy",
    # major US cities (sample)
    "san francisco", "new york", "seattle", "austin", "boston", "chicago",
    "los angeles", "denver", "atlanta", "dallas", "houston", "miami",
    "portland", "philadelphia", "san diego", "minneapolis",
}


def _looks_us(loc: str) -> bool:
    s = loc.lower()
    return any(re.search(rf"\b{re.escape(h)}\b", s) for h in _US_HINTS)


_TITLE_RE = re.compile(
    r"\b(software engineer|frontend engineer|backend engineer|full[- ]stack engineer|"
    r"data scientist|data engineer|ml engineer|machine learning engineer|"
    r"product designer|ux designer|devops engineer|sre|site reliability engineer|"
    r"engineering manager|cto|founder)\b",
    re.IGNORECASE,
)


def _title_from_bio(bio: Optional[str]) -> Optional[str]:
    if not bio:
        return None
    m = _TITLE_RE.search(bio)
    return m.group(1).title() if m else None
