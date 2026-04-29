"""Blue-collar job description parser.

Tuned for the kinds of JDs your staffing agency actually receives — forklift,
warehouse, drivers, construction, manufacturing, hospitality, healthcare aides.
Extracts: title, certifications, skills, pay rate, shift, location,
compliance requirements (I-9, E-Verify, drug-test panel size, background-check
levels, NDA), and other staffing-agency-specific fields like conversion
hours and temps_needed.

Rule-based + dictionary-driven so it works without an LLM. Swap-in an LLM
parser later behind the same `parse_jd` signature.
"""
from __future__ import annotations

import re
from typing import Optional

from app.models import ComplianceRequirements, JobDescription, ParsedJD

# ============================================================================
# Vocabulary — blue-collar / light-industrial / hourly
# ============================================================================

# Skills (equipment, soft skills, trade tools). Canonical name on right.
SKILL_VOCAB: dict[str, str] = {
    # Material handling
    "forklift": "Forklift",
    "fork lift": "Forklift",
    "fork-lift": "Forklift",
    "lift truck": "Forklift",
    "stand-up forklift": "Stand-up Forklift",
    "sit-down forklift": "Sit-down Forklift",
    "reach truck": "Reach Truck",
    "order picker": "Order Picker",
    "cherry picker": "Cherry Picker",
    "pallet jack": "Pallet Jack",
    "electric pallet jack": "Electric Pallet Jack",
    "scissor lift": "Scissor Lift",
    "boom lift": "Boom Lift",
    "crane": "Crane Operation",
    "rigging": "Rigging",
    # Warehouse / logistics
    "warehouse": "Warehouse",
    "shipping": "Shipping",
    "receiving": "Receiving",
    "loading": "Loading",
    "unloading": "Unloading",
    "picking": "Picking",
    "packing": "Packing",
    "stocking": "Stocking",
    "inventory": "Inventory Management",
    "rf scanner": "RF Scanner",
    "wms": "WMS",
    "sap": "SAP",
    "barcode scanner": "Barcode Scanner",
    "pulling material": "Material Pulling",
    # Driving / transport
    "cdl class a": "CDL Class A",
    "cdl class b": "CDL Class B",
    "cdl class c": "CDL Class C",
    "cdl-a": "CDL Class A",
    "cdl-b": "CDL Class B",
    "hazmat": "Hazmat",
    "tanker": "Tanker Endorsement",
    "doubles/triples": "Doubles/Triples",
    "delivery driver": "Delivery Driver",
    "box truck": "Box Truck",
    "tractor trailer": "Tractor Trailer",
    "dot medical card": "DOT Medical Card",
    # Construction / trades
    "carpentry": "Carpentry",
    "framing": "Framing",
    "drywall": "Drywall",
    "concrete": "Concrete",
    "masonry": "Masonry",
    "roofing": "Roofing",
    "plumbing": "Plumbing",
    "electrical": "Electrical",
    "hvac": "HVAC",
    "welding": "Welding",
    "mig welding": "MIG Welding",
    "tig welding": "TIG Welding",
    "stick welding": "Stick Welding",
    "pipe fitting": "Pipefitting",
    "blueprint reading": "Blueprint Reading",
    "power tools": "Power Tools",
    "hand tools": "Hand Tools",
    # Manufacturing
    "assembly": "Assembly",
    "machine operator": "Machine Operator",
    "cnc": "CNC",
    "lathe": "Lathe",
    "mill": "Mill",
    "press operator": "Press Operator",
    "quality control": "Quality Control",
    "qc": "Quality Control",
    "qa": "Quality Assurance",
    "lean manufacturing": "Lean Manufacturing",
    "six sigma": "Six Sigma",
    "5s": "5S",
    "gmp": "GMP",
    # Hospitality / food service
    "servsafe": "ServSafe",
    "food handler": "Food Handler",
    "line cook": "Line Cook",
    "prep cook": "Prep Cook",
    "dishwasher": "Dishwashing",
    "host": "Host/Hostess",
    "server": "Server",
    "bartender": "Bartender",
    "barista": "Barista",
    "housekeeping": "Housekeeping",
    # Healthcare aides
    "cna": "CNA",
    "ma": "Medical Assistant",
    "phlebotomy": "Phlebotomy",
    "ehr": "EHR",
    "epic": "Epic",
    "cerner": "Cerner",
    "vital signs": "Vital Signs",
    "patient care": "Patient Care",
    "first aid": "First Aid",
    "cpr": "CPR",
    "bls": "BLS",
    # Office / customer service
    "data entry": "Data Entry",
    "10-key": "10-Key",
    "ms office": "MS Office",
    "excel": "Excel",
    "customer service": "Customer Service",
    "call center": "Call Center",
    "bilingual": "Bilingual",
    "spanish speaking": "Spanish-Speaking",
    "english speaking": "English-Speaking",
    # Soft / safety
    "osha": "OSHA",
    "safety": "Safety",
    "ppe": "PPE",
    "team player": "Teamwork",
    "reliable": "Reliability",
    "on time": "Punctuality",
    "physical": "Physical Stamina",
}

