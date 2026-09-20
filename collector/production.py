"""Register verified production adapters and seed source/competition maps.

Does not invent events. Competitions are created as identity rows and only
become coverage after a collector cycle writes real events.
"""

from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.orm import Session

from collector.adapters import register_adapter
from collector.adapters_bbc import BbcSportAdapter
from collector.adapters_espn import EspnScoreboardAdapter
from collector.adapters_cricsheet import CricsheetAdapter
from collector.adapters_omega import OmegaTimingAdapter
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
from collector.adapters_mass import (
    AsoLetourAdapter,
    CetusNwplAdapter,
    ClubMenangleAdapter,
    FiaClassificationAdapter,
    DiamondLeaguePdfAdapter,
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
from collector.adapters_csv import SackmannTennisAdapter
from collector.adapters_wiki import LiquipediaAdapter
from collector.adapters_feeds import (
    EuroleagueLiveAdapter,
    FifaFootballAdapter,
    JolpicaF1Adapter,
    KhlAdapter,
    MlbAdapter,
    NhlAdapter,
    WorldRugbyAdapter,
)
from collector.adapters_generic import GenericHttpAdapter, PulseLiveFamilyAdapter
from collector.adapters_opendota import OpenDotaAdapter
from collector.adapters_openfootball import OpenFootballAdapter
from collector.adapters_sportscore import SportScoreAdapter
from collector.adapters_fotmob import FotMobAdapter
from collector.adapters_sofascore import SofaScoreWebAdapter
from collector.adapters_ro56 import (
    CflScoreboardAdapter,
    F1LiveTimingIndexAdapter,
    LolEsportsAdapter,
    WorldAquaticsApiAdapter,
)
from collector.adapters_final18 import (
    AltiusRtHtmlAdapter,
    ChampionDataNetballAdapter,
    ClickTtRemixAdapter,
    GbgbMeetingJsonAdapter,
    PgaGraphqlAdapter,
)
from collector.adapters_sporting_events import SportingEventsAdapter
from collector.adapters_worldcup26 import Worldcup26ApiAdapter
from collector.adapters_sportsrc import SportSrcAdapter
from collector.adapters_soccerway import SoccerwayAdapter
from collector.adapters_aiff import AiffWebAdapter
from collector.adapters_rte_rugby import RteRugbyAdapter
from collector.adapters_super_rugby_html import SuperRugbyHtmlAdapter
from collector.adapters_eliteprospects import EliteProspectsAdapter
from collector.adapters_volleyballworld import VolleyballWorldAdapter
from collector.adapters_cev_competition_area import CevCompetitionAreaAdapter
from collector.adapters_dataproject import DataProjectWebAdapter
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
from collector.adapters_wta import WtaJsonAdapter
from collector.adapters_openligadb import OpenLigaDbAdapter
from collector.adapters_squiggle import SquiggleAflAdapter
from collector.adapters_thesportsdb import TheSportsDbAdapter
from collector.catalog import sync_identity_catalog
from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition
from collector.registry import build_runtime_registry
from collector.util import dump_json
from sports_registry.sports import get_sport


def register_production_adapters() -> None:
    register_adapter("openfootball-json", OpenFootballAdapter)
    register_adapter("openligadb", OpenLigaDbAdapter)
    register_adapter("thesportsdb", TheSportsDbAdapter)
    register_adapter("opendota", OpenDotaAdapter)
    register_adapter("squiggle-afl", SquiggleAflAdapter)
    register_adapter("cricsheet-json", CricsheetAdapter)
    register_adapter("fifa-json", FifaFootballAdapter)
    register_adapter("nhl-web", NhlAdapter)
    register_adapter("mlb-statsapi", MlbAdapter)
    register_adapter("khl-mobile", KhlAdapter)
    register_adapter("world-rugby-rims", WorldRugbyAdapter)
    register_adapter("jolpica-f1", JolpicaF1Adapter)
    register_adapter("euroleague-live", EuroleagueLiveAdapter)
    register_adapter("generic-http", GenericHttpAdapter)
    register_adapter("bbc-sport", BbcSportAdapter)
    register_adapter("espn-scoreboard", EspnScoreboardAdapter)
    register_adapter("pulselive-family", PulseLiveFamilyAdapter)
    register_adapter("liquipedia", LiquipediaAdapter)
    register_adapter("sackmann-csv", SackmannTennisAdapter)
    register_adapter("omega-timing", OmegaTimingAdapter)
    register_adapter("sportscore", SportScoreAdapter)
    register_adapter("fotmob", FotMobAdapter)
    register_adapter("sofascore-web", SofaScoreWebAdapter)
    register_adapter("cfl-scoreboard-json", CflScoreboardAdapter)
    register_adapter("lolesports-json", LolEsportsAdapter)
    register_adapter("f1-livetiming-index", F1LiveTimingIndexAdapter)
    register_adapter("world-aquatics-api", WorldAquaticsApiAdapter)
    register_adapter("pga-graphql", PgaGraphqlAdapter)
    register_adapter("click-tt-remix", ClickTtRemixAdapter)
    register_adapter("altiusrt-html", AltiusRtHtmlAdapter)
    register_adapter("championdata-netball", ChampionDataNetballAdapter)
    register_adapter("gbgb-meeting-json", GbgbMeetingJsonAdapter)
    register_adapter("wta-json", WtaJsonAdapter)
    register_adapter("sporting-events", SportingEventsAdapter)
    register_adapter("worldcup26-api", Worldcup26ApiAdapter)
    register_adapter("sportsrc", SportSrcAdapter)
    register_adapter("soccerway-html", SoccerwayAdapter)
    register_adapter("aiff-web", AiffWebAdapter)
    register_adapter("rte-rugby", RteRugbyAdapter)
    register_adapter("super-rugby-html", SuperRugbyHtmlAdapter)
    register_adapter("eliteprospects", EliteProspectsAdapter)
    register_adapter("volleyballworld", VolleyballWorldAdapter)
    register_adapter("cev-competition-area", CevCompetitionAreaAdapter)
    register_adapter("dataproject-web", DataProjectWebAdapter)
    register_adapter("prod2-web", Prod2Adapter)
    register_adapter("acb-html", AcbHtmlAdapter)
    register_adapter("formula-e-web", FormulaEAdapter)
    register_adapter("netballpass", NetballPassAdapter)
    register_adapter("world-netball-web", WorldNetballAdapter)
    register_adapter("futsalplanet", FutsalPlanetAdapter)
    register_adapter("gbgb-web", GbgbAdapter)
    register_adapter("fis-web", FisResultsAdapter)
    register_adapter("eurohockey-web", EuroHockeyAdapter)
    register_adapter("ettu-web", EttuAdapter)
    register_adapter("nll-web", NllAdapter)
    register_adapter("eurosport-volleyball", EurosportVolleyballAdapter)
    register_adapter("pcs-web", PcsCyclingAdapter)
    register_adapter("sporting-life", SportingLifeRacingAdapter)
    register_adapter("fcpro-web", FcProAdapter)
    register_adapter("gri-web", GriAdapter)
    register_adapter("total-waterpolo", TotalWaterpoloAdapter)
    register_adapter("hbl-web", HblScheduleAdapter)
    register_adapter("ibu-web", IbuResultsAdapter)
    register_adapter("rte-cycling", RteCyclingAdapter)
    register_adapter("world-athletics-web", WorldAthleticsAdapter)
    register_adapter("nrl-draw-web", NrlDrawAdapter)
    register_adapter("standardbred-canada-web", StandardbredCanadaAdapter)
    register_adapter("hrnsw-web", HrnswMeetAdapter)
    register_adapter("letrot-web", LetrotMeetAdapter)
    register_adapter("equidia-web", EquidiaMeetAdapter)
    register_adapter("england-hockey-web", EnglandHockeyAdapter)
    register_adapter("lacrosse-canada-web", LacrosseCanadaAdapter)
    register_adapter("fiaf2-web", FormulaTwoAdapter)
    register_adapter("fiaf3-web", FormulaThreeAdapter)
    register_adapter("aso-letour", AsoLetourAdapter)
    register_adapter("fia-web", FiaClassificationAdapter)
    register_adapter("scottish-hockey-web", ScottishHockeyAdapter)
    register_adapter("gpcqm-web", GpcqmAdapter)
    register_adapter("woodbine-mohawk-web", WoodbineMohawkAdapter)
    register_adapter("uefa-futsal-web", UefaFutsalAdapter)
    register_adapter("lnf-web", LnfOficialAdapter)
    register_adapter("wikipedia-lnbp-web", WikiLnbpAdapter)
    register_adapter("diamond-league-pdf", DiamondLeaguePdfAdapter)
    register_adapter("tischtennislive", TischtennisLiveAdapter)
    register_adapter("ttbl-web", TtblAdapter)
    register_adapter("wikipedia-all-england-web", WikiAllEnglandAdapter)
    register_adapter("wikipedia-uefa-futsal-web", WikiUefaFutsalAdapter)
    register_adapter("wikipedia-lol-worlds-web", WikiLolWorldsAdapter)
    register_adapter("wikipedia-fifa-futsal-web", WikiFifaFutsalAdapter)
    register_adapter("meadowlands-web", MeadowlandsAdapter)
    register_adapter("cetus-web", CetusNwplAdapter)
    register_adapter("club-menangle-web", ClubMenangleAdapter)
    register_adapter("harrington-web", HarringtonAdapter)
    register_adapter("wikipedia-indonesia-open-web", WikiIndonesiaOpenAdapter)
    register_adapter("kompas-web", KompasIndonesiaOpenAdapter)
    register_adapter("cbf-fifa-futsal-web", CbfFifaFutsalAdapter)
    register_adapter("afa-fifa-futsal-web", AfaFifaFutsalAdapter)
    register_adapter("nordic-waterpolo-native", NordicWaterpoloNativeAdapter)
    register_adapter("ettu-news-results", EttuNewsResultsAdapter)
    register_adapter("fftt-web", FfttEttuAdapter)
    register_adapter("kpga-web", KpgaLeaderboardAdapter)
    register_adapter("rocketleague-recaps", RocketLeagueRecapsAdapter)
    register_adapter("blizzard-owcs-recaps", BlizzardOwcsRecapsAdapter)
    register_adapter("world-aquatics-web", WorldAquaticsWebAdapter)
    register_adapter("wikipedia-wa-wp-web", WikiWaWaterPoloAdapter)
    register_adapter("pgl-web", PglCsAdapter)
    register_adapter("wikipedia-rlcs-web", WikiRlcsAdapter)
    register_adapter("wikipedia-vct-web", WikiVctAdapter)
    register_adapter("wikipedia-korean-tour-web", WikiKoreanTourAdapter)
    register_adapter("wikipedia-irish-greyhound-derby-web", WikiIrishGreyhoundDerbyAdapter)
    register_adapter("wikipedia-owcs-world-finals-web", WikiOwcsWorldFinalsAdapter)
    register_adapter("ewc-owcs-web", EwcOwcsAdapter)
    register_adapter("dttb-web", DttbEttuAdapter)
    register_adapter("skidskytte-web", SkidskytteAdapter)


def _upsert_source(db: Session, payload: Dict) -> None:
    row = db.query(SportsSource).filter_by(source_id=payload["source_id"]).first()
    if row is None:
        row = SportsSource(source_id=payload["source_id"])
        db.add(row)
    for key, value in payload.items():
        setattr(row, key, value)


def _upsert_competition(db: Session, spec: Dict) -> None:
    competition_id = spec["competition_id"]
    sport = get_sport(spec.get("sport_id") or spec.get("sport")) or {}
    row = db.query(SportsCompetition).filter_by(competition_id=competition_id).first()
    payload = dict(
        sport_id=spec.get("sport_id") or spec.get("sport") or "",
        name=spec.get("name") or competition_id,
        official_name=spec.get("official_name") or spec.get("name") or competition_id,
        slug=spec.get("slug") or competition_id,
        country_id=spec.get("country_id") or None,
        region_id=spec.get("region_id") or None,
        event_model=spec.get("event_model") or sport.get("event_model") or "team_match",
        series_id=competition_id if (spec.get("event_model") or sport.get("event_model")) == "motorsport_race" else None,
        game_id=spec.get("sport") if sport.get("parent_id") == "esports" else None,
        parent_sport_id=sport.get("parent_id"),
        country_based=bool(sport.get("country_based")),
        gender=spec.get("gender"),
        active=bool(spec.get("enabled", True)),
        news_taxonomy=False,
        identity_only=False,
    )
    if row is None:
        db.add(SportsCompetition(competition_id=competition_id, **payload))
        return
    for key, value in payload.items():
        setattr(row, key, value)


def _upsert_mapping_row(db: Session, mapping: Dict) -> None:
    row = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=mapping["competition_id"], source_id=mapping["source_id"])
        .first()
    )
    if row is None:
        row = SportsSourceCompetition(
            competition_id=mapping["competition_id"],
            source_id=mapping["source_id"],
        )
        db.add(row)
    row.priority = mapping["priority"]
    row.enabled = bool(mapping.get("enabled", True))
    row.source_competition_id = mapping.get("source_competition_id") or mapping["competition_id"]
    row.coverage_scope = mapping.get("coverage") or "full"
    row.coverage_notes = mapping.get("coverage_notes")
    row.verification = mapping.get("verification")
    row.polling_class = mapping.get("polling_class") or "NORMAL"
    row.source_config_json = dump_json(mapping.get("source_config") or {})
    row.independence_status = mapping.get("independence_status")
    row.derived_from = mapping.get("derived_from") or None
    row.upstream_family = mapping.get("source_family")


