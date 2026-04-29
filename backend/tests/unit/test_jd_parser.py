"""JD parser tests — the most business-critical pure-logic module."""
from __future__ import annotations

import pytest

from app.core.jd_parser import parse_jd
from app.models import JobDescription


def test_parses_white_cap_jd(whitecap_jd_text: str) -> None:
    parsed = parse_jd(JobDescription(text=whitecap_jd_text))

    assert "Forklift" in parsed.title or parsed.title == "Forklift Operator"
    assert parsed.pay_rate == 20.0
    assert parsed.pay_rate_unit == "hourly"
    assert parsed.location and "Albuquerque" in parsed.location
    assert parsed.state == "NM"
    assert parsed.temps_needed == 1
    assert parsed.conversion_hours == 400
    assert parsed.shift is not None and "6:30" in parsed.shift

    c = parsed.compliance
    assert c.requires_i9 is True
    assert c.requires_everify is True
    assert c.requires_drug_test is True
    assert c.drug_test_panel == 4
    assert c.requires_background_check is True
    assert "federal" in c.background_check_levels
    assert "county" in c.background_check_levels
    assert c.requires_nda is True
    assert c.requires_schedule_c is True
    assert c.requires_ehs_training is True


def test_extracts_forklift_skill(whitecap_jd_text: str) -> None:
    parsed = parse_jd(JobDescription(text=whitecap_jd_text))
    assert "Forklift" in parsed.required_skills


def test_empty_jd_raises() -> None:
    with pytest.raises(ValueError):
        parse_jd(JobDescription(text=""))


def test_cdl_driver_jd_extracts_class_a() -> None:
    text = """
    Class A Driver needed in Dallas, TX. CDL Class A required, hazmat endorsement preferred.
    Pay: $25/hr. 2+ years experience. Drug test 5-panel required.
    """
    parsed = parse_jd(JobDescription(text=text))
    assert "CDL Class A" in parsed.required_skills or "CDL Class A" in parsed.required_certs
    assert parsed.pay_rate == 25.0
    assert parsed.compliance.drug_test_panel == 5
    assert parsed.state == "TX"


def test_warehouse_associate_jd() -> None:
    text = """
    Warehouse Associate. Phoenix, AZ. $17 per hour.
    Picking, packing, stocking. Must be able to lift 50 lbs.
    Forklift certification a plus.
    """
    parsed = parse_jd(JobDescription(text=text))
    assert parsed.pay_rate == 17.0
    assert "Warehouse" in parsed.required_skills or "Picking" in parsed.required_skills


def test_title_hint_overrides() -> None:
    text = "Some role in NYC. $20/hr."
    parsed = parse_jd(JobDescription(text=text, title_hint="Custom Title"))
    assert parsed.title == "Custom Title"


def test_remote_flag() -> None:
    text = "Customer Service Rep. Remote, US. $18/hr."
    parsed = parse_jd(JobDescription(text=text))
    assert parsed.remote_ok is True


def test_no_drug_test_section_returns_false() -> None:
    text = "Carpenter. Boston, MA. $30/hr. Must have own tools."
    parsed = parse_jd(JobDescription(text=text))
    assert parsed.compliance.requires_drug_test is False
    assert parsed.compliance.drug_test_panel is None
