"""Family-grouped live verification. Writes proof_ledger.json from real events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from collector.adapters import FetchRequest
from collector.adapters_bbc import BbcSportAdapter
from collector.adapters_espn import EspnScoreboardAdapter
from collector.adapters_omega import OmegaTimingAdapter
from collector.adapters_sportscore import SportScoreAdapter
from collector.adapters_wta import WtaJsonAdapter
from collector.event_quality import INDIVIDUAL_SPORTS, MEET, MULTI_EVENT_MEET, RACE, TOURNAMENT, event_is_valid, event_type_for
from collector.provider_catalog import write_catalog
from collector.adapters_sporting_events import SportingEventsAdapter
from collector.adapters_soccerway import SoccerwayAdapter
from collector.adapters_aiff import AiffWebAdapter
from collector.adapters_generic import GenericHttpAdapter
from collector.adapters_rte_rugby import RteRugbyAdapter
from collector.adapters_super_rugby_html import SuperRugbyHtmlAdapter
from collector.adapters_eliteprospects import EliteProspectsAdapter
from collector.adapters_volleyballworld import VolleyballWorldAdapter
from collector.adapters_cev_competition_area import CevCompetitionAreaAdapter
from collector.adapters_official import (
    AcbHtmlAdapter,
    EttuAdapter,
    EuroHockeyAdapter,
    FisResultsAdapter,
    FormulaEAdapter,
    FutsalPlanetAdapter,
    GbgbAdapter,
    NetballPassAdapter,
    NllAdapter,
    Prod2Adapter,
    WorldNetballAdapter,
)
from collector.adapters_closure import (
    EurosportVolleyballAdapter,
    FcProAdapter,
    GriAdapter,
    PcsCyclingAdapter,
    SportingLifeRacingAdapter,
    TotalWaterpoloAdapter,
    HblScheduleAdapter,
)
from collector.adapters_omega import OmegaTimingAdapter
from collector.adapters_wiki import LiquipediaAdapter
from collector.adapters_feeds import FifaFootballAdapter
from collector.adapters_mass import (
    AsoLetourAdapter,
    CetusNwplAdapter,
    ClubMenangleAdapter,
    DiamondLeaguePdfAdapter,
    FiaClassificationAdapter,
    GpcqmAdapter,
    HarringtonAdapter,
    KompasIndonesiaOpenAdapter,
    LnfOficialAdapter,
    MeadowlandsAdapter,
    ScottishHockeyAdapter,
    TischtennisLiveAdapter,
    TtblAdapter,
    UefaFutsalAdapter,
    WikiAllEnglandAdapter,
    WikiFifaFutsalAdapter,
    WikiIndonesiaOpenAdapter,
    WikiLnbpAdapter,
    WikiLolWorldsAdapter,
    WikiUefaFutsalAdapter,
    WikiWaWaterPoloAdapter,
    WoodbineMohawkAdapter,
    AfaFifaFutsalAdapter,
    BlizzardOwcsRecapsAdapter,
    CbfFifaFutsalAdapter,
    EttuNewsResultsAdapter,
    FfttEttuAdapter,
    KpgaLeaderboardAdapter,
    NordicWaterpoloNativeAdapter,
    PglCsAdapter,
    RocketLeagueRecapsAdapter,
    WorldAquaticsWebAdapter,
    DttbEttuAdapter,
    EwcOwcsAdapter,
    SkidskytteAdapter,
    WikiRlcsAdapter,
    WikiVctAdapter,
    WikiKoreanTourAdapter,
    WikiIrishGreyhoundDerbyAdapter,
    WikiOwcsWorldFinalsAdapter,
)
from collector.adapters_final import (
    EnglandHockeyAdapter,
    EquidiaMeetAdapter,
    FormulaThreeAdapter,
    FormulaTwoAdapter,
    HrnswMeetAdapter,
    IbuResultsAdapter,
    LacrosseCanadaAdapter,
    LetrotMeetAdapter,
    NrlDrawAdapter,
    RteCyclingAdapter,
    StandardbredCanadaAdapter,
    WorldAthleticsAdapter,
)
from collector.adapters_thesportsdb import TheSportsDbAdapter
from collector.source_matrix import _strict_working_sample, write_matrix

ROOT = Path(__file__).resolve().parent.parent
PROOF = ROOT / "collector" / "proof_ledger.json"


def _sample(event: dict, competition_id: str = "", sport_id: str = "") -> str:
    home = ((event.get("home") or {}).get("name") or "").strip()
    away = ((event.get("away") or {}).get("name") or "").strip()
    start = (event.get("start_time") or "")[:10]
    kind = event_type_for(competition_id, sport_id)
    if kind in {RACE, MEET, TOURNAMENT, MULTI_EVENT_MEET}:
        return f"{home} vs {away} {start}".strip()
    return f"{home} vs {away} {start}".strip()


def _record(pairs: dict, competition_id: str, family: str, events: list, reason: str = "", sport_id: str = "") -> None:
    key = f"{competition_id}|{family}"
    if not events:
        pairs[key] = {
            "status": "EMPTY_ARCHIVE",
            "events": 0,
            "sample": "",
            "reason": reason or "reachable; no extractable canonical events",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        return
    sample = _sample(events[0], competition_id, sport_id)
    if not event_is_valid(events[0], sport_id=sport_id, competition_id=competition_id):
        pairs[key] = {
            "status": "EMPTY_ARCHIVE",
            "events": 0,
            "sample": sample,
            "reason": "parsed object failed event quality (sport/competition/participants)",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        return
    sample_ok = _strict_working_sample(sample, competition_id=competition_id, sport_id=sport_id)
    if not sample_ok and sport_id in INDIVIDUAL_SPORTS:
        home = (events[0].get("home") or {}).get("name") or ""
        away = (events[0].get("away") or {}).get("name") or ""
        sample_ok = bool(home and away and "full calendar" not in f"{home} {away}".lower())
    if not sample_ok:
        pairs[key] = {
            "status": "EMPTY_ARCHIVE",
            "events": 0,
            "sample": sample,
            "reason": "parsed payload but names failed canonical sample filter",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        return
    pairs[key] = {
        "status": "WORKING",
        "events": len(events),
        "sample": sample,
        "reason": reason or "canonical events produced from upstream",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def verify() -> dict:
    pairs = {}
    if PROOF.exists():
        try:
            pairs = json.loads(PROOF.read_text(encoding="utf-8")).get("pairs") or {}
        except (OSError, ValueError):
            pairs = {}

    write_catalog()
    sportscore = SportScoreAdapter()
    for competition_id in ("atp-tour", "wta-tour"):
        result = sportscore.fetch(FetchRequest(capability="snapshot", competition_id=competition_id, sport_id="tennis"))
        _record(pairs, competition_id, "sportscore", result.events or [], "SportScore tennis widget")
    football = sportscore.fetch(FetchRequest(capability="snapshot", competition_id="usa-usl-championship", sport_id="football"))
    _record(pairs, "usa-usl-championship", "sportscore", football.events or [], "SportScore football retest once after cooldown")

    events_ds = SportingEventsAdapter()
    for competition_id, sport in (("motogp", "motorsport"), ("nrl", "rugby-league"), ("korean-golf-tour", "golf")):
        result = events_ds.fetch(FetchRequest(capability="snapshot", competition_id=competition_id, sport_id=sport))
        _record(pairs, competition_id, "sporting-events", result.events or [], "sporting-events.org dataset")

    wta = WtaJsonAdapter()
    wta_result = wta.fetch(FetchRequest(capability="snapshot", competition_id="wta-tour"))
    _record(pairs, "wta-tour", "wta-json", wta_result.events or [], "api.wtatennis.com tournaments/901/2026/matches")

    espn = EspnScoreboardAdapter()
    for competition_id in (
        "usa-usl-championship",
        "usa-nwsl",
        "copa-libertadores",
        "argentina-primera",
        "atp-tour",
        "wta-tour",
        "czech-first-league",
        "denmark-superliga",
        "sweden-allsvenskan",
        "mexico-liga-mx",
        "australia-a-league",
        "france-top-14",
    ):
        result = espn.fetch(FetchRequest(capability="snapshot", competition_id=competition_id))
        _record(pairs, competition_id, "espn-html", result.events or [], "ESPN scoreboard with date discovery")

    omega = OmegaTimingAdapter()
    omega_result = omega.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="world-aquatics-meets",
            source_config={
                "url": "https://www.omegatiming.com/2025/world-aquatics-swimming-world-cup01-live-results"
            },
        )
    )
    _record(
        pairs,
        "world-aquatics-meets",
        "omega-timing",
        omega_result.events or [],
        "Omega Swimming World Cup 2025 Carmel page/XML",
    )
    _record(
        pairs,
        "world-aquatics-events",
        "omega-timing",
        omega_result.events or [],
        "same Omega family page; water polo scope may be partial",
    )
    soccerway_pass(pairs)
    rugby_volleyball_hockey_pass(pairs)
    remainder_pass(pairs)
    closure_pass(pairs)

    payload = {"pairs": pairs, "updated": datetime.now(timezone.utc).isoformat()}
    PROOF.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    matrix = write_matrix()
    return {"proof": payload, "matrix": matrix}


def soccerway_pass(pairs: dict) -> dict:
    soccerway = SoccerwayAdapter()
    for competition_id in (
        "afc-champions-league",
        "australia-a-league-women",
        "caf-champions-league",
        "copa-sudamericana",
        "serbia-superliga",
        "slovakia-super-liga",
        "thai-league-1",
        "uzbekistan-super-league",
        "malaysia-super-league",
    ):
        result = soccerway.fetch(
            FetchRequest(capability="snapshot", competition_id=competition_id, sport_id="football")
        )
        _record(pairs, competition_id, "soccerway", result.events or [], result.parse_reason or "Soccerway public HTML")
    aiff = AiffWebAdapter()
    aiff_result = aiff.fetch(
        FetchRequest(capability="snapshot", competition_id="india-super-league", sport_id="football")
    )
    _record(pairs, "india-super-league", "aiff-web", aiff_result.events or [], "the-aiff.com/competitions/isl")
    official = GenericHttpAdapter()
    serbia = official.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="serbia-superliga",
            sport_id="football",
            upstream_family="superliga-web",
            source_config={
                "url": "https://www.superliga.rs/sezona/raspored-i-rezultati/",
                "html_urls": [
                    "https://www.superliga.rs/sezona/raspored-i-rezultati/",
                    "https://fss.rs/takmicenje/mozzart-bet-super-liga-srbije-26-27/?script=lat",
                    "https://fss.rs/delegiranje/mozzart-bet-super-liga-srbije-26-27-delegiranje/?script=lat",
                ],
            },
        )
    )
    _record(pairs, "serbia-superliga", "superliga-web", serbia.events or [], "superliga.rs raspored + FSS Mozzart Bet 26/27")
    slovakia = official.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="slovakia-super-liga",
            sport_id="football",
            upstream_family="futbalnet",
            source_config={"url": "https://sportnet.sme.sk/futbalnet/z/ulk/s/nike-liga/vysledky/"},
        )
    )
    _record(pairs, "slovakia-super-liga", "futbalnet", slovakia.events or [], "sportnet.sme.sk futbalnet nike-liga vysledky")
    return pairs


def rugby_volleyball_hockey_pass(pairs: dict) -> dict:
    rte = RteRugbyAdapter()
    top14 = rte.fetch(FetchRequest(capability="snapshot", competition_id="france-top-14", sport_id="rugby"))
    _record(pairs, "france-top-14", "rte-rugby", top14.events or [], "rte.ie rugby top-14 43093 results/fixtures")
    prod2 = rte.fetch(FetchRequest(capability="snapshot", competition_id="france-pro-d2", sport_id="rugby"))
    if prod2.events:
        _record(pairs, "france-pro-d2", "rte-rugby", prod2.events, "rte rugby catalog Pro D2")
    super_rugby = SuperRugbyHtmlAdapter()
    srp = super_rugby.fetch(FetchRequest(capability="snapshot", competition_id="super-rugby", sport_id="rugby"))
    _record(pairs, "super-rugby", "super-rugby-html", srp.events or [], "super.rugby match-centre HTML match-packs")
    ep = EliteProspectsAdapter()
    liiga = ep.fetch(FetchRequest(capability="snapshot", competition_id="finland-liiga", sport_id="ice-hockey"))
    _record(pairs, "finland-liiga", "eliteprospects", liiga.events or [], "eliteprospects.com/league/liiga/scores")
    vw = VolleyballWorldAdapter()
    plusliga = vw.fetch(FetchRequest(capability="snapshot", competition_id="plusliga", sport_id="volleyball"))
    _record(pairs, "plusliga", "volleyballworld", plusliga.events or [], "en.volleyballworld.com competitions/plusliga")
    cev = CevCompetitionAreaAdapter()
    eurovolley = cev.fetch(FetchRequest(capability="snapshot", competition_id="cev-eurovolley-men", sport_id="volleyball"))
    _record(pairs, "cev-eurovolley-men", "cev-competition-area", eurovolley.events or [], "www-old.cev.eu CompetitionView ID=1572")
    return pairs


def remainder_pass(pairs: dict) -> dict:
    """Final remainder: verified official surfaces then remaining non-FULL rows."""
    prod2 = Prod2Adapter().fetch(FetchRequest(capability="snapshot", competition_id="france-pro-d2", sport_id="rugby"))
    _record(pairs, "france-pro-d2", "prod2-web", prod2.events or [], "prod2.lnr.fr calendrier-et-resultats", sport_id="rugby")
    acb = AcbHtmlAdapter().fetch(FetchRequest(capability="snapshot", competition_id="spain-acb", sport_id="basketball"))
    _record(pairs, "spain-acb", "acb-web", acb.events or [], "acb.com/es/liga/calendario Liga Endesa", sport_id="basketball")
    fe = FormulaEAdapter().fetch(FetchRequest(capability="snapshot", competition_id="formula-e", sport_id="motorsport"))
    _record(pairs, "formula-e", "formula-e-web", fe.events or [], "fiaformulae.com results-and-standings", sport_id="motorsport")
    eh = EuroHockeyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fih-eurohockey", sport_id="field-hockey"))
    _record(pairs, "fih-eurohockey", "eurohockey-web", eh.events or [], "eurohockey.org championship event pages", sport_id="field-hockey")
    wn = WorldNetballAdapter().fetch(FetchRequest(capability="snapshot", competition_id="world-netball", sport_id="netball"))
    _record(pairs, "world-netball", "world-netball-web", wn.events or [], "worldnetball.sport NWC2027 Qualifier Asia", sport_id="netball")
    np = NetballPassAdapter().fetch(FetchRequest(capability="snapshot", competition_id="ssn-australia", sport_id="netball"))
    _record(pairs, "ssn-australia", "netballpass", np.events or [], "netballpass.com Suncorp Super Netball 2026", sport_id="netball")
    fis = FisResultsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fis-disciplines", sport_id="winter-sports"))
    _record(pairs, "fis-disciplines", "fis-web", fis.events or [], "fis-ski.com DB results raceid 24016", sport_id="winter-sports")
    omega = OmegaTimingAdapter().fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="world-aquatics-meets",
            sport_id="swimming",
            source_config={"url": "https://www.omegatiming.com/Sport"},
        )
    )
    _record(pairs, "world-aquatics-meets", "omega-timing", omega.events or [], "omegatiming.com/Sport 2026 index", sport_id="swimming")
    nll = NllAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nll", sport_id="lacrosse"))
    _record(pairs, "nll", "nll-web", nll.events or [], "nll.com/schedule/scores", sport_id="lacrosse")
    ettu = EttuAdapter().fetch(FetchRequest(capability="snapshot", competition_id="ettu-events", sport_id="table-tennis"))
    _record(pairs, "ettu-events", "ettu-web", ettu.events or [], "ettu.org/past-events + results.ettu.site", sport_id="table-tennis")
    fp = FutsalPlanetAdapter().fetch(FetchRequest(capability="snapshot", competition_id="brazil-lnf", sport_id="futsal"))
    _record(pairs, "brazil-lnf", "futsalplanet", fp.events or [], "futsalplanet.com LNF com=2737", sport_id="futsal")
    gbgb = GbgbAdapter().fetch(FetchRequest(capability="snapshot", competition_id="gbgb-meetings", sport_id="greyhound-racing"))
    _record(pairs, "gbgb-meetings", "gbgb-web", gbgb.events or [], "api.gbgb.org.uk/api/results", sport_id="greyhound-racing")
    generic = GenericHttpAdapter()
    remainder_generic = [
        ("mexico-lnbp", "basketball", "lnbp-web", "https://www.lnbp.mx", "LNBP official"),
        ("germany-handball-bundesliga", "handball", "hbl-web", "https://www.liquimoly-hbl.de/de/s/spielplan/", "HBL spielplan"),
        ("uci-calendar", "cycling", "uci-web", "https://www.uci.org/calendar/all/1nhtco8YqG60QAx5aVHIzc", "UCI calendar"),
        ("world-aquatics-events", "water-polo", "omega-timing", "https://www.omegatiming.com/Sport", "Omega Sport index water polo"),
        ("bwf-and-national-events", "badminton", "bwf-web", "https://bwfbadminton.com/calendar/", "BWF calendar"),
        ("national-and-club", "table-tennis", "rankedin-web", "https://rankedin.com", "Rankedin public"),
        ("irish-greyhound-derby", "greyhound-racing", "gri-web", "https://www.grireland.ie/results/view-results/?date=27-Sep-25&track=SPK", "GRI Irish Greyhound Derby"),
        ("nsw-hrnsw-meetings", "harness-racing", "hrnsw-web", "https://www.hrnsw.com.au/racing/results", "HRNSW results"),
        ("usa-usta-meetings", "harness-racing", "usta-web", "https://racing.ustrotting.com/results", "USTA results"),
        ("france-letrot-meetings", "harness-racing", "letrot-web", "https://www.letrot.com/en/racing/results", "LeTROT"),
        ("korean-golf-tour", "golf", "kpga-web", "https://www.kpga.co.kr", "KPGA"),
        ("nordic-water-polo-league", "water-polo", "nordic-wpl-web", "https://www.nordicwaterpololeague.com/results-and-standings/", "Nordic WPL results"),
        ("world-lacrosse", "lacrosse", "inside-lacrosse-web", "https://www.insidelacrosse.com/intl", "Inside Lacrosse intl"),
        ("canada-standardbred-meetings", "harness-racing", "woodbine-mohawk-web", "https://woodbine.com/mohawk/racing/results/", "Woodbine Mohawk results"),
        ("bha-meetings", "horse-racing", "sporting-life", "https://www.sportinglife.com/racing/results", "Sporting Life racing"),
        ("vct", "esports", "vlr-web", "https://www.vlr.gg/events", "VLR events"),
        ("worlds-msi-regional", "esports", "lolesports-web", "https://lolesports.com/schedule", "LoL Esports schedule"),
        ("rlcs", "esports", "rlcs-web", "https://rocketleagueesports.com", "RLCS official"),
        ("tier1", "esports", "hltv-web", "https://www.hltv.org/results", "HLTV results"),
        ("competitive-ea-fc", "esports", "easportsfc-web", "https://www.ea.com/games/ea-sports-fc/compete", "EA FC compete"),
    ]
    for competition_id, sport, family, url, reason in remainder_generic:
        if family == "omega-timing":
            result = OmegaTimingAdapter().fetch(
                FetchRequest(capability="snapshot", competition_id=competition_id, sport_id=sport, source_config={"url": url})
            )
        else:
            result = generic.fetch(
                FetchRequest(
                    capability="snapshot",
                    competition_id=competition_id,
                    sport_id=sport,
                    upstream_family=family,
                    source_config={"url": url},
                )
            )
        _record(pairs, competition_id, family, result.events or [], reason, sport_id=sport)
    return pairs


def closure_pass(pairs: dict) -> dict:
    """Repair remaining non-FULL rows only. Never rewrite already-FULL competitions."""
    from collector.source_matrix import build_matrix

    matrix = build_matrix()
    full = {
        row["competition"]
        for row in matrix.get("competitions") or []
        if row.get("full_or_partial") == "full" or row.get("bucket") == "A+B WORKING"
    }
    jobs = [
        ("nll", "lacrosse", "nll-web", lambda: NllAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nll", sport_id="lacrosse")), "nll.com/schedule/scores"),
        ("world-netball", "netball", "world-netball-web", lambda: WorldNetballAdapter().fetch(FetchRequest(capability="snapshot", competition_id="world-netball", sport_id="netball")), "netball.sport Commonwealth Games fixtures"),
        ("fih-eurohockey", "field-hockey", "eurohockey-web", lambda: EuroHockeyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fih-eurohockey", sport_id="field-hockey")), "eurohockey.org qualifier event table"),
        ("plusliga", "volleyball", "eurosport-volleyball", lambda: EurosportVolleyballAdapter().fetch(FetchRequest(capability="snapshot", competition_id="plusliga", sport_id="volleyball")), "Eurosport PlusLiga calendar"),
        ("uci-calendar", "cycling", "pcs-web", lambda: PcsCyclingAdapter().fetch(FetchRequest(capability="snapshot", competition_id="uci-calendar", sport_id="cycling")), "procyclingstats.com GP Montreal 2026"),
        ("bha-meetings", "horse-racing", "sporting-life", lambda: SportingLifeRacingAdapter().fetch(FetchRequest(capability="snapshot", competition_id="bha-meetings", sport_id="horse-racing")), "sportinglife.com racing results"),
        ("gbgb-meetings", "greyhound-racing", "sporting-life", lambda: SportingLifeRacingAdapter().fetch(FetchRequest(capability="snapshot", competition_id="gbgb-meetings", sport_id="greyhound-racing")), "sportinglife.com greyhound results"),
        ("competitive-ea-fc", "ea-sports-fc", "fcpro-web", lambda: FcProAdapter().fetch(FetchRequest(capability="snapshot", competition_id="competitive-ea-fc", sport_id="ea-sports-fc")), "EA FC Pro official results"),
        ("irish-greyhound-derby", "greyhound-racing", "gri-web", lambda: GriAdapter().fetch(FetchRequest(capability="snapshot", competition_id="irish-greyhound-derby", sport_id="greyhound-racing")), "grireland.ie Irish Greyhound Derby"),
        ("nordic-water-polo-league", "water-polo", "total-waterpolo", lambda: TotalWaterpoloAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nordic-water-polo-league", sport_id="water-polo")), "total-waterpolo Nordic League"),
        ("germany-handball-bundesliga", "handball", "hbl-web", lambda: HblScheduleAdapter().fetch(FetchRequest(capability="snapshot", competition_id="germany-handball-bundesliga", sport_id="handball")), "official HBL 2026/27 schedule article"),
        ("biathlon", "winter-sports", "ibu-web", lambda: IbuResultsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="biathlon", sport_id="winter-sports")), "biathlonresults.com SportAPI Events"),
        ("tour-de-france", "cycling", "rte-cycling", lambda: RteCyclingAdapter().fetch(FetchRequest(capability="snapshot", competition_id="tour-de-france", sport_id="cycling")), "rte.ie cycling Tour de France"),
        ("uci-calendar", "cycling", "rte-cycling", lambda: RteCyclingAdapter().fetch(FetchRequest(capability="snapshot", competition_id="uci-calendar", sport_id="cycling")), "rte.ie cycling calendar"),
        ("wa-calendar", "athletics", "world-athletics-web", lambda: WorldAthleticsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="wa-calendar", sport_id="athletics")), "worldathletics.org calendar-results"),
        ("nrl", "rugby-league", "nrl-draw-web", lambda: NrlDrawAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nrl", sport_id="rugby-league")), "official NRL 2026 draw"),
        ("canada-standardbred-meetings", "harness-racing", "standardbred-canada-web", lambda: StandardbredCanadaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="canada-standardbred-meetings", sport_id="harness-racing")), "standardbredcanada.ca results"),
        ("nsw-hrnsw-meetings", "harness-racing", "hrnsw-web", lambda: HrnswMeetAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nsw-hrnsw-meetings", sport_id="harness-racing")), "hrnsw.com.au results"),
        ("france-letrot-meetings", "harness-racing", "letrot-web", lambda: LetrotMeetAdapter().fetch(FetchRequest(capability="snapshot", competition_id="france-letrot-meetings", sport_id="harness-racing")), "letrot.com resultats"),
        ("france-letrot-meetings", "harness-racing", "equidia-web", lambda: EquidiaMeetAdapter().fetch(FetchRequest(capability="snapshot", competition_id="france-letrot-meetings", sport_id="harness-racing")), "equidia.fr arrivees"),
        ("fih-eurohockey", "field-hockey", "england-hockey-web", lambda: EnglandHockeyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fih-eurohockey", sport_id="field-hockey")), "englandhockey.co.uk international"),
        ("world-lacrosse", "lacrosse", "lacrosse-canada-web", lambda: LacrosseCanadaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="world-lacrosse", sport_id="lacrosse")), "lacrosse.ca CAN 5 JPN 4 OT"),
        ("uci-calendar", "cycling", "gpcqm-web", lambda: GpcqmAdapter().fetch(FetchRequest(capability="snapshot", competition_id="uci-calendar", sport_id="cycling")), "gpcqm.ca Montreal 2026 classement"),
        ("canada-standardbred-meetings", "harness-racing", "woodbine-mohawk-web", lambda: WoodbineMohawkAdapter().fetch(FetchRequest(capability="snapshot", competition_id="canada-standardbred-meetings", sport_id="harness-racing")), "woodbine.com Mohawk Simcoe recap"),
        ("brazil-lnf", "futsal", "lnf-web", lambda: LnfOficialAdapter().fetch(FetchRequest(capability="snapshot", competition_id="brazil-lnf", sport_id="futsal")), "lnfoficial.com.br tabela de jogos"),
        ("mexico-lnbp", "basketball", "wikipedia-lnbp-web", lambda: WikiLnbpAdapter().fetch(FetchRequest(capability="snapshot", competition_id="mexico-lnbp", sport_id="basketball")), "es.wikipedia.org LNBP 2026 scores"),
        ("wa-calendar", "athletics", "diamond-league-pdf", lambda: DiamondLeaguePdfAdapter().fetch(FetchRequest(capability="snapshot", competition_id="wa-calendar", sport_id="athletics")), "Diamond League Paris 2026 official PDF"),
        ("wa-calendar", "athletics", "bbc-sport", lambda: BbcSportAdapter().fetch(FetchRequest(capability="snapshot", competition_id="wa-calendar", sport_id="athletics")), "bbc.co.uk Diamond League Paris results"),
        ("formula-2", "motorsport", "fiaf2-web", lambda: FormulaTwoAdapter().fetch(FetchRequest(capability="snapshot", competition_id="formula-2", sport_id="motorsport")), "fiaformula2.com/Standings/Driver"),
        ("formula-2", "motorsport", "fia-web", lambda: FiaClassificationAdapter().fetch(FetchRequest(capability="snapshot", competition_id="formula-2", sport_id="motorsport")), "fia.com F2 Melbourne sprint classification"),
        ("formula-3", "motorsport", "fiaf3-web", lambda: FormulaThreeAdapter().fetch(FetchRequest(capability="snapshot", competition_id="formula-3", sport_id="motorsport")), "fiaformula3.com/Standings/Driver"),
        ("formula-3", "motorsport", "fia-web", lambda: FiaClassificationAdapter().fetch(FetchRequest(capability="snapshot", competition_id="formula-3", sport_id="motorsport")), "fia.com F3 Melbourne sprint classification"),
        ("tour-de-france", "cycling", "aso-letour", lambda: AsoLetourAdapter().fetch(FetchRequest(capability="snapshot", competition_id="tour-de-france", sport_id="cycling")), "letour.fr/en/rankings"),
        ("fih-eurohockey", "field-hockey", "scottish-hockey-web", lambda: ScottishHockeyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fih-eurohockey", sport_id="field-hockey")), "scottish-hockey.org.uk Rome 6-1"),
        ("italy-superlega", "volleyball", "volleyballworld", lambda: VolleyballWorldAdapter().fetch(FetchRequest(capability="snapshot", competition_id="italy-superlega", sport_id="volleyball")), "en.volleyballworld.com superlega 27232"),
        ("nrl", "rugby-league", "nrl-draw-web", lambda: NrlDrawAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nrl", sport_id="rugby-league")), "official NRL 2026 draw"),
        ("nordic-water-polo-league", "water-polo", "total-waterpolo", lambda: TotalWaterpoloAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nordic-water-polo-league", sport_id="water-polo")), "total-waterpolo Nordic League 2024-25 iframe"),
        ("irish-greyhound-derby", "greyhound-racing", "gri-web", lambda: GriAdapter().fetch(FetchRequest(capability="snapshot", competition_id="irish-greyhound-derby", sport_id="greyhound-racing")), "grireland.ie Irish Greyhound Derby"),
        ("germany-click-tt", "table-tennis", "ttbl-web", lambda: TtblAdapter().fetch(FetchRequest(capability="snapshot", competition_id="germany-click-tt", sport_id="table-tennis")), "ttbl.de Spielplan 2026/27"),
        ("germany-click-tt", "table-tennis", "tischtennislive", lambda: TischtennisLiveAdapter().fetch(FetchRequest(capability="snapshot", competition_id="germany-click-tt", sport_id="table-tennis")), "bettv.tischtennislive.de Spielbericht"),
        ("all-england-open", "badminton", "wikipedia-all-england-web", lambda: WikiAllEnglandAdapter().fetch(FetchRequest(capability="snapshot", competition_id="all-england-open", sport_id="badminton")), "en.wikipedia.org 2026 All England Open"),
        ("all-england-open", "badminton", "bbc-sport", lambda: BbcSportAdapter().fetch(FetchRequest(capability="snapshot", competition_id="all-england-open", sport_id="badminton")), "bbc.co.uk All England live blog"),
        ("indonesia-open", "badminton", "wikipedia-indonesia-open-web", lambda: WikiIndonesiaOpenAdapter().fetch(FetchRequest(capability="snapshot", competition_id="indonesia-open", sport_id="badminton")), "en.wikipedia.org 2026 Indonesia Open"),
        ("indonesia-open", "badminton", "kompas-web", lambda: KompasIndonesiaOpenAdapter().fetch(FetchRequest(capability="snapshot", competition_id="indonesia-open", sport_id="badminton")), "kompas.com Indonesia Open final"),
        ("uefa-futsal-champions-league", "futsal", "uefa-futsal-web", lambda: UefaFutsalAdapter().fetch(FetchRequest(capability="snapshot", competition_id="uefa-futsal-champions-league", sport_id="futsal")), "uefa.com Futsal CL recap"),
        ("uefa-futsal-champions-league", "futsal", "wikipedia-uefa-futsal-web", lambda: WikiUefaFutsalAdapter().fetch(FetchRequest(capability="snapshot", competition_id="uefa-futsal-champions-league", sport_id="futsal")), "en.wikipedia.org 2025-26 UEFA Futsal CL"),
        ("fifa-futsal-when-listed", "futsal", "wikipedia-fifa-futsal-web", lambda: WikiFifaFutsalAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fifa-futsal-when-listed", sport_id="futsal")), "en.wikipedia.org 2024 FIFA Futsal World Cup"),
        ("fifa-futsal-when-listed", "futsal", "fifa-digital", lambda: FifaFootballAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fifa-futsal-when-listed", sport_id="futsal")), "FIFA Digital calendar futsal filter"),
        ("lol-world-championship", "league-of-legends", "wikipedia-lol-worlds-web", lambda: WikiLolWorldsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="lol-world-championship", sport_id="league-of-legends")), "en.wikipedia.org 2025 LoL Worlds"),
        ("lol-world-championship", "league-of-legends", "liquipedia", lambda: LiquipediaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="lol-world-championship", sport_id="league-of-legends", source_config={"wiki": "leagueoflegends", "page": "World_Championship/2025"})), "liquipedia.net World Championship/2025"),
        ("nordic-water-polo-league", "water-polo", "cetus-web", lambda: CetusNwplAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nordic-water-polo-league", sport_id="water-polo")), "cetus.fi NWPL ottelut"),
        ("nsw-hrnsw-meetings", "harness-racing", "club-menangle-web", lambda: ClubMenangleAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nsw-hrnsw-meetings", sport_id="harness-racing")), "clubmenangle.com.au Verbici recap"),
        ("usa-usta-meetings", "harness-racing", "meadowlands-web", lambda: MeadowlandsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="usa-usta-meetings", sport_id="harness-racing")), "playmeadowlands.com race-day results"),
        ("usa-usta-meetings", "harness-racing", "harrington-web", lambda: HarringtonAdapter().fetch(FetchRequest(capability="snapshot", competition_id="usa-usta-meetings", sport_id="harness-racing")), "harringtonraceway.com feature recap"),
        ("fifa-futsal-when-listed", "futsal", "cbf-fifa-futsal-web", lambda: CbfFifaFutsalAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fifa-futsal-when-listed", sport_id="futsal")), "cbf.com.br FIFA Futsal World Cup recap"),
        ("fifa-futsal-when-listed", "futsal", "afa-fifa-futsal-web", lambda: AfaFifaFutsalAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fifa-futsal-when-listed", sport_id="futsal")), "afa.com.ar FIFA Futsal World Cup recap"),
        ("nordic-water-polo-league", "water-polo", "nordic-waterpolo-native", lambda: NordicWaterpoloNativeAdapter().fetch(FetchRequest(capability="snapshot", competition_id="nordic-water-polo-league", sport_id="water-polo")), "nordicwaterpololeague.com Final Eight native results"),
        ("ettu-events", "table-tennis", "ettu-news-results", lambda: EttuNewsResultsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="ettu-events", sport_id="table-tennis")), "ettu.org 2026 youth result articles"),
        ("ettu-events", "table-tennis", "fftt-web", lambda: FfttEttuAdapter().fetch(FetchRequest(capability="snapshot", competition_id="ettu-events", sport_id="table-tennis")), "fftt.com CEJ 2026 U15 recap"),
        ("korean-golf-tour", "golf", "kpga-web", lambda: KpgaLeaderboardAdapter().fetch(FetchRequest(capability="snapshot", competition_id="korean-golf-tour", sport_id="golf")), "kpga.co.kr tours/leaderboard"),
        ("rlcs", "rocket-league", "rocketleague-recaps", lambda: RocketLeagueRecapsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="rlcs", sport_id="rocket-league")), "rocketleague.com Paris Major recap"),
        ("rlcs", "rocket-league", "liquipedia", lambda: LiquipediaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="rlcs", sport_id="rocket-league", source_config={"wiki": "rocketleague", "page": "Rocket_League_Championship_Series/2026/Paris_Major"})), "liquipedia.net RLCS 2026 Paris Major"),
        ("owcs-world-finals", "overwatch", "liquipedia", lambda: LiquipediaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="owcs-world-finals", sport_id="overwatch", source_config={"wiki": "overwatch", "page": "Overwatch_Champions_Series/2025/World_Finals"})), "liquipedia.net OWCS 2025 World Finals"),
        ("world-aquatics-events", "water-polo", "world-aquatics-web", lambda: WorldAquaticsWebAdapter().fetch(FetchRequest(capability="snapshot", competition_id="world-aquatics-events", sport_id="water-polo")), "worldaquatics.com WP World Cup unit results"),
        ("world-aquatics-events", "water-polo", "wikipedia-wa-wp-web", lambda: WikiWaWaterPoloAdapter().fetch(FetchRequest(capability="snapshot", competition_id="world-aquatics-events", sport_id="water-polo")), "en.wikipedia.org 2026 Men's Water Polo World Cup"),
        ("tier1", "counter-strike", "pgl-web", lambda: PglCsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="tier1", sport_id="counter-strike")), "pglesports.com PGL Bucharest 2026"),
        ("tier1", "counter-strike", "liquipedia", lambda: LiquipediaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="tier1", sport_id="counter-strike", source_config={"wiki": "counterstrike", "page": "PGL/2026/Bucharest"})), "liquipedia.net PGL Bucharest 2026"),
        ("vct", "valorant", "liquipedia", lambda: LiquipediaAdapter().fetch(FetchRequest(capability="snapshot", competition_id="vct", sport_id="valorant", source_config={"wiki": "valorant", "page": "Masters_Santiago_2026"})), "liquipedia.net Masters Santiago 2026"),
        ("rlcs", "rocket-league", "wikipedia-rlcs-web", lambda: WikiRlcsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="rlcs", sport_id="rocket-league")), "en.wikipedia.org RLCS Paris Major"),
        ("vct", "valorant", "wikipedia-vct-web", lambda: WikiVctAdapter().fetch(FetchRequest(capability="snapshot", competition_id="vct", sport_id="valorant")), "en.wikipedia.org Valorant Champions Tour Masters Santiago"),
        ("owcs-world-finals", "overwatch", "wikipedia-owcs-world-finals-web", lambda: WikiOwcsWorldFinalsAdapter().fetch(FetchRequest(capability="snapshot", competition_id="owcs-world-finals", sport_id="overwatch")), "en.wikipedia.org OWCS World Finals results"),
        ("ettu-events", "table-tennis", "dttb-web", lambda: DttbEttuAdapter().fetch(FetchRequest(capability="snapshot", competition_id="ettu-events", sport_id="table-tennis")), "tischtennis.de Jugend-EM U15 2:3"),
        ("biathlon", "winter-sports", "skidskytte-web", lambda: SkidskytteAdapter().fetch(FetchRequest(capability="snapshot", competition_id="biathlon", sport_id="winter-sports")), "skidskytte.se Ruhpolding jaktstart"),
        ("korean-golf-tour", "golf", "wikipedia-korean-tour-web", lambda: WikiKoreanTourAdapter().fetch(FetchRequest(capability="snapshot", competition_id="korean-golf-tour", sport_id="golf")), "en.wikipedia.org 2026 Korean Tour"),
        ("korean-golf-tour", "golf", "thesportsdb", lambda: TheSportsDbAdapter().fetch(FetchRequest(capability="snapshot", competition_id="korean-golf-tour", sport_id="golf", source_competition_id="4766")), "TheSportsDB Korean Tour 4766 eventsseason"),
        ("irish-greyhound-derby", "greyhound-racing", "wikipedia-irish-greyhound-derby-web", lambda: WikiIrishGreyhoundDerbyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="irish-greyhound-derby", sport_id="greyhound-racing")), "en.wikipedia.org {year}_Irish_Greyhound_Derby"),
    ]
    remaining = {
        "irish-greyhound-derby",
        "owcs-world-finals",
    }
    rerecord = remaining
    for competition_id, sport, family, fetcher, reason in jobs:
        if competition_id in full and competition_id not in rerecord:
            continue
        result = fetcher()
        _record(pairs, competition_id, family, result.events or [], reason, sport_id=sport)
    for competition_id, family, reason in (
        ("uci-calendar", "pcs-web", "LICENSING_BLOCKER: PCS free embed permits website iframe top-10 widgets only; backend ingestion of race pages is outside that grant"),
        ("worlds-msi-regional", "lolesports-web", "LICENSING_BLOCKER: Riot ToS forbid scrape/expropriate and unauthorized bots/scripts on Riot Services; terms https://www.riotgames.com/en/terms-of-service"),
        ("lol-world-championship", "lolesports-web", "LICENSING_BLOCKER: Riot ToS forbid scrape/expropriate and unauthorized bots/scripts on Riot Services; terms https://www.riotgames.com/en/terms-of-service"),
        ("mexico-lnbp", "flashscore", "LICENSING_BLOCKER: Flashscore ToU forbids copy/download without written authorization"),
        ("vct", "vlr-web", "LICENSING_BLOCKER: VLR terms forbid automated access and commercial reuse"),
        ("vct", "valorantesports-web", "TECHNICALLY_WORKING public schedule HTML (e.g. Paper Rex 3-1 NRG 2026-03-14); TERMS_RESTRICTED Riot ToS https://www.riotgames.com/en/terms-of-service; ingestion not enabled"),
        ("korean-golf-tour", "owgr-web", "LICENSING_BLOCKER: OWGR terms forbid reproduction/adaptation/transmission of website material without prior written permission"),
        ("tier1", "hltv-web", "LICENSING_BLOCKER: HLTV terms forbid scraping and commercial use"),
        ("usa-usta-meetings", "usta-web", "LICENSING_BLOCKER: racing.ustrotting.com personal non-commercial use only; not expanded"),
        ("germany-click-tt", "click-tt", "LICENSING_BLOCKER: click-TT terms restrict automated parsing/reuse"),
    ):
        if competition_id in full:
            continue
        pairs[f"{competition_id}|{family}"] = {
            "status": "RESTRICTED",
            "events": 0,
            "sample": "",
            "reason": reason,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    return pairs


if __name__ == "__main__":
    out = verify()
    buckets = out["matrix"].get("buckets") or {}
    print(json.dumps({"buckets": buckets, "exceptions": len(out["matrix"].get("exceptions") or [])}, indent=2))