def _feed_sources() -> list:
    return [
        dict(
            source_id="opendota",
            display_name="OpenDota",
            kind="dynamic",
            enabled=True,
            adapter_key="opendota",
            attribution_required=True,
            attribution_text="Professional Dota 2 matches from OpenDota.",
            attribution_url="https://www.opendota.com/",
            license_name="OpenDota API terms",
            rate_limit_per_minute=50,
            capabilities_json=dump_json({"fixtures": True, "results": True, "live_scores": True, "standings": False}),
            sports_supported_json=dump_json(["dota-2"]),
            upstream_family="opendota",
            source_type="official API",
        ),
        dict(
            source_id="fifa",
            display_name="FIFA Digital calendar/live JSON",
            kind="dynamic",
            enabled=True,
            adapter_key="fifa-json",
            attribution_required=True,
            attribution_text="Match data from FIFA public website JSON.",
            attribution_url="https://www.fifa.com/",
            license_name="reuse:restricted",
            rate_limit_per_minute=20,
            capabilities_json=dump_json({"fixtures": True, "results": True, "live_scores": True, "standings": False}),
            sports_supported_json=dump_json(["football"]),
            upstream_family="fifa-digital",
            source_type="public JSON",
        ),
        dict(
            source_id="cricsheet",
            display_name="Cricsheet",
            kind="dynamic",
            enabled=True,
            adapter_key="cricsheet-json",
            attribution_required=True,
            attribution_text="Cricket match data from Cricsheet (ODC-By 1.0).",
            attribution_url="https://cricsheet.org/",
            license_name="ODC-By 1.0",
            rate_limit_per_minute=6,
            capabilities_json=dump_json({"fixtures": True, "results": True, "live_scores": False, "standings": False}),
            sports_supported_json=dump_json(["cricket"]),
            upstream_family="cricsheet",
            source_type="other verified public source",
        ),
    ]


