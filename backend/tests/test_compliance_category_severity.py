"""Severity of a compliance control's category (compliance_score_endpoints._category_severity).

On 2026-11-18 only 8 of the catalogue's 229 categories were mapped, so the score weighted 1,050 of 1,292
controls as Low (startup log: 222 "unmapped control category" warnings). protects/fails_when/no_claim per test.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import compliance_score_endpoints as score
from seed_compliance_frameworks_a import FRAMEWORKS_PART1
from seed_compliance_frameworks_b import FRAMEWORKS_PART2

CATEGORIES = sorted({c["category"] for f in FRAMEWORKS_PART1 + FRAMEWORKS_PART2 for c in f["controls"]})


def test_every_seeded_category_has_a_severity_of_its_own():
    """protects=each of the 44 seeded frameworks' categories is mapped by name or by a rule, never by the Low
    default; fails_when=a new framework's categories quietly weigh as Low again; no_claim=the weights' fairness"""
    assert len(CATEGORIES) >= 229
    unmapped = [c for c in CATEGORIES if not (score._CATEGORY_SEVERITY.get(c) or score._rule_severity(c))]
    assert unmapped == []


@pytest.mark.parametrize("category,expected", [
    ("Access Control", "Critical"), ("Logical and Physical Access Controls", "Critical"),
    ("Identification & Authentication", "Critical"), ("Cryptographic Failures", "Critical"),
    ("Security Incident Management, E-Discovery and Cloud Forensics", "Critical"), ("Injection", "Critical"),
    ("Physical Security", "Medium"), ("Physical and Environmental Protection", "Medium"),
    ("Logging and Monitoring", "High"), ("Monitoring Activities", "Medium"),
    ("Operations Security", "High"), ("Operations", "Medium"), ("Operational Risk", "Medium"),
    ("Privacy Risk Management", "High"), ("Vulnerability Management", "High"),
    ("Universal Endpoint Management", "High"), ("Business Continuity Management", "High"),
    ("Supply Chain Management, Transparency and Accountability", "Medium"),
    ("Security Policy", "Medium"), ("Security Awareness", "Medium"), ("Information Security", "High"),
    ("Identify", "Medium"), ("Identity", "Critical"), ("Technological", "High"), ("Organizational", "Medium"),
    ("Data for AI", "Medium"), ("MAP", "Medium"), ("Risk Management", "Medium"), ("Audit", "High"),
])
def test_rule_order_settles_the_words_categories_share(category, expected):
    """protects=the first matching group wins (access before physical, physical before protection, logging before
    monitoring, operations security before operations, specific governance words before the generic 'security');
    fails_when=a reordered rule moves a category to the wrong weight; no_claim=-"""
    assert score._category_severity(category) == expected


def test_a_category_nothing_covers_is_low_and_warned_once(caplog):
    """protects=an unknown category still scores (as Low) and is logged once; fails_when=it raises, or floods the
    log on every request; no_claim=-"""
    score._unmapped_categories_warned.discard("Quantum Readiness Annex")
    with caplog.at_level(logging.WARNING, logger="compliance_score_endpoints"):
        assert score._category_severity("Quantum Readiness Annex") == "Low"
        assert score._category_severity("Quantum Readiness Annex") == "Low"
    assert sum("Quantum Readiness Annex" in r.getMessage() for r in caplog.records) == 1
