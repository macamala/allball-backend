"""Build the 180-competition rich-data capability artifact from the frozen matrix."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "source_matrix_final.json"
OVERLAY = ROOT / "audit" / "rich_production_overlay.json"

# Adapter/canonical/API/Match Centre path exists for these families.
_IMPLEMENTED = {
    "openligadb": {
        "timeline": "PARTIAL",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "PARTIAL",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "openligadb",
        "transport": "api.openligadb.de/getmatchdata",
        "limitation": "Goals timeline only; no cards/lineups on OpenLigaDB",
    },
    "fotmob": {
        "timeline": "PARTIAL",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "PARTIAL",
        "standings": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "player_stats": "PARTIAL",
        "venue": "PROVEN",
        "officials": "PARTIAL",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "fotmob",
        "transport": "www.fotmob.com/api/data/matches + matchDetails on-demand",
        "limitation": "Player rating/goals/assists/xG when matchDetails.playerStats present; referee/stadium from infoBox; table not mapped from match payload",
    },
    "sofascore-web": {
        "timeline": "PARTIAL",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "PARTIAL",
        "standings": "ACCESS_BLOCKED",
        "player_stats": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "venue": "PARTIAL",
        "officials": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "sofascore-web",
        "transport": "www.sofascore.com/api/v1/sport/*/events + event/{id} detail",
        "limitation": "unique-tournament routes 403 from Railway; sport boards + event detail only",
    },
    "wta-json": {
        "timeline": "NOT_APPLICABLE",
        "stats": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "lineups": "NOT_APPLICABLE",
        "periods": "PROVEN",
        "standings": "NOT_APPLICABLE",
        "player_stats": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "wta-json",
        "transport": "api.wtatennis.com/tennis/tournaments/{id}/{year}/matches",
        "limitation": "Match score from completed sets; official W/O has no sets so score stays blank with walkover; serve stats only when present on the match JSON",
    },
    "mlb-statsapi": {
        "timeline": "PROVEN",
        "stats": "PROVEN",
        "lineups": "PROVEN",
        "periods": "PROVEN",
        "standings": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "player_stats": "PROVEN",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PROVEN",
        "implemented": True,
        "adapter": "mlb-statsapi",
        "transport": "statsapi.mlb.com schedule + feed/live on-demand",
        "limitation": "Play-by-play truncated to recent plays; standings not mapped",
    },
    "nhl-web": {
        "timeline": "PROVEN",
        "stats": "PROVEN",
        "lineups": "PROVEN",
        "periods": "PARTIAL",
        "standings": "SOURCE_AVAILABLE_NOT_IMPLEMENTED",
        "player_stats": "PROVEN",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PROVEN",
        "implemented": True,
        "adapter": "nhl-web",
        "transport": "api-web.nhle.com gamecenter landing + boxscore on-demand",
        "limitation": "Period scores from scoreByPeriod when present; goals/penalties/rosters/player stats proven",
    },
    "pulselive": {
        "timeline": "PARTIAL",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "PARTIAL",
        "officials": "PARTIAL",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "world-rugby-rims",
        "transport": "api.wr-rims-prod.pulselive.com/rugby/v3/match/{id}/stats",
        "limitation": "Tries/conversions/rosters when teamStats present; scoring timeline when summary.teams.scoring present",
    },
    "pulselive-family": {
        "timeline": "PARTIAL",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "PARTIAL",
        "officials": "PARTIAL",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "pulselive-family",
        "transport": "api.wr-rims-prod.pulselive.com/rugby/v3/match",
        "limitation": "Same PulseLive rugby match stats family",
    },
    "squiggle": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "PARTIAL",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "squiggle-afl",
        "transport": "api.squiggle.com.au games",
        "limitation": "Goals/behinds/score; no player box on Squiggle games feed",
    },
    "jolpica-f1": {
        "timeline": "NOT_APPLICABLE",
        "stats": "PARTIAL",
        "lineups": "NOT_APPLICABLE",
        "periods": "NOT_APPLICABLE",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "PARTIAL",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "jolpica-f1",
        "transport": "api.jolpi.ca/ergast/f1 results",
        "limitation": "Race classification/grid/status; live timing not used",
    },
    "opendota": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "NOT_APPLICABLE",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "NOT_APPLICABLE",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "opendota",
        "transport": "api.opendota.com/api/matches/{id}",
        "limitation": "KDA/hero on-demand; no full PBP mapped",
    },
    "lolesports-json": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "NOT_APPLICABLE",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "NOT_APPLICABLE",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "lolesports-json",
        "transport": "esports-api.lolesports.com getEventDetails",
        "limitation": "Series maps/game wins when event details return games",
    },
    "cfl-scoreboard-json": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "PARTIAL",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "NO_ACCESSIBLE_DATA_FOUND",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "cfl-scoreboard-json",
        "transport": "cflscoreboard.cfl.ca rounds.json",
        "limitation": "Quarter scores when present on scoreboard payload",
    },
    "euroleague-live": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "PARTIAL",
        "lineups": "PARTIAL",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "euroleague-live",
        "transport": "live.euroleague.net/api/Boxscore",
        "limitation": "Boxscore when Header/Boxscore routes respond; catalog v1 games often 404",
    },
    "pga-graphql": {
        "timeline": "NOT_APPLICABLE",
        "stats": "PARTIAL",
        "lineups": "NOT_APPLICABLE",
        "periods": "NOT_APPLICABLE",
        "standings": "NOT_APPLICABLE",
        "player_stats": "PARTIAL",
        "venue": "PARTIAL",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "pga-graphql",
        "transport": "orchestrator.pgatour.com/graphql leaderboardV3",
        "limitation": "Leaderboard position/thru/total; hole-by-hole not mapped",
    },
    "gbgb-meeting-json": {
        "timeline": "NOT_APPLICABLE",
        "stats": "NOT_APPLICABLE",
        "lineups": "NOT_APPLICABLE",
        "periods": "NOT_APPLICABLE",
        "standings": "NOT_APPLICABLE",
        "player_stats": "NOT_APPLICABLE",
        "venue": "PROVEN",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "gbgb-meeting-json",
        "transport": "api.gbgb.org.uk/api/results and /api/results/meeting/{id}",
        "limitation": "Rapid official finish; never LIVE; placing from resultPosition",
    },
    "gbgb-web": {
        "timeline": "NOT_APPLICABLE",
        "stats": "NOT_APPLICABLE",
        "lineups": "NOT_APPLICABLE",
        "periods": "NOT_APPLICABLE",
        "standings": "NOT_APPLICABLE",
        "player_stats": "NOT_APPLICABLE",
        "venue": "PROVEN",
        "officials": "NOT_APPLICABLE",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "gbgb-web",
        "transport": "api.gbgb.org.uk/api/results",
        "limitation": "Winner/placing when greyhound name present",
    },
    "sportscore": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "sportscore",
        "transport": "sportscore.com widget JSON",
        "limitation": "Score/status/periods when present; no match-centre stats in widget",
    },
    "thesportsdb": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "NO_ACCESSIBLE_DATA_FOUND",
        "standings": "PARTIAL",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "PARTIAL",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "NO_ACCESSIBLE_DATA_FOUND",
        "implemented": True,
        "adapter": "thesportsdb",
        "transport": "www.thesportsdb.com/api/v1/json public events",
        "limitation": "Fixture/score/venue; events table has no incidents",
    },
    "championdata-netball": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "PARTIAL",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "PARTIAL",
        "venue": "NO_ACCESSIBLE_DATA_FOUND",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "championdata-netball",
        "transport": "mc.championdata.com fixture + match JSON on-demand",
        "limitation": "Quarter scores/player box when present on Champion Data match JSON; no invented periods",
    },
    "click-tt-remix": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "NO_ACCESSIBLE_DATA_FOUND",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "click-tt-remix",
        "transport": "mytischtennis.de click-TT remix table + /api/meeting/{id}/live",
        "limitation": "Individual rubber set scores when live JSON returns matches",
    },
    "dataproject-web": {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "PARTIAL",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "NO_ACCESSIBLE_DATA_FOUND",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "PARTIAL",
        "implemented": True,
        "adapter": "dataproject-web",
        "transport": "DataProject WCM HTML/JSON family",
        "limitation": "Set score on list; match-centre stats only when source_event_id is numeric mID",
    },
}

_SPORT_NA = {
    "golf": {"timeline": "NOT_APPLICABLE", "lineups": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
    "greyhound-racing": {"timeline": "NOT_APPLICABLE", "stats": "NOT_APPLICABLE", "lineups": "NOT_APPLICABLE", "periods": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
    "horse-racing": {"timeline": "NOT_APPLICABLE", "stats": "NOT_APPLICABLE", "lineups": "NOT_APPLICABLE", "periods": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
    "harness-racing": {"timeline": "NOT_APPLICABLE", "stats": "NOT_APPLICABLE", "lineups": "NOT_APPLICABLE", "periods": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
    "motorsport": {"lineups": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
    "tennis": {"lineups": "NOT_APPLICABLE", "standings": "NOT_APPLICABLE"},
}


def _blank(sport: str) -> Dict[str, str]:
    base = {
        "timeline": "NO_ACCESSIBLE_DATA_FOUND",
        "stats": "NO_ACCESSIBLE_DATA_FOUND",
        "lineups": "NO_ACCESSIBLE_DATA_FOUND",
        "periods": "NO_ACCESSIBLE_DATA_FOUND",
        "standings": "NO_ACCESSIBLE_DATA_FOUND",
        "player_stats": "NO_ACCESSIBLE_DATA_FOUND",
        "venue": "NO_ACCESSIBLE_DATA_FOUND",
        "officials": "NO_ACCESSIBLE_DATA_FOUND",
        "sport_detail": "NO_ACCESSIBLE_DATA_FOUND",
    }
    base.update(_SPORT_NA.get(sport) or {})
    return base


def _families(comp: Dict[str, Any]) -> List[str]:
    names = []
    for key in ("primary", "fallback", "provider_a", "provider_b", "provider_c"):
        block = comp.get(key) or {}
        fam = block.get("family")
        if fam and fam not in names:
            names.append(fam)
    for extra in comp.get("optional_additional") or []:
        fam = extra.get("family")
        if fam and fam not in names:
            names.append(fam)
    return names


def build_rows() -> List[Dict[str, Any]]:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = []
    for comp in matrix.get("competitions") or []:
        sport = comp.get("sport") or ""
        families = _families(comp)
        score = families[0] if families else ""
        caps = _blank(sport)
        detail_provider = ""
        adapter = (comp.get("primary") or {}).get("adapter") or score
        transport = (comp.get("primary") or {}).get("url") or (comp.get("primary") or {}).get("access") or ""
        railway = bool(comp.get("railway_access"))
        implemented = False
        limitation = "Scoreboard path only; no rich match-centre source mapped"
        for fam in families:
            spec = _IMPLEMENTED.get(fam)
            if not spec:
                continue
            for key in ("timeline", "stats", "lineups", "periods", "standings", "player_stats", "venue", "officials", "sport_detail"):
                incoming = spec.get(key)
                current = caps.get(key)
                rank = {
                    "PROVEN": 5,
                    "PARTIAL": 4,
                    "SOURCE_AVAILABLE_NOT_IMPLEMENTED": 3,
                    "ACCESS_BLOCKED": 2,
                    "NOT_APPLICABLE": 1,
                    "NO_ACCESSIBLE_DATA_FOUND": 0,
                }
                if rank.get(incoming, 0) >= rank.get(current, 0):
                    caps[key] = incoming
            if spec.get("implemented"):
                implemented = True
                detail_provider = detail_provider or fam
                adapter = spec.get("adapter") or adapter
                transport = spec.get("transport") or transport
                limitation = spec.get("limitation") or limitation
        if not detail_provider:
            detail_provider = score
        overlay = {}
        if OVERLAY.exists():
            try:
                overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                overlay = {}
        proven = overlay.get(str(comp.get("competition") or "")) if isinstance(overlay, dict) else None
        if isinstance(proven, dict):
            for key in ("timeline", "stats", "lineups", "periods", "standings", "player_stats", "venue", "officials", "sport_detail"):
                if proven.get(key):
                    caps[key] = proven[key]
            limitation = proven.get("limitation") or limitation
        production = False
        if isinstance(proven, dict) and proven.get("production_verified"):
            production = True
        rows.append(
            {
                "competition": comp.get("competition"),
                "sport": sport,
                "score_provider": score,
                "detail_provider": detail_provider,
                "timeline": caps["timeline"],
                "stats": caps["stats"],
                "lineups": caps["lineups"],
                "periods": caps["periods"],
                "standings": caps["standings"],
                "player_stats": caps["player_stats"],
                "venue": caps["venue"],
                "officials": caps["officials"],
                "sport_detail": caps["sport_detail"],
                "transport": transport,
                "Railway_access": railway,
                "adapter": adapter,
                "implemented": implemented,
                "production_verified": production,
                "limitation": limitation,
            }
        )
    rows.sort(key=lambda row: str(row["competition"]))
    return rows


def write_artifacts() -> List[Dict[str, Any]]:
    rows = build_rows()
    out_dir = ROOT / "audit"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "rich_capability_180.json").write_text(json.dumps({"count": len(rows), "rows": rows}, indent=2), encoding="utf-8")
    fields = list(rows[0].keys()) if rows else []
    with (out_dir / "rich_capability_180.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    data = write_artifacts()
    print(len(data))
