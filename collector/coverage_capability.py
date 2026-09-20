"""Railway-evidence coverage classes for the frozen matrix.

LIVE requires a provider that can emit explicit live event state.
RAPID_RESULT is race-card + official finish, never in-running LIVE.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

LIVE_CAPABLE_FAMILIES: Set[str] = {
    "fotmob",
    "sofascore-web",
    "pulselive",
    "mlb-statsapi",
    "nhl-web",
    "sportscore",
    "wta-json",
    "openligadb",
    "cfl-scoreboard-json",
    "lolesports-json",
    "f1-livetiming-index",
    "world-aquatics-api",
    "pga-graphql",
    "click-tt",
    "click-tt-remix",
    "altiusrt-html",
    "championdata-netball",
    "dataproject-web",
    "dataproject-wcm",
    "euroleague-live",
    "khl-mobile",
    "fifa-digital",
    "opendota",
    "espn-html",
    "bbc-sport",
}

RAPID_RESULT_FAMILIES: Set[str] = {
    "gbgb-web",
    "gbgb-meeting-json",
    "gri-web",
    "standardbred-canada-web",
    "letrot-web",
    "hrnsw-web",
    "usta-web",
    "sporting-life",
    "meadowlands-web",
    "equidia-web",
    "woodbine-mohawk-web",
    "harrington-web",
    "club-menangle-web",
}

FAMILY_EVIDENCE: Dict[str, Dict[str, Any]] = {
    "fotmob": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "www.fotmob.com/api/data/matches + match-score"},
    "sofascore-web": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "www.sofascore.com/api/v1/sport/{sport}/events/live"},
    "pulselive": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "api.wr-rims-prod.pulselive.com/rugby/v3/match date window"},
    "pga-graphql": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "POST orchestrator.pgatour.com/graphql"},
    "click-tt": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "mytischtennis.de Remix _data + /api/meeting/{id}/live"},
    "click-tt-remix": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "mytischtennis.de Remix _data + /api/meeting/{id}/live"},
    "altiusrt-html": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "fih.altiusrt.com HTML (REST 401)"},
    "championdata-netball": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "mc.championdata.com competitions + fixture"},
    "gbgb-meeting-json": {"railway_access": True, "live_schema": False, "rapid_result": True, "live_sample_observed": False, "transport": "api.gbgb.org.uk/api/results/meeting/{id}"},
    "cfl-scoreboard-json": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "CFL public scoreboard JSON"},
    "lolesports-json": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "esports-api.lolesports.com"},
    "f1-livetiming-index": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "livetiming.formula1.com/static/Index.json"},
    "world-aquatics-api": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "api.worldaquatics.com"},
    "dataproject-web": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "DataProject WCM HTML"},
    "dataproject-wcm": {"railway_access": True, "live_schema": True, "live_sample_observed": False, "transport": "DataProject WCM HTML"},
    "mlb-statsapi": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "statsapi.mlb.com"},
    "nhl-web": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "api-web.nhle.com"},
    "sportscore": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "sportscore.com widget JSON"},
    "wta-json": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "api.wtatennis.com"},
    "openligadb": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "api.openligadb.de"},
    "opendota": {"railway_access": True, "live_schema": True, "live_sample_observed": True, "transport": "api.opendota.com"},
    "europeantour-web": {"railway_access": False, "live_schema": False, "live_sample_observed": False, "transport": "europeantour.com 403"},
}

COMPETITION_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "korean-golf-tour": {
        "capability": "RESULTS_ONLY",
        "railway_access": True,
        "live_schema": False,
        "live_sample_observed": False,
        "reason": "KPGA public HTML; no proven public live transport",
    },
    "ettu-events": {
        "capability": "RESULTS_ONLY",
        "railway_access": True,
        "live_schema": False,
        "live_sample_observed": False,
        "reason": "ETTU public HTML/results; no proven live transport",
    },
    "world-lacrosse": {
        "capability": "RESULTS_ONLY",
        "railway_access": True,
        "live_schema": False,
        "live_sample_observed": False,
        "reason": "official public HTML/results; no proven live transport",
    },
    "european-challenge-tour": {
        "capability": "ACCESS_BLOCKED",
        "railway_access": False,
        "live_schema": False,
        "live_sample_observed": False,
        "reason": "europeantour.com 403 from Railway; no live coverage claimed",
    },
    "pga-tour": {
        "capability": "LIVE",
        "railway_access": True,
        "live_schema": True,
        "live_sample_observed": True,
        "reason": "PGA GraphQL POST upcomingSchedule IN_PROGRESS Biltmore R2026557",
    },
    "korn-ferry-tour": {
        "capability": "STRUCTURALLY_LIVE",
        "railway_access": True,
        "live_schema": True,
        "live_sample_observed": False,
        "reason": "same PGA GraphQL tourCode S",
    },
    "nz-national-league": {
        "capability": "STRUCTURALLY_LIVE",
        "railway_access": True,
        "live_schema": True,
        "live_sample_observed": False,
        "reason": "SofaScore uniqueTournament 594 on sport live/date boards; not FotMob 8870",
    },
    "nordic-water-polo-league": {
        "capability": "STRUCTURALLY_LIVE",
        "railway_access": True,
        "live_schema": True,
        "live_sample_observed": False,
        "reason": "SofaScore uniqueTournament 27690 on waterpolo live board",
    },
}

LIVE_SAMPLE_COMPETITIONS = {"pga-tour"}


def _family_names(families: Iterable[Dict[str, Any]]) -> Set[str]:
    return {str(row.get("family") or "") for row in families if row.get("family")}


def annotate_record(record: Dict[str, Any], families: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    cid = record.get("competition") or ""
    rows = list(families or [])
    names = _family_names(rows)
    override = COMPETITION_OVERRIDES.get(cid)
    live_fams = sorted(names & LIVE_CAPABLE_FAMILIES)
    rapid_fams = sorted(names & RAPID_RESULT_FAMILIES)
    evidence = {}
    for fam in names:
        if fam in FAMILY_EVIDENCE:
            evidence[fam] = dict(FAMILY_EVIDENCE[fam])
    if override:
        record["capability"] = override["capability"]
        record["railway_access"] = override["railway_access"]
        record["live_schema"] = override["live_schema"]
        record["live_sample_observed"] = override["live_sample_observed"]
        record["capability_reason"] = override["reason"]
    elif live_fams:
        sample = cid in LIVE_SAMPLE_COMPETITIONS or any(
            FAMILY_EVIDENCE.get(fam, {}).get("live_sample_observed") for fam in live_fams
        )
        record["capability"] = "LIVE" if sample and any(
            FAMILY_EVIDENCE.get(fam, {}).get("live_sample_observed") for fam in live_fams
        ) else "STRUCTURALLY_LIVE"
        # Existing live providers (MLB/NHL/SportScore/WTA/OpenLiga) keep LIVE if family evidence says sample observed.
        if any(FAMILY_EVIDENCE.get(fam, {}).get("live_sample_observed") for fam in live_fams):
            record["capability"] = "LIVE"
        record["railway_access"] = True
        record["live_schema"] = True
        record["live_sample_observed"] = bool(any(FAMILY_EVIDENCE.get(fam, {}).get("live_sample_observed") for fam in live_fams))
        record["capability_reason"] = "live-capable family: " + ", ".join(live_fams)
    elif rapid_fams:
        record["capability"] = "RAPID_RESULT"
        record["railway_access"] = True
        record["live_schema"] = False
        record["live_sample_observed"] = False
        record["capability_reason"] = "race card + official finish; not in-running LIVE"
    else:
        record["capability"] = "RESULTS_ONLY"
        record["railway_access"] = True
        record["live_schema"] = False
        record["live_sample_observed"] = False
        record["capability_reason"] = "no proven live-capable family"
    record["live_capable_families"] = live_fams
    record["rapid_result_families"] = rapid_fams
    record["family_evidence"] = evidence
    record["redundant_live_paths"] = len(live_fams) >= 2
    return record
