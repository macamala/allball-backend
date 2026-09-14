"""Lightweight entity extraction for related/ranking diversity.

Conservative aliases only. Team hits never imply a competition.
Replaceable when a sports-data provider arrives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set

from editorial import sanitize_summary, sanitize_title

GENERIC_TOKENS = {
    "match",
    "game",
    "team",
    "season",
    "goal",
    "win",
    "lost",
    "home",
    "away",
    "coach",
    "player",
    "club",
    "league",
    "night",
    "late",
    "side",
    "news",
    "story",
    "after",
    "before",
    "against",
    "pressure",
    "title",
    "official",
    "line",
    "ups",
    "liveblog",
}


def _norm(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return f" {' '.join(cleaned.split())} "


# Each entry is one entity. Aliases are word-boundary phrases.
ENTITY_ALIASES: Sequence[tuple] = (
    ("tottenham", ("tottenham", "spurs"), "team"),
    ("arsenal", ("arsenal", "gunners"), "team"),
    ("liverpool", ("liverpool",), "team"),
    ("chelsea", ("chelsea",), "team"),
    ("manchester-city", ("manchester city", "man city"), "team"),
    ("manchester-united", ("manchester united", "man utd", "man united"), "team"),
    ("newcastle", ("newcastle",), "team"),
    ("west-ham", ("west ham",), "team"),
    ("aston-villa", ("aston villa",), "team"),
    ("brighton", ("brighton",), "team"),
    ("crystal-palace", ("crystal palace",), "team"),
    ("nottingham-forest", ("nottingham forest",), "team"),
    ("fulham", ("fulham",), "team"),
    ("brentford", ("brentford",), "team"),
    ("everton", ("everton",), "team"),
    ("wolves", ("wolves", "wolverhampton"), "team"),
    ("bournemouth", ("bournemouth",), "team"),
    ("juventus", ("juventus",), "team"),
    ("napoli", ("napoli",), "team"),
    ("inter", ("inter milan", "internazionale", " inter "), "team"),
    ("ac-milan", ("ac milan", " milan "), "team"),
    ("roma", (" as roma", " roma "), "team"),
    ("lazio", ("lazio",), "team"),
    ("atalanta", ("atalanta",), "team"),
    ("fiorentina", ("fiorentina",), "team"),
    ("bologna", ("bologna",), "team"),
    ("sassuolo", ("sassuolo",), "team"),
    ("como", (" como ",), "team"),
    ("lecce", ("lecce",), "team"),
    ("monza", ("monza",), "team"),
    ("cagliari", ("cagliari",), "team"),
    ("real-madrid", ("real madrid",), "team"),
    ("barcelona", ("barcelona", "barca"), "team"),
    ("atletico", ("atletico madrid", "atlético madrid", "atletico"), "team"),
    ("bayern", ("bayern",), "team"),
    ("dortmund", ("borussia dortmund", "dortmund"), "team"),
    ("leipzig", ("rb leipzig", "leipzig"), "team"),
    ("lakers", ("lakers",), "team"),
    ("celtics", ("celtics",), "team"),
    ("knicks", ("knicks",), "team"),
    ("76ers", ("76ers", "sixers", "philadelphia 76ers"), "team"),
    ("clippers", ("clippers",), "team"),
    ("warriors", ("warriors", "golden state"), "team"),
    ("raptors", ("raptors",), "team"),
    ("heat", (" miami heat", " heat "), "team"),
    ("nuggets", ("nuggets",), "team"),
    ("bucks", ("bucks",), "team"),
    ("mavericks", ("mavericks",), "team"),
    ("grizzlies", ("grizzlies",), "team"),
    ("thunder", ("oklahoma city", "thunder"), "team"),
    ("pistons", ("pistons",), "team"),
    ("olympiacos", ("olympiacos",), "team"),
    ("de-zerbi", ("de zerbi", "dezerbi"), "person"),
    ("spalletti", ("spalletti",), "person"),
    ("mourinho", ("mourinho",), "person"),
    ("fabregas", ("fabregas", "fàbregas", "cesc"), "person"),
    ("zenga", ("zenga",), "person"),
    ("allegri", ("allegri",), "person"),
    ("capello", ("capello",), "person"),
    ("emery", ("unai emery", "emery"), "person"),
    ("arteta", ("arteta",), "person"),
    ("slot", ("arneslot", "arna slot"), "person"),
    ("lebron", ("lebron", "lebron james"), "person"),
    ("kawhi", ("kawhi",), "person"),
    ("dillon-jones", ("dillon jones",), "person"),
)


@dataclass
class ArticleEntities:
    teams: Set[str] = field(default_factory=set)
    people: Set[str] = field(default_factory=set)
    tokens: Set[str] = field(default_factory=set)

    @property
    def all_ids(self) -> Set[str]:
        return set(self.teams) | set(self.people)


def _padded_alias(alias: str) -> str:
    return alias if alias.startswith(" ") or alias.endswith(" ") else f" {alias.strip()} "


def extract_entities(
    title: Optional[str] = None,
    summary: Optional[str] = None,
    extra: Optional[str] = None,
) -> ArticleEntities:
    blob = _norm(
        " ".join(
            [
                sanitize_title(title or ""),
                sanitize_summary(summary or "", title=title),
                extra or "",
            ]
        )
    )
    found = ArticleEntities()
    for entity_id, aliases, kind in ENTITY_ALIASES:
        for alias in aliases:
            needle = _padded_alias(_norm(alias).strip())
            if len(needle.strip()) < 3:
                continue
            if needle in blob or (needle.strip() in blob and len(needle.strip().split()) > 1):
                if kind == "team":
                    found.teams.add(entity_id)
                else:
                    found.people.add(entity_id)
                break
    found.tokens = significant_tokens(blob)
    return found


def significant_tokens(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9']{4,}", (text or "").lower())
    return {word for word in words if word not in GENERIC_TOKENS}


def shared_count(left: Iterable[str], right: Iterable[str]) -> int:
    return len(set(left) & set(right))