# Certifications (separate from skills; tracked in the certifications table)
CERT_VOCAB: dict[str, str] = {
    "osha-10": "OSHA-10",
    "osha 10": "OSHA-10",
    "osha-30": "OSHA-30",
    "osha 30": "OSHA-30",
    "forklift certified": "Forklift Certification",
    "forklift cert": "Forklift Certification",
    "powered industrial truck": "Forklift Certification",
    "cdl class a": "CDL Class A",
    "cdl class b": "CDL Class B",
    "cdl class c": "CDL Class C",
    "hazmat endorsement": "Hazmat Endorsement",
    "tanker endorsement": "Tanker Endorsement",
    "doubles/triples endorsement": "Doubles/Triples Endorsement",
    "twic": "TWIC Card",
    "servsafe": "ServSafe Certification",
    "food handler card": "Food Handler Card",
    "cpr certification": "CPR Certification",
    "bls": "BLS Certification",
    "first aid": "First Aid Certification",
    "ekg": "EKG Certification",
    "phlebotomy certification": "Phlebotomy Certification",
    "ehs training": "EHS Training",
    "lockout/tagout": "Lockout/Tagout",
    "loto": "Lockout/Tagout",
    "fall protection": "Fall Protection",
    "scaffold": "Scaffold Safety",
}

# Title heads — order matters (longest match wins)
TITLE_HEADS = [
    # warehouse / industrial
    "Forklift Operator", "Lift Truck Operator", "Reach Truck Operator",
    "Order Picker", "Material Handler", "Warehouse Associate",
    "Warehouse Worker", "Shipping Clerk", "Receiving Clerk",
    "Inventory Clerk", "Stocker", "Loader", "Unloader",
    "Picker/Packer", "Picker", "Packer", "Production Worker",
    "Production Associate", "Machine Operator", "Press Operator",
    "Assembly Worker", "Assembler", "Quality Inspector",
    "QC Inspector", "Forklift Driver",
    # driving
    "CDL Driver", "Class A Driver", "Class B Driver",
    "Delivery Driver", "Truck Driver", "Box Truck Driver",
    "Local Driver", "Route Driver", "OTR Driver", "Owner Operator",
    # trades
    "Carpenter", "Apprentice Carpenter", "Electrician",
    "Apprentice Electrician", "Plumber", "Apprentice Plumber",
    "HVAC Technician", "HVAC Installer", "Welder", "Pipefitter",
    "Mason", "Roofer", "Drywall Finisher", "Painter",
    "Construction Laborer", "General Laborer", "Demolition Laborer",
    # manufacturing
    "CNC Operator", "CNC Machinist", "Maintenance Technician",
    "Industrial Mechanic", "Forklift Mechanic",
    # hospitality / food
    "Line Cook", "Prep Cook", "Dishwasher", "Server", "Host",
    "Bartender", "Barista", "Housekeeper", "Janitor",
    "Custodian", "Cleaner",
    # healthcare aides
    "Certified Nursing Assistant", "Medical Assistant",
    "Patient Care Tech", "Home Health Aide", "Caregiver",
    "Phlebotomist",
    # office / cs (light)
    "Data Entry Clerk", "Customer Service Rep", "Call Center Agent",
    "Receptionist", "Office Assistant", "Administrative Assistant",
]


