from collector.competition_identity import source_native_public_competition_id
from collector.ehf_breadth import competition_meta, discover_round_urls, parse_round_page


def test_ehf_index_discovers_current_round_links_and_keeps_fallbacks():
    html = """
    <a href="/ec/cl/men/2026-27/round/1/Group+Phase">open</a>
    <a href="/ec/00-04/ct/women/2026-27/round/2/Round+2">open</a>
    <a href="/ec/cl/men/2025-26/round/1/Group+Phase">old</a>
    """
    urls = discover_round_urls(html)
    assert "https://old.eurohandball.com/ec/cl/men/2026-27/round/1/Group+Phase" in urls
    assert "https://old.eurohandball.com/ec/00-04/ct/women/2026-27/round/2/Round+2" in urls
    assert all("2025-26" not in url for url in urls)


def test_ehf_competition_identity_is_gender_and_family_specific():
    men = competition_meta(
        "https://old.eurohandball.com/ec/cl/men/2026-27/round/1/Group+Phase"
    )
    women = competition_meta(
        "https://old.eurohandball.com/ec/00-04/ct/women/2026-27/round/2/Round+2"
    )
    assert men[:3] == (
        "handball-ehf-champions-league-men",
        "EHF Champions League Men",
        "men",
    )
    assert women[:3] == (
        "handball-ehf-european-cup-women",
        "EHF European Cup Women",
        "women",
    )


def test_ehf_round_page_builds_stable_source_native_event():
    html = """
    <div class="matches">
      <span>16.09.2026</span> <span>20:45</span>
      <span>Füchse Berlin</span> VS <span>One Veszprém HC</span>
      <strong>:</strong>
      <span>10.09.2026</span> <span>18:45</span>
      <span>RK Partizan AdmiralBet</span> VS <span>Füchse Berlin</span>
      <strong>44 : 33</strong>
    </div>
    """
    url = "https://old.eurohandball.com/ec/cl/men/2026-27/round/1/Group+Phase"
    rows = parse_round_page(html, url)
    assert len(rows) == 2
    assert rows[0]["sport"] == "handball"
    assert rows[0]["event_family"] == "team_match"
    assert rows[0]["competition_key"] == "handball-ehf-champions-league-men"
    assert rows[0]["source_family"] == "ehf-web"
    assert rows[0]["source_event_ids"]["ehf-web"] == rows[0]["source_event_id"]
    assert rows[1]["status"] == "finished"
    assert rows[1]["score"] == {"home": 44, "away": 33}


def test_ehf_source_native_id_requires_validated_prefix():
    accepted = source_native_public_competition_id(
        stored_competition_id="handball-ehf-champions-league-men",
        source_competition_name="EHF Champions League Men",
        sport_id="handball",
        source_family="ehf-web",
    )
    rejected = source_native_public_competition_id(
        stored_competition_id="handball-random-league",
        source_competition_name="Random League",
        sport_id="handball",
        source_family="ehf-web",
    )
    assert accepted == "handball-ehf-champions-league-men"
    assert rejected is None
