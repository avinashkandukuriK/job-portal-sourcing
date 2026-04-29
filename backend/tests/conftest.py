"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make `app.*` importable when running from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Disable Supabase by default — unit tests should never hit a live DB
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_KEY", "")


@pytest.fixture
def tmp_toggle_store(tmp_path: Path):
    """Fresh JSON-file toggle store for each test."""
    from app.adapters.toggle_store import JSONFileToggleStore, reset_toggle_store
    reset_toggle_store()
    yield JSONFileToggleStore(tmp_path / "toggles.json")
    reset_toggle_store()


@pytest.fixture
def whitecap_jd_text() -> str:
    return """
I have a need for White Cap Albuquerque, NM. Can you help?

Job Details:
1. Client: White Cap / Dayton Superior
2. Report to address: 6707 Washington St NE, Albuquerque, NM
3. Position: Forklift
4. Temps needed: 1
5. Pay Rate: 20
6. Conversion hours: 400
7. Background check: yes – federal and county level
8. Drug Test: yes – 4 panel
9. I-9 Required: Yes
10. Everify Required Y/N: Y
11. Shift: 6:30 am – 2:30 pm
12. After offer made before start date would need to sign NDA, Schedule C form, and EHS training confirmation.
13. English speaking and understanding required for safety purposes: Yes

Detailed job description: Operates fork lift to push, pull, lift, stack, tier, or move products,
equipment, or materials in warehouse area. Follows regulatory requirements. May require certification.
Pulls material, loads trucks, assists with counter orders.
"""
