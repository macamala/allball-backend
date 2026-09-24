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
    "colombia-primera-a": "https://images.fotmob.com/image_resources/logo/leaguelogo/274.png",
    "womens-super-league": "https://img.sofascore.com/api/v1/unique-tournament/1044/image",
    "uruguay-primera": "https://images.fotmob.com/image_resources/logo/leaguelogo/161.png",
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
    if sport_id != "football":
        return None
    public_key = str((extra or {}).get("public_competition_key") or "").strip()
    return (
        _VERIFIED_FOOTBALL_COMPETITIONS.get(public_key)
        or _VERIFIED_FOOTBALL_COMPETITIONS.get(str(competition_id or "").strip())
    )
