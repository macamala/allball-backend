"""Verified last-resort participant artwork seeds.

These are used only when a participant logo is blank. They never overwrite
source-native artwork. IDs were verified against public provider team pages.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from collector.participant_text import fold_for_identity


_VERIFIED_FOOTBALL_COMPETITIONS: Dict[str, str] = {
    "football-ang-girabola": "https://img.sofascore.com/api/v1/unique-tournament/2308/image",
    "football-dom-liga-mayor": "https://img.sofascore.com/api/v1/unique-tournament/20209/image",
    "football-mar-botola-pro": "https://images.fotmob.com/image_resources/logo/leaguelogo/530.png",
    "football-tun-ligue-1": "https://images.fotmob.com/image_resources/logo/leaguelogo/544.png",
    "football-alg-ligue-1": "https://images.fotmob.com/image_resources/logo/leaguelogo/516.png",
    "football-col-liga-femenina": "https://img.sofascore.com/api/v1/unique-tournament/18555/image",
    "football-can-canadian-premier-league": "https://images.fotmob.com/image_resources/logo/leaguelogo/9986.png",
    "football-gua-liga-nacional": "https://images.fotmob.com/image_resources/logo/leaguelogo/336.png",
    "colombia-primera-a": "https://images.fotmob.com/image_resources/logo/leaguelogo/274.png",
    "womens-super-league": "https://img.sofascore.com/api/v1/unique-tournament/1044/image",
    "uruguay-primera": "https://images.fotmob.com/image_resources/logo/leaguelogo/161.png",
    "argentina-primera": "https://images.fotmob.com/image_resources/logo/leaguelogo/112.png",
    "austria-bundesliga": "https://images.fotmob.com/image_resources/logo/leaguelogo/38.png",
    "brazil-serie-a": "https://images.fotmob.com/image_resources/logo/leaguelogo/268.png",
    "denmark-superliga": "https://images.fotmob.com/image_resources/logo/leaguelogo/46.png",
    "football-friendlies-women": "https://images.fotmob.com/image_resources/logo/leaguelogo/293.png",
    "germany-2-bundesliga": "https://images.fotmob.com/image_resources/logo/leaguelogo/146.png",
    "mls": "https://images.fotmob.com/image_resources/logo/leaguelogo/130.png",
    "spain-copa-del-rey": "https://images.fotmob.com/image_resources/logo/leaguelogo/138.png",
    "sweden-allsvenskan": "https://images.fotmob.com/image_resources/logo/leaguelogo/67.png",
    "switzerland-super-league": "https://images.fotmob.com/image_resources/logo/leaguelogo/69.png",
    "thai-league-1": "https://images.fotmob.com/image_resources/logo/leaguelogo/8984.png",
    "ukraine-premier-league": "https://images.fotmob.com/image_resources/logo/leaguelogo/441.png",
    "uzbekistan-super-league": "https://images.fotmob.com/image_resources/logo/leaguelogo/540.png",
    "womens-super-league": "https://images.fotmob.com/image_resources/logo/leaguelogo/9227.png",
}


_VERIFIED_COMPETITIONS: Dict[tuple[str, str], str] = {
    # Official WTA-hosted artwork from the current WTA brand rollout.
    ("tennis", "wta-tour"): "https://photoresources.wtatennis.com/photo-resources/2025/02/27/bf3c987a-350a-4b59-864b-a5312fd7bcbb/Frame-1-1-2.png?height=500&width=500",
}


_VERIFIED_FOOTBALL: Dict[str, str] = {
    # FotMob team IDs.
    "js omrane": "https://images.fotmob.com/image_resources/logo/teamlogo/1669235.png",
    "omrane": "https://images.fotmob.com/image_resources/logo/teamlogo/1669235.png",
    "progres sakiet eddaier": "https://images.fotmob.com/image_resources/logo/teamlogo/2147000.png",
    "ps sakiet eddaier": "https://images.fotmob.com/image_resources/logo/teamlogo/2147000.png",
    "marsa": "https://images.fotmob.com/image_resources/logo/teamlogo/102105.png",
    "avenir de la marsa": "https://images.fotmob.com/image_resources/logo/teamlogo/102105.png",
    "khenchela": "https://images.fotmob.com/image_resources/logo/teamlogo/1387869.png",
    "usm khenchela": "https://images.fotmob.com/image_resources/logo/teamlogo/1387869.png",
    "mb rouisset": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
    "mb rouissat": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
    "rouisset": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
    "rouissat": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
    # Sofascore team ID.
    "salcedo": "https://img.sofascore.com/api/v1/team/511055/image",
    "salcedo fc": "https://img.sofascore.com/api/v1/team/511055/image",
}


def verified_participant_logo(sport_id: str, side: Any) -> Optional[str]:
    if sport_id != "football" or not isinstance(side, dict):
        return None
    raw = side.get("display_name") or side.get("name") or ""
    folded = fold_for_identity(raw)
    return _VERIFIED_FOOTBALL.get(folded)


def verified_competition_logo(sport_id: str, competition_id: str, extra: Dict[str, Any]) -> Optional[str]:
    sport = str(sport_id or "").strip()
    competition = str(competition_id or "").strip()
    public_key = str((extra or {}).get("public_competition_key") or "").strip()
    if sport == "football":
        return (
            _VERIFIED_FOOTBALL_COMPETITIONS.get(public_key)
            or _VERIFIED_FOOTBALL_COMPETITIONS.get(competition)
        )
    return (
        _VERIFIED_COMPETITIONS.get((sport, public_key))
        or _VERIFIED_COMPETITIONS.get((sport, competition))
    )
