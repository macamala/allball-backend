from collector.attribution import attribution_payload, public_provider_items
from tests.test_collector_architecture import _session, _source


def test_public_attribution_dedupes_and_hides_espn():
    db = _session()
    try:
        a = _source(
            db,
            "sportscore:widget:usl",
            "sportscore",
            display_name="Sports data from SportScore widget JSON.",
            attribution_required=True,
            attribution_text="Sports data from SportScore widget JSON.",
            license_name="reuse:permitted",
        )
        a.upstream_family = "sportscore"
        b = _source(
            db,
            "sportscore:standings:la-liga",
            "sportscore",
            display_name="Sports data from SportScore standings+team JSON.",
            attribution_required=True,
            license_name="reuse:permitted",
        )
        b.upstream_family = "sportscore"
        espn = _source(
            db,
            "espn-html:nba",
            "espn-html",
            display_name="Sports data from ESPN NBA scoreboard HTML.",
            attribution_required=True,
            license_name="reuse:unclear",
        )
        espn.upstream_family = "espn-html"
        tsdb = _source(
            db,
            "thesportsdb:1",
            "thesportsdb",
            display_name="Sports data from TheSportsDB.",
            attribution_required=True,
            license_name="reuse:permitted",
        )
        tsdb.upstream_family = "thesportsdb"
        db.commit()
        items = public_provider_items(db)
        names = [row["name"] for row in items]
        assert names.count("SportScore") == 1
        assert "TheSportsDB" in names
        assert not any("ESPN" in name for name in names)
        assert not any("reuse:" in (row.get("description") or "") for row in items)
        assert not any(str(row.get("name") or "").startswith("Sports data from") for row in items)
        payload = attribution_payload(db)
        assert payload["count"] == len(items)
        assert "official public sources" in payload["message"]
        sportscore = next(row for row in items if row["name"] == "SportScore")
        assert sportscore["required"] is False
        assert sportscore["attribution_kind"] == "transparency"
        ts = next(row for row in items if row["name"] == "TheSportsDB")
        assert ts["required"] is True
    finally:
        db.close()
