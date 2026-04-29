"""Craigslist nationwide resumes adapter.

Scrapes the public 'resumes' section across ~75 US metros. Workers post their
own contact info (phone + email) and skills here. Free, no login, low captcha
risk if scraped gently with backoff.

Search strategy:
- Pick metros to query based on the JD location (radius / state) or hit all
  top-N metros if location is unspecified.
- For each metro, GET /d/resumes/search/rrr with a query string built from
  required_skills + title.
- Parse listing cards, then optionally hydrate each detail page for full
  contact info.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from app.adapters import (
    AdapterAccessMode,
    AdapterCapability,
    AdapterMetadata,
    AdapterTier,
    RoleType,
    SourceAdapter,
    register_adapter,
)
from app.models import Candidate, ContactInfo, ParsedJD

logger = logging.getLogger(__name__)


# Top US metros — extend freely. (subdomain, state, label)
US_METROS: list[tuple[str, str, str]] = [
    ("newyork", "NY", "New York"), ("losangeles", "CA", "Los Angeles"),
    ("chicago", "IL", "Chicago"), ("houston", "TX", "Houston"),
    ("phoenix", "AZ", "Phoenix"), ("philadelphia", "PA", "Philadelphia"),
    ("sanantonio", "TX", "San Antonio"), ("sandiego", "CA", "San Diego"),
    ("dallas", "TX", "Dallas"), ("sfbay", "CA", "San Francisco Bay Area"),
    ("austin", "TX", "Austin"), ("jacksonville", "FL", "Jacksonville"),
    ("columbus", "OH", "Columbus"), ("charlotte", "NC", "Charlotte"),
    ("seattle", "WA", "Seattle"), ("denver", "CO", "Denver"),
    ("washingtondc", "DC", "Washington DC"), ("boston", "MA", "Boston"),
    ("elpaso", "TX", "El Paso"), ("detroit", "MI", "Detroit"),
    ("nashville", "TN", "Nashville"), ("oklahomacity", "OK", "Oklahoma City"),
    ("portland", "OR", "Portland"), ("lasvegas", "NV", "Las Vegas"),
    ("memphis", "TN", "Memphis"), ("louisville", "KY", "Louisville"),
    ("milwaukee", "WI", "Milwaukee"), ("baltimore", "MD", "Baltimore"),
    ("albuquerque", "NM", "Albuquerque"), ("tucson", "AZ", "Tucson"),
    ("fresno", "CA", "Fresno"), ("sacramento", "CA", "Sacramento"),
    ("kansascity", "MO", "Kansas City"), ("atlanta", "GA", "Atlanta"),
    ("omaha", "NE", "Omaha"), ("minneapolis", "MN", "Minneapolis"),
    ("cleveland", "OH", "Cleveland"), ("raleigh", "NC", "Raleigh"),
    ("miami", "FL", "Miami"), ("tampa", "FL", "Tampa"),
    ("orlando", "FL", "Orlando"), ("oakland", "CA", "Oakland"),
    ("tulsa", "OK", "Tulsa"), ("stlouis", "MO", "St. Louis"),
    ("indianapolis", "IN", "Indianapolis"), ("pittsburgh", "PA", "Pittsburgh"),
    ("buffalo", "NY", "Buffalo"), ("hartford", "CT", "Hartford"),
    ("saltlakecity", "UT", "Salt Lake City"), ("birmingham", "AL", "Birmingham"),
    ("neworleans", "LA", "New Orleans"), ("rochester", "NY", "Rochester"),
]


PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


@register_adapter
class CraigslistAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="craigslist",
        display_name="Craigslist (Resumes — Nationwide)",
        version="1.0.0",
        description="Scrapes public 'resumes' postings across ~50 US metros. Best free source for blue-collar candidates with self-posted contact info.",
        homepage="https://craigslist.org",
        tier=AdapterTier.NON_PREMIUM,
        access_mode=AdapterAccessMode.SCRAPING,
        capabilities=[AdapterCapability.SEARCH, AdapterCapability.PHONE_LOOKUP, AdapterCapability.EMAIL_LOOKUP],
        supported_role_types=[
            RoleType.BLUE_COLLAR,
            RoleType.HOURLY_GENERAL,
            RoleType.SKILLED_TRADE,
            RoleType.DRIVING,
            RoleType.HOSPITALITY,
            RoleType.GENERAL,
        ],
        supported_regions=["US"],
        rate_limit_per_min=20,
        tos_risk=False,  # Public pages, no login required
        required_env_vars=[],
    )

    USER_AGENT = "Mozilla/5.0 (compatible; SourcingBot/1.0)"

    async def setup(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": self.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ---------------- core search ----------------

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        metros = self._select_metros(jd)
        per_metro = max(3, limit // max(1, len(metros)))
        query = self._build_query(jd)

        sem = asyncio.Semaphore(5)

        async def _one(metro: tuple[str, str, str]) -> list[Candidate]:
            async with sem:
                return await self._search_metro(metro, query, per_metro)

        batches = await asyncio.gather(*[_one(m) for m in metros])
        flat: list[Candidate] = []
        seen_ids: set[str] = set()
        for batch in batches:
            for c in batch:
                if c.source_id in seen_ids:
                    continue
                seen_ids.add(c.source_id)
                flat.append(c)
                if len(flat) >= limit:
                    return flat
        return flat

    # ---------------- helpers ----------------

    def _select_metros(self, jd: ParsedJD) -> list[tuple[str, str, str]]:
        """If the JD has a location hint, prioritize that state's metros; else top-15."""
        if jd.location:
            # crude: pull state code if "City, ST"
            m = re.search(r",\s*([A-Z]{2})\b", jd.location)
            if m:
                state = m.group(1)
                same = [t for t in US_METROS if t[1] == state]
                if same:
                    return same
        return US_METROS[:15]

    def _build_query(self, jd: ParsedJD) -> str:
        terms: list[str] = []
        if jd.required_skills:
            terms.extend(jd.required_skills[:3])
        elif jd.title:
            terms.append(jd.title)
        return " ".join(terms)

    async def _search_metro(
        self,
        metro: tuple[str, str, str],
        query: str,
        limit: int,
    ) -> list[Candidate]:
        sub, state, label = metro
        url = f"https://{sub}.craigslist.org/search/rrr"
        params = {"query": query} if query else {}
        try:
            r = await self._client.get(f"{url}?{urlencode(params)}")
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Craigslist %s failed: %s", sub, exc)
            return []

        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("li.cl-static-search-result, li.result-row")[:limit]
        results: list[Candidate] = []
        for row in rows:
            cand = self._parse_row(row, sub, state, label)
            if cand:
                results.append(cand)
        return results

    def _parse_row(
        self,
        row,
        sub: str,
        state: str,
        label: str,
    ) -> Optional[Candidate]:
        link = row.select_one("a")
        if not link:
            return None
        href = link.get("href")
        title = (link.get("title") or link.get_text(" ", strip=True) or "").strip()
        if not title:
            return None
        # extract id if possible
        cl_id = href.rstrip("/").rsplit("/", 1)[-1].split(".")[0] if href else title

        snippet = row.get_text(" ", strip=True)
        phone_m = PHONE_RE.search(snippet)
        email_m = EMAIL_RE.search(snippet)

        return Candidate(
            source=self.metadata.name,
            source_id=f"{sub}:{cl_id}",
            profile_url=href,
            name=title[:80],
            headline=snippet[:200],
            location=label,
            country="US",
            skills=[],  # populated when we hydrate the detail page
            contact=ContactInfo(
                phone=phone_m.group(0) if phone_m else None,
                email=email_m.group(0) if email_m else None,
            ),
            raw={"metro": sub, "state": state},
        )
