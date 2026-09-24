"""FotMob total standings, keeping division/group identity and numeric zeroes."""
from typing import Any, Dict, List


def first(*values):
    return next((value for value in values if value is not None and value != ""), None)


def parse_tables(payload: Any) -> List[Dict[str, Any]]:
    found = []
    details = payload.get("details", {}) if isinstance(payload, dict) else {}
    initial_stage = details.get("name") or None

    def take(rows, stage, group):
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            team = item.get("team") if isinstance(item.get("team"), dict) else {}
            name = first(item.get("name"), item.get("shortName"), team.get("name"))
            pts = first(item.get("pts"), item.get("points"))
            played = first(item.get("played"), item.get("matchesPlayed"))
            if not name or (pts is None and played is None):
                continue
            tid = first(item.get("id"), item.get("teamId"), team.get("id"))
            score = str(item.get("scoresStr") or "").split("-")
            gf, ga = (score[0].strip(), score[1].strip()) if len(score) == 2 else (None, None)
            label = str(group or "").strip()
            if stage and label and not label.lower().startswith(str(stage).lower()):
                label = str(stage) + " " + label
            found.append({
                "position":first(item.get("idx"), item.get("position")), "team":name,
                "team_id":str(tid) if tid is not None else None,
                "logo":f"https://images.fotmob.com/image_resources/logo/teamlogo/{tid}.png" if tid is not None else None,
                "played":played, "wins":item.get("wins"), "draws":item.get("draws"), "losses":item.get("losses"),
                "goals_for":first(item.get("scoresFor"),gf), "goals_against":first(item.get("scoresAgainst"),ga),
                "goal_difference":first(item.get("goalConDiff"),item.get("gd")), "points":pts,
                "form": "".join(str(x) for x in item.get("form", []) if x) if isinstance(item.get("form"),list) else item.get("form"),
                "stage":stage, "group":label or None,
            })

    def walk(node, stage=None, group=None):
        if isinstance(node,list):
            for item in node: walk(item,stage,group)
            return
        if not isinstance(node,dict): return
        label = first(node.get("leagueName"),node.get("groupName"),node.get("name"))
        if node.get("composite") or isinstance(node.get("tables"),list):
            stage = label or stage
        elif label:
            group = label if label != stage else group
        table = node.get("table")
        if isinstance(table,dict) and isinstance(table.get("all"),list):
            take(table["all"],stage,group)
            return
        if isinstance(table,list) and table and isinstance(table[0],dict) and ("pts" in table[0] or "played" in table[0]):
            take(table,stage,group)
            return
        if isinstance(node.get("all"),list):
            take(node["all"],stage,group)
            return
        for key,value in node.items():
            if key in {"data","table","tables","leagueTable","standings"}:
                walk(value,stage,group)

    walk(payload,initial_stage)
    unique = {}
    for row in found:
        key = (row.get("stage"),row.get("group"),row.get("team_id") or row.get("team"))
        unique.setdefault(key,row)
    return list(unique.values())
