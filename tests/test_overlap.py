"""R007 and R018 firing on the same SDK symbol collapse into one finding.

#221: `CreateMessageResultSchema` trips both DeprecatedCoreFeatures (R007,
deprecated) and MultiRoundTripReplacesServerInitiated (R018, breaking) on
the same line. Both claims are true, but showing two contradicting
severities for one symbol is noise, not signal.
"""
from __future__ import annotations

from pathlib import Path

from mcp_migrate.cli import run_check_detailed
from mcp_migrate.overlap import dedupe
from mcp_migrate.rules.base import Finding
from mcp_migrate.rules.r007_deprecated_features import DeprecatedCoreFeatures
from mcp_migrate.rules.r018_multi_round_trip_replaces_server_initiated import (
    MultiRoundTripReplacesServerInitiated,
)

RULES = {"R007": DeprecatedCoreFeatures(), "R018": MultiRoundTripReplacesServerInitiated()}


def test_overlapping_pair_merges_into_the_more_severe_finding():
    same_spot = [
        Finding(rule_id="R007", message="Sampling is deprecated; plan a migration.",
                path=Path("a.py"), line=2, snippet="x"),
        Finding(rule_id="R018", message="Server-initiated sampling/createMessage was replaced.",
                path=Path("a.py"), line=2, snippet="x"),
    ]
    out = dedupe(same_spot, RULES)
    assert len(out) == 1
    assert out[0].rule_id == "R018"
    assert "Server-initiated sampling/createMessage was replaced." in out[0].message
    assert "Also flagged by R007: Sampling is deprecated; plan a migration." in out[0].message


def test_merge_order_does_not_matter():
    # R018 discovered first this time -- the winner should still be R018,
    # not whichever rule happened to run first.
    same_spot = [
        Finding(rule_id="R018", message="breaking claim", path=Path("a.py"), line=5),
        Finding(rule_id="R007", message="deprecated claim", path=Path("a.py"), line=5),
    ]
    out = dedupe(same_spot, RULES)
    assert len(out) == 1
    assert out[0].rule_id == "R018"


def test_unrelated_rules_on_the_same_line_are_left_alone():
    # R007 and R011 aren't a known overlapping pair -- coincidentally
    # sharing a line is not evidence they describe the same symbol.
    findings = [
        Finding(rule_id="R007", message="deprecated claim", path=Path("a.py"), line=3),
        Finding(rule_id="R011", message="unrelated claim", path=Path("a.py"), line=3),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_findings_at_different_locations_are_never_merged():
    findings = [
        Finding(rule_id="R007", message="deprecated claim", path=Path("a.py"), line=3),
        Finding(rule_id="R018", message="breaking claim", path=Path("a.py"), line=9),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_project_level_findings_without_a_line_pass_through():
    findings = [
        Finding(rule_id="R007", message="no location"),
        Finding(rule_id="R018", message="also no location"),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_check_reports_one_finding_for_the_issue_221_repro(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.types import CreateMessageResultSchema\n"
        "sampler = CreateMessageResultSchema\n"
    )
    result = run_check_detailed(tmp_path)
    hits = [f for f in result.findings if f.line == 2]
    assert len(hits) == 1, f"expected one merged finding on line 2, got {hits}"
    assert hits[0].rule_id == "R018"
    assert "Also flagged by R007" in hits[0].message
