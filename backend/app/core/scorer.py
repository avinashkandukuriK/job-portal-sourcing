"""Boolean + keyword scorer.

Produces a 0-100 match score for a candidate against a parsed JD, plus a short
human-readable reasoning string. Designed to be replaced (or layered with) an
embedding/LLM scorer later. Keep the signature stable.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from app.models import Candidate, ParsedJD, ScoredCandidate

# Component weights — must sum to 1.0
WEIGHTS = {
    "required_skills": 0.55,
    "nice_to_have_skills": 0.10,
    "title_match": 0.15,
    "experience": 0.10,
    "location": 0.10,
}


def score_candidate(candidate: Candidate, jd: ParsedJD) -> ScoredCandidate:
    breakdown: dict[str, float] = {}
    reasons: list[str] = []

    breakdown["required_skills"] = _score_skill_set(candidate.skills, jd.required_skills)
    breakdown["nice_to_have_skills"] = _score_skill_set(candidate.skills, jd.nice_to_have_skills)
    breakdown["title_match"] = _score_title(candidate, jd)
    breakdown["experience"] = _score_experience(candidate, jd)
    breakdown["location"] = _score_location(candidate, jd)

    raw = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)
    score = round(raw * 100, 1)

    reasons.append(_skill_reason(candidate, jd))
    if jd.title:
        reasons.append(_title_reason(candidate, jd))
    if jd.min_years_experience is not None:
        reasons.append(_experience_reason(candidate, jd))
    if jd.location:
        reasons.append(_location_reason(candidate, jd))

    return ScoredCandidate(
        candidate=candidate,
        score=score,
        score_breakdown={k: round(v * 100, 1) for k, v in breakdown.items()},
        reasoning=" • ".join(r for r in reasons if r),
    )


# ---------------- component scorers ----------------

def _score_skill_set(candidate_skills: list[str], target: list[str]) -> float:
    if not target:
        return 1.0  # nothing to match against → neutral full credit
    if not candidate_skills:
        return 0.0
    cand_lc = {s.lower() for s in candidate_skills}
    hits = sum(1 for s in target if s.lower() in cand_lc)
    return hits / len(target)


def _score_title(candidate: Candidate, jd: ParsedJD) -> float:
    targets = [jd.title] + jd.title_variants
    sources = [candidate.current_title or "", candidate.headline or ""]
    best = 0.0
    for t in targets:
        for s in sources:
            if not t or not s:
                continue
            ratio = fuzz.token_set_ratio(t.lower(), s.lower()) / 100.0
            if ratio > best:
                best = ratio
    return best


def _score_experience(candidate: Candidate, jd: ParsedJD) -> float:
    if jd.min_years_experience is None:
        return 1.0
    if candidate.years_experience is None:
        return 0.5  # unknown → partial credit (don't penalize public-profile gaps)
    if candidate.years_experience >= jd.min_years_experience:
        # diminishing returns past the requirement
        return min(1.0, 0.7 + (candidate.years_experience - jd.min_years_experience) * 0.05)
    # under-experienced — scale linearly
    return max(0.0, candidate.years_experience / jd.min_years_experience)


def _score_location(candidate: Candidate, jd: ParsedJD) -> float:
    # Country-level filter first (project is US-focused)
    if jd.location_country and candidate.country and candidate.country.upper() != jd.location_country.upper():
        return 0.0 if not jd.remote_ok else 0.4

    if not jd.location:
        return 1.0

    cand_loc = (candidate.location or "").lower()
    if not cand_loc:
        return 0.5

    target = jd.location.lower()
    if target in cand_loc or cand_loc in target:
        return 1.0

    # Partial fuzzy
    return max(0.0, fuzz.partial_ratio(target, cand_loc) / 100.0)


# ---------------- reason text ----------------

def _skill_reason(candidate: Candidate, jd: ParsedJD) -> str:
    if not jd.required_skills:
        return ""
    cand_lc = {s.lower() for s in candidate.skills}
    matched = [s for s in jd.required_skills if s.lower() in cand_lc]
    return f"matches {len(matched)}/{len(jd.required_skills)} required skills" + (
        f" ({', '.join(matched[:5])})" if matched else ""
    )


def _title_reason(candidate: Candidate, jd: ParsedJD) -> str:
    title = candidate.current_title or candidate.headline or "no title"
    return f"title: \"{title}\" vs target \"{jd.title}\""


def _experience_reason(candidate: Candidate, jd: ParsedJD) -> str:
    if candidate.years_experience is None:
        return f"experience unknown (req {jd.min_years_experience}+ yrs)"
    return f"{candidate.years_experience:g} yrs exp vs req {jd.min_years_experience:g}+"


def _location_reason(candidate: Candidate, jd: ParsedJD) -> str:
    return f"location: {candidate.location or 'unknown'} vs {jd.location}"