def bootstrap_registry(db: Session) -> Dict[str, int]:
    """Idempotent source/competition maps compiled from discovery_inventory."""
    sync_identity_catalog(db)
    runtime = build_runtime_registry()
    for payload in runtime["sources"].values():
        _upsert_source(
            db,
            dict(
                source_id=payload["source_id"],
                source_id_original=payload.get("source_id_original") or payload["source_id"],
                display_name=payload["display_name"],
                kind=payload["kind"],
                enabled=payload["enabled"],
                adapter_key=payload["adapter_key"],
                attribution_required=payload.get("attribution_required", True),
                attribution_text=payload.get("attribution_text"),
                attribution_url=payload.get("attribution_url"),
                license_name=payload.get("license_name"),
                rate_limit_per_minute=payload.get("rate_limit_per_minute") or 4,
                requires_credentials=payload.get("requires_credentials", False),
                licensed=payload.get("licensed", False),
                upstream_family=payload.get("upstream_family"),
                source_type=payload.get("source_type"),
                credential_env=payload.get("credential_env"),
                independence_status=payload.get("independence_status"),
                derived_from=payload.get("derived_from") or None,
                sports_supported_json=dump_json(payload.get("sports_supported")),
                capabilities_json=dump_json(
                    {"fixtures": True, "results": True, "live_scores": True, "standings": False}
                ),
            ),
        )
    for spec in runtime["competitions"].values():
        _upsert_competition(
            db,
            dict(
                competition_id=spec["competition_id"],
                sport_id=spec["sport"],
                name=spec["name"],
                official_name=spec.get("official_name"),
                slug=spec.get("slug"),
                country_id=spec.get("country_id"),
                region_id=spec.get("region_id"),
                event_model=spec.get("event_model"),
                gender=spec.get("gender"),
                enabled=spec.get("enabled", True),
            ),
        )
    for mapping in runtime["mappings"]:
        _upsert_mapping_row(db, mapping)
    for payload in _feed_sources():
        _upsert_source(db, payload)
    db.flush()
    return {
        "competitions": runtime["counts"]["competitions"],
        "mappings": runtime["counts"]["mappings"],
        "sources": runtime["counts"]["sources"],
        "enabled_mappings": runtime["counts"]["enabled_mappings"],
        "families": runtime["counts"]["families"],
        "adapters": runtime["counts"]["adapters"],
    }
