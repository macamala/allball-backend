"""News03 discovery candidates, NOT republication licences or coverage claims.

Every active News sport has a source-review row. A landing page is not an RSS
feed. Only actual RSS/Atom metadata may be admitted by the later feed adapter.
Original text, source factuality, image rights and required credits need their
own acceptance; a successful HTTP read proves none of those things.
"""
from sports_registry.sports import SPORTS

# (canonical sport, publisher, discovery URL, expected representation)
SOURCE_CANDIDATES = [
    ("football", "FIFA", "https://inside.fifa.com/news", "landing"),
    ("football", "BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml", "rss"),
    ("basketball", "FIBA", "https://www.fiba.basketball/en/news", "landing"),
    ("basketball", "ESPN", "https://www.espn.com/espn/rss/nba/news", "rss"),
    ("tennis", "ATP Tour", "https://www.atptour.com/en/media/rss-feed/xml-feed", "rss"),
    ("tennis", "BBC Sport", "https://feeds.bbci.co.uk/sport/tennis/rss.xml", "rss"),
    ("motorsport", "FIA", "https://www.fia.com/news", "landing"),
    ("motorsport", "BBC Sport", "https://feeds.bbci.co.uk/sport/formula1/rss.xml", "rss"),
    ("american-football", "NFL", "https://www.nfl.com/news/", "landing"),
    ("american-football", "ESPN", "https://www.espn.com/espn/rss/nfl/news", "rss"),
    ("ice-hockey", "IIHF", "https://www.iihf.com/en/news", "landing"),
    ("ice-hockey", "ESPN", "https://www.espn.com/espn/rss/nhl/news", "rss"),
    ("baseball", "MLB", "https://www.mlb.com/news", "landing"),
    ("baseball", "ESPN", "https://www.espn.com/espn/rss/mlb/news", "rss"),
    ("rugby", "World Rugby", "https://www.world.rugby/news", "landing"),
    ("rugby", "BBC Sport", "https://feeds.bbci.co.uk/sport/rugby-union/rss.xml", "rss"),
    ("rugby-league", "International Rugby League", "https://www.intrl.sport/news/", "landing"),
    ("rugby-league", "BBC Sport", "https://feeds.bbci.co.uk/sport/rugby-league/rss.xml", "rss"),
    ("cricket", "ICC", "https://www.icc-cricket.com/news", "landing"),
    ("cricket", "BBC Sport", "https://feeds.bbci.co.uk/sport/cricket/rss.xml", "rss"),
    ("volleyball", "FIVB", "https://www.fivb.com/feed/", "rss"),
    ("handball", "IHF", "https://www.ihf.info/media-center/news", "landing"),
    ("futsal", "FIFA", "https://www.fifa.com/en/tournaments/mens/futsalworldcup", "landing"),
    ("water-polo", "World Aquatics", "https://www.worldaquatics.com/water-polo/news", "landing"),
    ("field-hockey", "FIH", "https://www.fih.hockey/news", "landing"),
    ("australian-rules", "AFL", "https://www.afl.com.au/news", "landing"),
    ("netball", "World Netball", "https://netball.sport/feed/", "rss"),
    ("lacrosse", "World Lacrosse", "https://worldlacrosse.sport/feed/", "rss"),
    ("table-tennis", "ITTF", "https://www.ittf.com/feed/", "rss"),
    ("badminton", "BWF", "https://bwfbadminton.com/feed/", "rss"),
    ("snooker", "World Snooker Tour", "https://www.wst.tv/news", "landing"),
    ("snooker", "BBC Sport", "https://feeds.bbci.co.uk/sport/snooker/rss.xml", "rss"),
    ("darts", "PDC", "https://www.pdc.tv/news", "landing"),
    ("boxing", "World Boxing", "https://worldboxing.org/feed/", "rss"),
    ("boxing", "BBC Sport", "https://feeds.bbci.co.uk/sport/boxing/rss.xml", "rss"),
    ("mma", "UFC", "https://www.ufc.com/trending/all", "landing"),
    ("horse-racing", "British Horseracing Authority", "https://www.britishhorseracing.com/feed/", "rss"),
    ("horse-racing", "BBC Sport", "https://feeds.bbci.co.uk/sport/horse-racing/rss.xml", "rss"),
    ("greyhound-racing", "GBGB", "https://www.gbgb.org.uk/feed/", "rss"),
    ("harness-racing", "Harness Racing Australia", "https://www.harness.org.au/news/", "landing"),
    ("golf", "PGA Tour", "https://www.pgatour.com/news", "landing"),
    ("golf", "BBC Sport", "https://feeds.bbci.co.uk/sport/golf/rss.xml", "rss"),
    ("cycling", "UCI", "https://www.uci.org/news", "landing"),
    ("cycling", "BBC Sport", "https://feeds.bbci.co.uk/sport/cycling/rss.xml", "rss"),
    ("athletics", "World Athletics", "https://worldathletics.org/news", "landing"),
    ("athletics", "BBC Sport", "https://feeds.bbci.co.uk/sport/athletics/rss.xml", "rss"),
    ("swimming", "World Aquatics", "https://www.worldaquatics.com/swimming/news", "landing"),
    ("swimming", "BBC Sport", "https://feeds.bbci.co.uk/sport/swimming/rss.xml", "rss"),
    ("winter-sports", "FIS", "https://www.fis-ski.com/inside-fis/news", "landing"),
    ("winter-sports", "BBC Sport", "https://feeds.bbci.co.uk/sport/winter-sports/rss.xml", "rss"),
    ("esports", "ESL", "https://esl.com/article/", "landing"),
    ("ea-sports-fc", "EA FC Pro", "https://www.ea.com/games/ea-sports-fc/fc-pro/news", "landing"),
    ("counter-strike", "Valve", "https://store.steampowered.com/feeds/news/app/730/?l=english", "rss"),
    ("league-of-legends", "Riot Games", "https://lolesports.com/en-US/news", "landing"),
    ("dota-2", "Valve", "https://www.dota2.com/news", "landing"),
    ("valorant", "Riot Games", "https://valorantesports.com/en-US/news", "landing"),
    ("call-of-duty", "Call of Duty League", "https://www.callofdutyleague.com/en-us/news", "landing"),
    ("overwatch", "Overwatch Esports", "https://esports.overwatch.com/en-us/news", "landing"),
    ("rocket-league", "Rocket League", "https://www.rocketleague.com/en/news/", "landing"),
]


def news_sport_ids():
    return tuple(row["id"] for row in SPORTS if row["active"] and row["supports_news"])


def validate_catalog():
    expected = set(news_sport_ids())
    actual = {row[0] for row in SOURCE_CANDIDATES}
    if actual != expected:
        raise ValueError(f"News discovery catalog mismatch: missing={expected-actual}, extra={actual-expected}")
    if len({row[2] for row in SOURCE_CANDIDATES}) != len(SOURCE_CANDIDATES):
        raise ValueError("Duplicate discovery URLs")
    return True
