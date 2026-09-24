"""Verified last-resort participant artwork seeds.

These are used only when a participant logo is blank. They never overwrite
source-native artwork. IDs were verified against public provider team pages.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from collector.participant_text import fold_for_identity


_VERIFIED_FOOTBALL: Dict[str, str] = {
    # FotMob team IDs.
    "js omrane": "https://images.fotmob.com/image_resources/logo/teamlogo/1669235.png",
    "progres sakiet eddaier": "https://images.fotmob.com/image_resources/logo/teamlogo/2147000.png",
    "ps sakiet eddaier": "https://images.fotmob.com/image_resources/logo/teamlogo/2147000.png",
    "marsa": "https://images.fotmob.com/image_resources/logo/teamlogo/102105.png",
    "avenir de la marsa": "https://images.fotmob.com/image_resources/logo/teamlogo/102105.png",
    "khenchela": "https://images.fotmob.com/image_resources/logo/teamlogo/1387869.png",
    "usm khenchela": "https://images.fotmob.com/image_resources/logo/teamlogo/1387869.png",
    "mb rouisset": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
    "mb rouissat": "https://images.fotmob.com/image_resources/logo/teamlogo/1792386.png",
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