# ============================================================================
# Patterns
# ============================================================================

# "$20", "$15.50/hr", "20 per hour", "20.00/hr", "Pay Rate: 20"
PAY_RATE_PATTERNS = [
    re.compile(r"\$\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:/\s*hr|per\s*hour|hourly|/h\b)?", re.IGNORECASE),
    re.compile(r"\bpay\s*rate[:\s]+\$?\s*(\d{1,3}(?:\.\d{1,2})?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3}(?:\.\d{1,2})?)\s*(?:/\s*hr|per\s*hour|hourly|an\s*hour)\b", re.IGNORECASE),
]

# Years of experience: "5 years", "5+ years", "3-5 years", "2 yrs"
YEARS_RANGE_RE = re.compile(r"(\d{1,2})\s*[-to]+\s*(\d{1,2})\s*(?:yrs?|years?)\s*(?:of\s+)?(?:experience|exp)?", re.IGNORECASE)
YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:yrs?|years?)\s*(?:of\s+)?(?:experience|exp)?", re.IGNORECASE)

# Shift: "6:30 am - 2:30 pm", "1st shift", "Day Shift", "Night Shift", "Mon-Fri"
SHIFT_PATTERNS = [
    re.compile(r"\b(\d{1,2}:?\d{0,2}\s*(?:am|pm)\s*[-–to]+\s*\d{1,2}:?\d{0,2}\s*(?:am|pm))\b", re.IGNORECASE),
    re.compile(r"\b(1st|2nd|3rd|first|second|third)\s*shift\b", re.IGNORECASE),
    re.compile(r"\b(day|night|swing|graveyard|overnight|weekend)\s*shift\b", re.IGNORECASE),
]

# Drug test panel: "4 panel", "4-panel", "5 panel", "10 panel"
DRUG_TEST_PANEL_RE = re.compile(r"(\d{1,2})\s*[-]?\s*panel", re.IGNORECASE)

# Background check levels
BG_FEDERAL_RE = re.compile(r"\bfederal\b", re.IGNORECASE)
BG_COUNTY_RE = re.compile(r"\bcounty\b", re.IGNORECASE)
BG_STATE_RE = re.compile(r"\bstate(?:wide)?\b", re.IGNORECASE)

# Compliance flags
I9_RE = re.compile(r"\bi[-\s]?9\b", re.IGNORECASE)
EVERIFY_RE = re.compile(r"\be[-\s]?verify\b", re.IGNORECASE)
NDA_RE = re.compile(r"\bnda\b|non[-\s]disclosure", re.IGNORECASE)
SCHEDULE_C_RE = re.compile(r"schedule\s*c", re.IGNORECASE)
EHS_RE = re.compile(r"\behs\b|environmental\s+health", re.IGNORECASE)
DRUG_TEST_RE = re.compile(r"drug\s*(?:test|screen)", re.IGNORECASE)
BG_CHECK_RE = re.compile(r"background\s*check", re.IGNORECASE)
BILINGUAL_RE = re.compile(r"\bbilingual\b|english\s+(?:speaking|required)|spanish\s+speaking", re.IGNORECASE)

# Conversion / temp-to-perm: "Conversion hours: 400", "after 400 hours"
CONVERSION_HOURS_RE = re.compile(r"conversion\s*(?:hours?)?[:\s]+(\d{2,5})", re.IGNORECASE)

# Temps needed: "1 temp needed", "Temps needed: 3"
TEMPS_NEEDED_RE = re.compile(r"temps?\s*needed[:\s]+(\d{1,3})", re.IGNORECASE)

