"""RSS sources. Mixed feeds are allowed only with independent classification."""

from typing import Dict, List, Optional, TypedDict


class Feed(TypedDict, total=False):
    url: str
    kind: str  # league | mixed | disabled
    sport: Optional[str]
    league: Optional[str]
    country: Optional[str]
    enabled: bool
    note: str


FEEDS: List[Feed] = [
    # League-specific (hint only; evidence still wins)
    {
        "url": "https://feeds.bbci.co.uk/sport/football/premier-league/rss.xml",
        "kind": "league",
        "sport": "football",
        "league": "england-premier-league",
        "country": "england",
        "enabled": True,
    },
    {
        "url": "https://feeds.bbci.co.uk/sport/football/championship/rss.xml",
        "kind": "league",
        "sport": "football",
        "league": "england-championship",
        "country": "england",
        "enabled": True,
    },
    {
        "url": "https://as.com/rss/futbol/primera.xml",
        "kind": "league",
        "sport": "football",
        "league": "spain-la-liga",
        "country": "spain",
        "enabled": True,
    },
    {
        "url": "https://as.com/rss/futbol/segunda.xml",
        "kind": "league",
        "sport": "football",
        "league": "spain-la-liga-2",
        "country": "spain",
        "enabled": True,
    },
    {
        "url": "https://www.football-italia.net/feed",
        "kind": "league",
        "sport": "football",
        "league": "italy-serie-a",
        "country": "italy",
        "enabled": True,
    },
    {
        "url": "https://www.espn.com/espn/rss/nba/news",
        "kind": "league",
        "sport": "basketball",
        "league": "nba",
        "country": "usa",
        "enabled": True,
    },
    {
        "url": "https://www.espn.com/espn/rss/ncb/news",
        "kind": "league",
        "sport": "basketball",
        "league": "ncaa-basketball",
        "country": "usa",
        "enabled": True,
    },
    {
        "url": "https://www.bbc.co.uk/sport/football/scottish-premiership/rss.xml",
        "kind": "league",
        "sport": "football",
        "league": "scotland-premiership",
        "country": "scotland",
        "enabled": True,
    },
    {
        "url": "https://www.skysports.com/rss/29328",
        "kind": "league",
        "sport": "football",
        "league": "scotland-premiership",
        "country": "scotland",
        "enabled": True,
    },
    {
        "url": "https://www.hln.be/sport/voetbal/rss.xml",
        "kind": "mixed",
        "enabled": True,
        "note": "Belgian football mix; classify independently",
    },
    {
        "url": "https://www.record.pt/rss",
        "kind": "mixed",
        "enabled": True,
        "note": "Portuguese general sport; classify independently",
    },
    {
        "url": "https://isport.blesk.cz/rss",
        "kind": "mixed",
        "enabled": True,
        "note": "Czech general sport; classify independently",
    },
    {
        "url": "https://www.novosti.rs/rss/sport",
        "kind": "mixed",
        "enabled": True,
        "note": "Serbian general sport firehose; never stamp SuperLiga",
    },
    {
        "url": "https://www.talkbasket.net/feed",
        "kind": "mixed",
        "enabled": True,
        "note": "NBA + EuroLeague mix; classify independently",
    },
    {
        "url": "https://www.getfootballnewsfrance.com/feed/",
        "kind": "mixed",
        "enabled": True,
        "note": "Often malformed XML; skipped when bozo",
    },
    {
        "url": "https://www.blick.ch/sport/rss.xml",
        "kind": "mixed",
        "enabled": True,
    },
    {
        "url": "https://www.espn.com/espn/rss/soccer/news",
        "kind": "mixed",
        "enabled": True,
        "note": "Global football mix, not a league stamp",
    },
    {
        "url": "https://feeds.bbci.co.uk/sport/football/german/rss.xml",
        "kind": "mixed",
        "enabled": True,
        "note": "BBC German football mix; classify independently, do not stamp Bundesliga",
    },
    # Disabled: confirmed HTML/broken XML firehoses from production audit
    {
        "url": "https://www.skysports.com/rss/12040",
        "kind": "disabled",
        "enabled": False,
        "note": "General Sky firehose mis-stamped as Premier League",
    },
    {
        "url": "https://www.skysports.com/rss/12040/championship",
        "kind": "disabled",
        "enabled": False,
        "note": "Not well-formed XML",
    },
    {
        "url": "https://www.bundesliga.com/en/bundesliga/rss-feed",
        "kind": "disabled",
        "enabled": False,
        "note": "Not well-formed XML",
    },
    {
        "url": "https://www.kicker.de/bundesliga/rss",
        "kind": "disabled",
        "enabled": False,
        "note": "Returns HTML",
    },
    {
        "url": "https://www.kicker.de/2-bundesliga/rss",
        "kind": "disabled",
        "enabled": False,
        "note": "Returns HTML",
    },
    {
        "url": "https://www.lequipe.fr/rss/actu_rss_Football.xml",
        "kind": "disabled",
        "enabled": False,
        "note": "XML syntax error",
    },
    {
        "url": "https://www.lequipe.fr/rss/actu_rss_Football_Ligue-2.xml",
        "kind": "disabled",
        "enabled": False,
        "note": "XML syntax error",
    },
    {
        "url": "https://www.vi.nl/feeds/nieuws",
        "kind": "disabled",
        "enabled": False,
        "note": "HTML not RSS",
    },
    {
        "url": "https://www.abola.pt/rss",
        "kind": "disabled",
        "enabled": False,
        "note": "XML syntax error",
    },
    {
        "url": "https://www.voetbalprimeur.nl/feed",
        "kind": "disabled",
        "enabled": False,
        "note": "HTML not RSS",
    },
    {
        "url": "https://www.uefa.com/rssfeed/uefachampionsleague/rss.xml",
        "kind": "disabled",
        "enabled": False,
        "note": "Mismatched tags",
    },
    {
        "url": "https://www.fifa.com/rss-feeds/news",
        "kind": "disabled",
        "enabled": False,
        "note": "Not valid RSS",
    },
]


def enabled_feeds() -> List[Feed]:
    return [f for f in FEEDS if f.get("enabled")]
