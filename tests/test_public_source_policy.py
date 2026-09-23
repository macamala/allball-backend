from types import SimpleNamespace

from collector.provider import _row_public_source_allowed
from collector.util import dump_json


def row(primary=None, contributors=None, family=None):
    return SimpleNamespace(
        primary_source_id=primary,
        contributing_sources_json=dump_json(contributors or []),
        extra_json=dump_json({"source_family": family} if family else {}),
    )


def test_branding_required_only_source_is_not_public():
    assert not _row_public_source_allowed(
        row(primary="sportscore-global", contributors=["sportscore-global"], family="sportscore"),
        {"sportscore-global"},
        {"sportscore"},
    )


def test_allowed_contributor_keeps_merged_event_public():
    assert _row_public_source_allowed(
        row(primary="sportscore-global", contributors=["sportscore-global", "wta-json"], family="sportscore"),
        {"sportscore-global"},
        {"sportscore"},
    )


def test_family_fallback_blocks_legacy_branding_source_ids():
    assert not _row_public_source_allowed(
        row(primary="sportscore:sportscore-widget-json:legacy", family="sportscore"),
        {"sportscore-global"},
        {"sportscore"},
    )