# Location: "Albuquerque, NM", "Remote"
LOCATION_RE = re.compile(
    r"\b("
    r"(?:[A-Z][a-zA-Z\.\- ]+,\s*[A-Z]{2})"
    r"|(?:Remote(?:[- ]US)?)"
    r"|(?:United States|USA)"
    r")"
)
ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
ADDRESS_LIKE_RE = re.compile(r"\d+\s+[\w\s,.\-]+\b(?:NE|NW|SE|SW|St|Ave|Blvd|Rd|Dr|Ln|Way)\b", re.IGNORECASE)

REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)


# ============================================================================
# Public API
# ============================================================================

def parse_jd(jd: JobDescription) -> ParsedJD:
    """Parse a raw JD into a structured query."""
    text = jd.text or ""
    if not text.strip():
        raise ValueError("Empty job description")

    title = _extract_title(text, jd.title_hint)
    skills_required, skills_nice = _extract_skills(text)
    certs = _extract_certs(text)
    pay_rate = _extract_pay_rate(text)
    min_years, max_years = _extract_years(text)
    shift = _extract_shift(text)
    location, remote_ok, zip_code, state = _extract_location(text)
    title_variants = _title_variants(title)
    compliance = ComplianceRequirements(**_extract_compliance(text))
    conversion_hours = _extract_conversion_hours(text)
    temps_needed = _extract_temps_needed(text)
    bilingual = bool(BILINGUAL_RE.search(text))

    keywords: list[str] = []
    if bilingual:
        keywords.append("Bilingual")

    return ParsedJD(
        title=title,
        title_variants=title_variants,
        required_skills=skills_required,
        nice_to_have_skills=skills_nice,
        required_certs=certs,                                # NEW (added below in models)
        pay_rate=pay_rate,
        pay_rate_unit="hourly" if pay_rate else None,
        min_years_experience=min_years,
        max_years_experience=max_years,
        seniority=None,
        location=location,
        location_country="US",
        zip=zip_code,
        state=state,
        remote_ok=remote_ok,
        shift=shift,
        conversion_hours=conversion_hours,
        temps_needed=temps_needed,
        compliance=compliance,
        keywords=keywords,
    )


# ============================================================================
# Helpers
# ============================================================================

