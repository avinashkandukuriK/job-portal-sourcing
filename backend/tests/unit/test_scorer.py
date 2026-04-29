"""Scorer tests — must be deterministic and produce reasonable rankings."""
from __future__ import annotations

from app.core.scorer import score_candidate
from app.models import Candidate, ContactInfo, ParsedJD


def _jd(skills, location="Albuquerque, NM", min_yrs=2, country="US"):
    return ParsedJD(
        title="Forklift Operator",
        title_variants=["Forklift Driver"],
        required_skills=skills,
        min_years_experience=min_yrs,
        location=location,
        location_country=country,
    )


def _cand(name, skills, location, country="US", years=3, title="Forklift Operator"):
    return Candidate(
        source="test",
        source_id=name.lower().replace(" ", "_"),
        name=name,
        current_title=title,
        location=location,
        country=country,
        skills=skills,
        years_experience=years,
        contact=ContactInfo(),
    )


def test_perfect_match_scores_high() -> None:
    jd = _jd(["Forklift", "Warehouse"])
    c = _cand("Alice", ["Forklift", "Warehouse"], "Albuquerque, NM")
    s = score_candidate(c, jd)
    assert s.score >= 80


def test_missing_skills_lowers_score() -> None:
    jd = _jd(["Forklift", "Warehouse", "OSHA"])
    c = _cand("Bob", ["Warehouse"], "Albuquerque, NM")
    s = score_candidate(c, jd)
    assert s.score < 80


def test_wrong_country_drops_to_zero_when_not_remote() -> None:
    jd = _jd(["Forklift"])
    c = _cand("Carlos", ["Forklift"], "Toronto, ON", country="CA")
    s = score_candidate(c, jd)
    # location component is 0; total still gets credit from skill+title
    assert s.score_breakdown["location"] == 0.0


def test_deterministic() -> None:
    jd = _jd(["Forklift", "OSHA-10"])
    c = _cand("Dana", ["Forklift", "OSHA-10"], "Albuquerque, NM")
    s1 = score_candidate(c, jd)
    s2 = score_candidate(c, jd)
    assert s1.score == s2.score
    assert s1.reasoning == s2.reasoning


def test_under_experienced_partial_credit() -> None:
    jd = _jd(["Forklift"], min_yrs=5)
    c = _cand("Eve", ["Forklift"], "Albuquerque, NM", years=2)
    s = score_candidate(c, jd)
    assert 0 < s.score_breakdown["experience"] < 100


def test_reasoning_mentions_skill_match() -> None:
    jd = _jd(["Forklift", "OSHA"])
    c = _cand("Frank", ["Forklift"], "Albuquerque, NM")
    s = score_candidate(c, jd)
    assert "1/2" in s.reasoning or "skills" in s.reasoning.lower()
