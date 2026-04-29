"""Stack Overflow source adapter (Stack Exchange API v2.3).

Strategy:
1. Map the JD's first matching skill to a Stack Overflow tag.
2. Pull top answerers for that tag (most signal of expertise).
3. Hydrate each user, keep only US-located ones.
"""
from __future__ import annotations

import asyncio
import logging
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
from .github import _looks_us  # reuse US heuristic
from .registry import register_adapter

logger = logging.getLogger(__name__)

SE_API = "https://api.stackexchange.com/2.3"


# Common JD skills -> SO tags (extend as needed)
SKILL_TO_TAG = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "java": "java",
    "kotlin": "kotlin",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "c++": "c%2b%2b",
    "c#": "c%23",
    "ruby": "ruby",
    "php": "php",
    "scala": "scala",
    "swift": "swift",
    "react": "reactjs",
    "vue": "vue.js",
    "angular": "angular",
    "node.js": "node.js",
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "spring": "spring",
    "spring boot": "spring-boot",
    "rails": "ruby-on-rails",
    "aws": "amazon-web-services",
    "gcp": "google-cloud-platform",
    "azure": "azure",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "tensorflow": "tensorflow",
    "pytorch": "pytorch",
    "pandas": "pandas",
    "numpy": "numpy",
}


@register_adapter
class StackOverflowAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="stackoverflow",
        display_name="Stack Overflow",
        version="1.0.0",
        description="Search Stack Overflow top answerers by skill tag.",
        homepage="https://stackoverflow.com",
        tier=AdapterTier.NON_PREMIUM,
        access_mode=AdapterAccessMode.PUBLIC_API,
        capabilities=[AdapterCapability.SEARCH],
        supported_role_types=[RoleType.TECH, RoleType.PROFESSIONAL, RoleType.GENERAL],
        supported_regions=["US", "GLOBAL"],
        rate_limit_per_min=30,
        optional_env_vars=["STACKEXCHANGE_KEY"],
        pii_returned=False,
    )
    name = "stackoverflow"
    display_name = "Stack Overflow"
    requires_paid_key = False

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = httpx.AsyncClient(base_url=SE_API, timeout=30.0)

    async def is_enabled(self) -> bool:
        return True

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        tag = self._best_tag(jd)
        if not tag:
            logger.info("No Stack Overflow tag mapped for JD skills; skipping")
            return []

        params: dict[str, str | int] = {
            "order": "desc",
            "sort": "reputation",
            "site": "stackoverflow",
            "pagesize": min(limit, 50),
        }
        if self._settings.stackexchange_key:
            params["key"] = self._settings.stackexchange_key

        # `top-answerers/{tag}` requires a period; use `users` with tag filter instead
        url = f"/tags/{tag}/top-answerers/all_time"
        try:
            r = await self._client.get(url, params=params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Stack Overflow search failed: %s", exc)
            return []

        items = r.json().get("items", [])
        # Each item has .user.user_id — fetch user details
        sem = asyncio.Semaphore(5)

        async def _hydrate(item: dict) -> Optional[Candidate]:
            user = item.get("user", {})
            uid = user.get("user_id")
            if not uid:
                return None
            async with sem:
                return await self._fetch_user(uid, tag, jd)

        results = await asyncio.gather(*[_hydrate(it) for it in items])
        return [c for c in results if c is not None]

    async def aclose(self) -> None:
        await self._client.aclose()

    # -------------------- internals --------------------

    def _best_tag(self, jd: ParsedJD) -> Optional[str]:
        for s in jd.required_skills + jd.nice_to_have_skills:
            tag = SKILL_TO_TAG.get(s.lower())
            if tag:
                return tag
        return None

    async def _fetch_user(self, uid: int, tag: str, jd: ParsedJD) -> Optional[Candidate]:
        params: dict[str, str] = {"site": "stackoverflow", "filter": "!9_bDDxJY5"}
        if self._settings.stackexchange_key:
            params["key"] = self._settings.stackexchange_key
        try:
            r = await self._client.get(f"/users/{uid}", params=params)
            r.raise_for_status()
        except httpx.HTTPError:
            return None

        items = r.json().get("items", [])
        if not items:
            return None
        u = items[0]

        location = u.get("location")
        country = "US" if location and _looks_us(location) else None
        # If JD is US-only and we can't confirm US, drop the candidate
        if jd.location_country == "US" and not country and not jd.remote_ok:
            return None

        # Top tags = skills proxy
        skills = await self._top_tags(uid)
        if tag and tag not in [s.lower() for s in skills]:
            skills.insert(0, tag.replace("%2b", "+").replace("%23", "#"))

        contact = ContactInfo(
            personal_url=u.get("website_url") or None,
        )

        return Candidate(
            source=self.name,
            source_id=str(uid),
            profile_url=u.get("link"),
            name=u.get("display_name") or "Unknown",
            headline=u.get("about_me") and u["about_me"][:200] or None,
            location=location,
            country=country,
            skills=skills[:20],
            contact=contact,
            raw={
                "reputation": u.get("reputation"),
                "answer_count": u.get("answer_count"),
                "question_count": u.get("question_count"),
            },
        )

    async def _top_tags(self, uid: int) -> list[str]:
        params: dict[str, str | int] = {"site": "stackoverflow", "pagesize": 20}
        if self._settings.stackexchange_key:
            params["key"] = self._settings.stackexchange_key
        try:
            r = await self._client.get(f"/users/{uid}/top-tags", params=params)
            r.raise_for_status()
            return [t["tag_name"] for t in r.json().get("items", [])]
        except httpx.HTTPError:
            return []