def _extract_title(text: str, hint: Optional[str]) -> str:
    if hint:
        return hint.strip()
    head = text[:600]
    # Prefer explicit "Position: <title>" line
    m = re.search(r"\bposition[:\s]+([^\n]{2,80})", head, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip(" -:")
        if candidate:
            return candidate
    # Fallback to title-head lookup
    for raw in sorted(TITLE_HEADS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(raw)}\b", head, re.IGNORECASE):
            return raw
    for raw in sorted(TITLE_HEADS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(raw)}\b", text, re.IGNORECASE):
            return raw
    # last resort: first non-empty line
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Unknown Role")
    return first_line[:80]


def _title_variants(title: str) -> list[str]:
    t = title.lower()
    variants = {title}
    pairs = [
        ("forklift operator", ["forklift driver", "lift truck operator", "fork lift operator"]),
        ("warehouse associate", ["warehouse worker", "warehouse helper"]),
        ("material handler", ["mover", "warehouse worker"]),
        ("cdl driver", ["truck driver", "delivery driver"]),
        ("class a driver", ["cdl class a driver", "cdl-a driver"]),
        ("class b driver", ["cdl class b driver", "cdl-b driver"]),
        ("general laborer", ["construction laborer", "labor", "laborer"]),
        ("line cook", ["cook", "kitchen staff"]),
        ("certified nursing assistant", ["cna", "nursing aide"]),
    ]
    for canonical, alts in pairs:
        if canonical in t:
            variants.update(alts)
    return sorted(variants)


def _extract_skills(text: str) -> tuple[list[str], list[str]]:
    """Returns (required, nice_to_have)."""
    sections = _split_required_vs_nice(text)
    req_text = sections["required"].lower()
    nice_text = sections["nice"].lower()

    required: list[str] = []
    nice: list[str] = []
    seen: set[str] = set()
    for raw, canonical in SKILL_VOCAB.items():
        if canonical in seen:
            continue
        pattern = re.compile(rf"(?<![\w/+\-]){re.escape(raw)}(?![\w/+\-])", re.IGNORECASE)
        in_req = bool(pattern.search(req_text))
        in_nice = bool(pattern.search(nice_text))
        if in_nice and not in_req:
            nice.append(canonical)
            seen.add(canonical)
        elif in_req or pattern.search(text.lower()):
            required.append(canonical)
            seen.add(canonical)
    return required, nice


def _extract_certs(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw, canonical in CERT_VOCAB.items():
        if canonical in seen:
            continue
        if re.search(rf"(?<![\w/+\-]){re.escape(raw)}(?![\w/+\-])", text, re.IGNORECASE):
            out.append(canonical)
            seen.add(canonical)
    return out


def _split_required_vs_nice(text: str) -> dict[str, str]:
    nice_pat = re.compile(
        r"(?im)^\s*(?:nice[- ]to[- ]have|preferred|bonus|plus|good to have)[^\n:]*[:\n]"
    )
    m = nice_pat.search(text)
    if not m:
        return {"required": text, "nice": ""}
    return {"required": text[: m.start()], "nice": text[m.start():]}


def _extract_pay_rate(text: str) -> Optional[float]:
    for pat in PAY_RATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _extract_years(text: str) -> tuple[Optional[float], Optional[float]]:
    m = YEARS_RANGE_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = YEARS_RE.search(text)
    if m:
        return float(m.group(1)), None
    return None, None


def _extract_shift(text: str) -> Optional[str]:
    for pat in SHIFT_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return None


def _extract_location(text: str) -> tuple[Optional[str], bool, Optional[str], Optional[str]]:
    """Returns (location string, remote_ok, zip, state)."""
    remote_ok = bool(REMOTE_RE.search(text))

    # Prefer "Report to address" or explicit address line
    loc_m = LOCATION_RE.search(text)
    location = loc_m.group(1) if loc_m else None
    state = None
    if location:
        sm = re.search(r",\s*([A-Z]{2})\b", location)
        if sm:
            state = sm.group(1)
    zip_m = ZIP_RE.search(text)
    zip_code = zip_m.group(1) if zip_m else None
    return location, remote_ok, zip_code, state


def _extract_compliance(text: str) -> dict:
    panel = None
    panel_m = DRUG_TEST_PANEL_RE.search(text)
    if panel_m:
        try:
            panel = int(panel_m.group(1))
        except ValueError:
            pass

    bg_levels: list[str] = []
    if BG_CHECK_RE.search(text):
        if BG_FEDERAL_RE.search(text):
            bg_levels.append("federal")
        if BG_COUNTY_RE.search(text):
            bg_levels.append("county")
        if BG_STATE_RE.search(text):
            bg_levels.append("state")
        if not bg_levels:
            bg_levels.append("standard")

    return {
        "requires_i9": bool(I9_RE.search(text)),
        "requires_everify": bool(EVERIFY_RE.search(text)),
        "requires_drug_test": bool(DRUG_TEST_RE.search(text)),
        "drug_test_panel": panel,
        "requires_background_check": bool(BG_CHECK_RE.search(text)),
        "background_check_levels": bg_levels,
        "requires_nda": bool(NDA_RE.search(text)),
        "requires_schedule_c": bool(SCHEDULE_C_RE.search(text)),
        "requires_ehs_training": bool(EHS_RE.search(text)),
    }


def _extract_conversion_hours(text: str) -> Optional[int]:
    m = CONVERSION_HOURS_RE.search(text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _extract_temps_needed(text: str) -> int:
    m = TEMPS_NEEDED_RE.search(text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 1
    return 1
