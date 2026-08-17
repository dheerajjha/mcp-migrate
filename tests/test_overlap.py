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


def test_findings_without_a_feature_at_different_locations_are_never_merged():
    """Without a feature classification there is nothing but the line to
    group on, so the old conservative behavior holds: different lines, no
    merge. (With features, same fact on different lines DOES merge -- that
    is the #221 fix, tested below.)"""
    findings = [
        Finding(rule_id="R007", message="deprecated claim", path=Path("a.py"), line=3),
        Finding(rule_id="R018", message="breaking claim", path=Path("a.py"), line=9),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_same_feature_on_different_lines_merges():
    """#221, the case a line key structurally cannot reach: R007 and R018
    describe the same underlying fact but matched different symbols on
    different lines. The feature -- not the line or the symbol -- is what
    makes it the same fact."""
    findings = [
        Finding(rule_id="R018", message="Server-initiated roots/list was replaced.",
                path=Path("a.py"), line=11, feature="Server-initiated roots/list"),
        Finding(rule_id="R007", message="Roots is deprecated. Use resource URIs instead.",
                path=Path("a.py"), line=12, feature="Roots"),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 1
    assert out[0].rule_id == "R018"
    assert out[0].line == 11  # the more severe rule's earliest line survives
    assert "Roots is deprecated. Use resource URIs instead." in out[0].message


def test_same_feature_repeated_by_both_rules_collapses_to_one():
    """The mcp-server-git shape: R007 fires twice (RootsCapability imports
    and uses) and R018 fires twice (ListRootsResult imports and uses), on
    four different lines -- one underlying fact, four findings. All four
    collapse into one."""
    findings = [
        Finding(rule_id="R018", message="Server-initiated roots/list was replaced.",
                path=Path("server.py"), line=11, feature="Server-initiated roots/list"),
        Finding(rule_id="R007", message="Roots is deprecated.",
                path=Path("server.py"), line=12, feature="Roots"),
        Finding(rule_id="R007", message="Roots is deprecated.",
                path=Path("server.py"), line=464, feature="Roots"),
        Finding(rule_id="R018", message="Server-initiated roots/list was replaced.",
                path=Path("server.py"), line=468, feature="Server-initiated roots/list"),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 1
    assert out[0].rule_id == "R018"
    assert out[0].line == 11
    assert "Also flagged by R007: Roots is deprecated." in out[0].message


def test_same_line_different_features_stay_separate():
    """A busy line naming two features from the same pair is two facts, not
    one. The old line key merged them -- R007's Sampling claim with R018's
    roots/list claim -- a false merge the feature key cannot make."""
    findings = [
        Finding(rule_id="R007", message="Sampling is deprecated.",
                path=Path("a.py"), line=2, feature="Sampling"),
        Finding(rule_id="R018", message="Server-initiated roots/list was replaced.",
                path=Path("a.py"), line=2, feature="Server-initiated roots/list"),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_same_feature_from_one_rule_alone_is_untouched():
    """R007 firing on the same feature twice with no R018 in the file is
    two real findings -- repetition of a single rule is not an overlap."""
    findings = [
        Finding(rule_id="R007", message="Roots is deprecated.",
                path=Path("a.py"), line=12, feature="Roots"),
        Finding(rule_id="R007", message="Roots is deprecated.",
                path=Path("a.py"), line=464, feature="Roots"),
    ]
    out = dedupe(findings, RULES)
    assert len(out) == 2


def test_same_feature_from_rules_not_in_a_known_pair_is_untouched():
    findings = [
        Finding(rule_id="R007", message="Roots is deprecated.",
                path=Path("a.py"), line=12, feature="Roots"),
        Finding(rule_id="R011", message="unrelated claim",
                path=Path("a.py"), line=12, feature="Roots"),
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
    """The issue's repro names `CreateMessageResultSchema` on two lines; both
    rules fire on both lines -- four findings about one fact. The feature
    key collapses all four into one."""
    (tmp_path / "server.py").write_text(
        "from mcp.types import CreateMessageResultSchema\n"
        "sampler = CreateMessageResultSchema\n"
    )
    result = run_check_detailed(tmp_path)
    assert len(result.findings) == 1, f"expected one merged finding, got {result.findings}"
    assert result.findings[0].rule_id == "R018"
    assert result.findings[0].line == 1  # the breaking rule's earliest line
    assert "Also flagged by R007" in result.findings[0].message


def test_check_merges_same_feature_across_lines_in_a_real_tree(tmp_path):
    """The mcp-server-git shape end to end: `RootsCapability` (R007-only
    signal) and `ListRootsResult` (R018-only signal) on different lines are
    one Roots fact, not four findings."""
    (tmp_path / "server.py").write_text(
        "from mcp.types import ListRootsResult, RootsCapability\n"
        "\n"
        "cap = RootsCapability()\n"
        "result: ListRootsResult = await server.request_context.session.list_roots()\n"
    )
    result = run_check_detailed(tmp_path)
    r007 = [f for f in result.findings if f.rule_id == "R007"]
    r018 = [f for f in result.findings if f.rule_id == "R018"]
    assert len(r007) == 0, f"R007 findings should have been absorbed: {r007}"
    assert len(r018) == 1, f"expected one merged R018 finding, got {r018}"
    assert "Also flagged by R007" in r018[0].message
