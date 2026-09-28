"""Deterministic News admission checks. Heuristics, not fact/rights certification."""
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTC = timezone.utc
TRACKING = {'fbclid', 'gclid', 'mc_cid', 'mc_eid'}
CRICKET_TITLE_RE = re.compile(
    r"(?<!\w)(?:cricket|t20i?s?|odis?|(?:20|50)[\s\-‐‑‒–—]+over)(?!\w)", re.I
)
VOLLEYBALL_TITLE_RE = re.compile(
    r"(?<!\w)(?:volleyball|fivb|eurovolley|odbojka|odbojku|odbojkaš(?:i|e|a|ima|ice|ica|ki|ke)|"
    r"odbojkas(?:i|e|a|ima|ice|ica|ki|ke))(?!\w)", re.I
)


def numeric_tokens(text):
    return set(re.findall(r'(?<!\w)\d+(?:[.,:/–-]\d+)*(?:%|\b)', text or ''))
_NAME_START_STOP = {'The','This','That','These','Those','After','Before','With','When','While','But','And','For','From','Into','During'}
_PROPER_NAME_RE = re.compile(
    r"\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,})(?:[ \t]+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}|de|da|del|di|la|le|van|von)){1,4}\b"
)


def protected_proper_names(text):
    """Conservative multi-word names that automated copy must preserve exactly."""
    output = []
    seen = set()
    for match in _PROPER_NAME_RE.finditer(text or ''):
        value = match.group(0).strip()
        first = value.split()[0]
        key = value.casefold()
        if first in _NAME_START_STOP or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def canonical_news_url(value):
    if not isinstance(value, str): return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
            return None
        if parts.port not in (None, 80, 443): return None
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in TRACKING]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', urlencode(query), ''))
    except ValueError:
        return None


_SOURCE_PATH_SPORTS = (
    ("www.theguardian.com", "/football/", "football"),
    ("www.sportschau.de", "/fussball/", "football"),
    ("www.sportschau.de", "/handball/", "handball"),
    ("www.sportschau.de", "/basketball/", "basketball"),
    ("www.sportschau.de", "/eishockey/", "ice-hockey"),
    ("www.sportschau.de", "/tennis/", "tennis"),
    ("www.sportschau.de", "/radsport/", "cycling"),
    ("www.sportschau.de", "/wintersport/", "winter-sports"),
    ("www.sportschau.de", "/leichtathletik/", "athletics"),
    ("www.sportschau.de", "/schwimmen/", "swimming"),
    ("www.sportschau.de", "/volleyball/", "volleyball"),
    ("www.sportschau.de", "/motorsport/", "motorsport"),
    ("www.b92.net", "/sport/fudbal/", "football"),
    ("www.b92.net", "/sport/kosarka/", "basketball"),
    ("www.b92.net", "/sport/tenis/", "tennis"),
    ("www.mozzartsport.com", "/fudbal/vesti/", "football"),
    ("www.mozzartsport.com", "/kosarka/vesti/", "basketball"),
    ("www.bbc.co.uk", "/sport/football/", "football"),
    ("www.bbc.co.uk", "/sport/tennis/", "tennis"),
    ("www.bbc.co.uk", "/sport/formula1/", "motorsport"),
    ("www.bbc.co.uk", "/sport/rugby-union/", "rugby"),
    ("www.bbc.co.uk", "/sport/rugby-league/", "rugby-league"),
    ("www.bbc.co.uk", "/sport/cricket/", "cricket"),
    ("www.bbc.co.uk", "/sport/basketball/", "basketball"),
    ("www.bbc.co.uk", "/sport/american-football/", "american-football"),
    ("www.bbc.co.uk", "/sport/ice-hockey/", "ice-hockey"),
    ("www.bbc.co.uk", "/sport/baseball/", "baseball"),
    ("www.bbc.co.uk", "/sport/mixed-martial-arts/", "mma"),
    ("www.bbc.co.uk", "/sport/boxing/", "boxing"),
    ("www.bbc.co.uk", "/sport/golf/", "golf"),
    ("www.bbc.co.uk", "/sport/cycling/", "cycling"),
    ("www.bbc.co.uk", "/sport/athletics/", "athletics"),
    ("www.bbc.co.uk", "/sport/swimming/", "swimming"),
    ("www.bbc.co.uk", "/sport/snooker/", "snooker"),
    ("www.bbc.co.uk", "/sport/darts/", "darts"),
    ("www.bbc.co.uk", "/sport/badminton/", "badminton"),
    ("www.bbc.co.uk", "/sport/hockey/", "field-hockey"),
    ("www.bbc.co.uk", "/sport/table-tennis/", "table-tennis"),
    ("www.bbc.co.uk", "/sport/water-polo/", "water-polo"),
    ("www.record.pt", "/modalidades/tenis/", "tennis"),
    ("www.record.pt", "/futebol/", "football"),
    ("www.record.pt", "/internacional/competicoes-de-selecoes/", "football"),
    ("isport.blesk.cz", "/clanek/fotbal-", "football"),
    ("isport.blesk.cz", "/clanek/ostatni-cyklistika/", "cycling"),
    ("www.novosti.rs", "/sport/fudbal/", "football"),
    ("www.blick.ch", "/sport/fussball/", "football"),
    ("www.blick.ch", "/sport/motorsport/", "motorsport"),
)


def source_path_sport_hint(url):
    """Conservative publisher-owned URL-path sport evidence.

    This is only a fallback when article text classification is unresolved. A
    strong textual sport classification always wins over the publisher path.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = (parts.path or "/").lower()
    for expected_host, prefix, sport in _SOURCE_PATH_SPORTS:
        if host == expected_host and path.startswith(prefix):
            return sport
    return None


def publication_time(stamp):
    # Deliberately do not convert timezone-naive metadata to invented UTC.
    if not isinstance(stamp, datetime) or stamp.tzinfo is None: return None
    try: return stamp.astimezone(UTC)
    except (ValueError, OverflowError): return None


def freshness_reason(stamp, now, max_age_hours=72):
    value = publication_time(stamp)
    if value is None: return 'publication_time_unverified'
    if value > now: return 'future_publication'
    if now - value > timedelta(hours=max_age_hours): return 'stale_publication'
    return None


def editorial_day_reason(stamp, now, timezone_name="Australia/Sydney"):
    value = publication_time(stamp)
    if value is None:
        return "publication_time_unverified"
    try:
        zone = ZoneInfo(timezone_name or "Australia/Sydney")
    except Exception:
        zone = UTC
    if value.astimezone(zone).date() != now.astimezone(zone).date():
        return "not_editorial_today"
    return None


def newsworthiness_score(item):
    """Editorial value only; never changes factual admission."""
    blob = " ".join(
        str(item.get(key) or "") for key in ("title", "summary")
    ).lower()
    score = 0
    major_patterns = (
        r"\b(final|semi[- ]?final|champion|championship|title|trophy)\b",
        r"\b(wins?|won|beats?|beat|defeats?|defeated|upset|knockout|knocks? out)\b",
        r"\b(signs?|signed|transfer|joins?|joined|leaves?|depart|sacked|fired|resigns?|retires?|retirement)\b",
        r"\b(injury|injured|ruled out|withdraws?|suspended|banned|ban)\b",
        r"\b(record|world record|contract extension|new contract|appoints?|appointed)\b",
        r"\b(qualifies?|qualified|reaches? (?:the )?final|returns?|comeback)\b",
    )
    for pattern in major_patterns:
        if re.search(pattern, blob):
            score += 4

    supporting_patterns = (
        r"\b(manager|coach|captain|debut|selection|squad|call[- ]?up)\b",
        r"\b(agrees? deal|set to join|medical|extension)\b",
    )
    for pattern in supporting_patterns:
        if re.search(pattern, blob):
            score += 2

    low_patterns = (
        r"\bcalendar\b|\bschedule\b|\bfixture list\b",
        r"\btickets?\b|ticket sale",
        r"\bevent guide\b|fan(?:'s)? guide|how to watch|where to watch",
        r"watch and earn|everything you need to know",
        r"pack probabilities|patch notes|soundtrack|offer\b",
        r"community api|rankings explained|terms and conditions|policy update",
        r"\bpodcast\b|\blisten\b|\baudio\b|\bquiz\b",
        r"rank audit|power rankings?|top \d+|grades?\b|ratings?\b",
    )
    for pattern in low_patterns:
        if re.search(pattern, blob):
            score -= 7
    return score


def non_article_news_reason(item):
    """Reject discovery records that are score/media products, not news articles."""
    title = str((item or {}).get("title") or "").casefold()
    url = str((item or {}).get("url") or "")
    try:
        path = urlsplit(url).path.casefold()
    except ValueError:
        path = ""

    # Confirmed incident: this is a future race schedule/weather guide. A prior
    # Azerbaijan result in its background must never become a Bahrain result.
    if path.rstrip("/") == "/sport/formula1/articles/ckz7zzy4d995o":
        return "non_article_service_guide"
    # Confirmed source: an entertainer's anonymous prediction of a football
    # disciplinary outcome, not an announcement from the club or competition.
    if path.rstrip("/") == "/internacional/paises/inglaterra/detalhe/liam-gallagher-revela-possivel-castigo-do-man-city-e-explode-calem-se-idiotas-neuroticos-desesperados":
        return "non_news_fan_speculation"

    if "weplaystrong-house-on-tour" in path or re.search(r"\bweplaystrong house on tour\b", title):
        return "non_article_event_promotion"
    if re.search(r"\b(?:predlozzi|tipovanja|ludi tiket|kladioničarski tipovi|kladionicarski tipovi)\b", title) or re.search(r"/(?:predlozzi-i-tipovanja|ludi-tiket|najava-dana)-", path):
        return "non_article_betting_product"
    if re.search(r"\b(?:biramo najlepši gol|biramo najlepsi gol|бирамо најлепши гол|vote for (?:the |your )?goal)\b", title):
        return "non_article_fan_poll"
    if re.search(r"^(?:online|uživo|uzivo|уживо)\s*:", title):
        return "non_article_live_program"
    if re.search(r"^(?:na današnji dan|na danasnji dan|на данашњи дан)\b", title):
        return "non_news_retrospective_commentary"

    if re.search(r"\b(?:quiz(?:zes)?|trivia|crosswords?|wordle|guess the|test your knowledge)\b", title):
        return "non_article_quiz"

    if re.search(r"\bpodcast\b|^nbl (?:overtime|now)\b", title) or "/iplayer/episode/" in path or "/podcasts/" in path:
        return "non_article_podcast"
    if re.search(r"\bscorecard\b", title) or "/scorecard/" in path:
        return "non_article_scorecard"
    if re.search(r"\b(?:all-time top scorers?|top international scorers?|most-capped|record collection|how he has scored)\b", title):
        return "non_article_rolling_tracker"
    if re.search(r"\binjury (?:reports?|updates?|trackers?)\b", title) and re.search(
        r"\b(?:updated daily|daily updates?|real[- ]time|fantasy (?:players|managers)|latest)\b", title
    ):
        return "non_article_rolling_tracker"
    if re.search(r"\b(?:roster tracker|off-season tracker|player movement tracker)\b", title):
        return "non_article_rolling_tracker"
    if re.search(r"/(?:photos|photo-gallery|gallery|galleries)/|/news/(?:gallery|photos|in-pictures)-", path) or re.search(
        r"\b(?:photo gallery|in pictures|in photos)\b", title
    ):
        return "non_article_photo_gallery"
    # Confirmed photo-gallery incident: the CMS uses an ordinary /news/ URL.
    if path.rstrip("/") == "/news/2026/09/28/fans-march-across-harbour-bridge-to-launch-grand-final-week":
        return "non_article_photo_gallery"
    if "/fantasy/" in path or re.search(
        r"\bfantasy (?:hockey|football|basketball|baseball|cricket|sports?|drafts?|rankings?|previews?)\b|\bsupercoach (?:nbl|classic)\b", title
    ):
        return "non_article_fantasy_product"
    # Confirmed legacy roundup mixes highlight cards and site acknowledgements.
    if title.strip() == "nrl finals week 3 moments":
        return "non_article_video_highlights"
    if re.search(r"/(?:video|videos|clips)/", path) or re.search(
        r"(?:^|/|-)(?:best-moments|game-highlights|match-highlights|tries-of-the-week)(?:/|-|$)", path
    ) or re.search(
        r"\b(?:game highlights|match highlights|top (?:plays|tries)|tries of the week|best moments|moments that mattered)\b|^top \d+\s*:", title
    ):
        return "non_article_video_highlights"
    if re.search(r"\b(?:race times|qualifying times|weather forecast|how to watch|where to watch|all you need to know|everything you need to know)\b", title):
        return "non_article_service_guide"
    if re.search(r"\b(?:today[’']?s papers|paper talk|newspaper round[- ]?up)\b", title):
        return "non_article_newspaper_roundup"
    # Keep scarce writer requests for factual news rather than opinion/listicle
    # products that repeatedly fail semantic validation or add little news value.
    if re.search(
        r"\b(?:what we learned|takeaways?|power rankings?|waiver wire|player poll|"
        r"most disappointing|our experts?|grades?)\b|^starting (?:5|five):",
        title,
    ):
        return "non_article_analysis"
    if re.search(r"\b(?:trade radio|watch live|listen live)\b", title):
        return "non_article_live_program"

    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    if host == "www.theguardian.com":
        if "/live/" in path:
            return "non_article_live_program"
        if "/blog/" in path or path.startswith("/commentisfree/") or re.search(r"\s\|\s[^|]+$", title):
            return "non_article_analysis"
    if host == "www.record.pt" and path.startswith("/jogo-da-vida/"):
        return "non_sports_lifestyle_section"
    if host == "www.record.pt" and path.startswith("/fora-de-campo/"):
        return "non_sports_off_field_section"
    return None


def publisher_branding_reason(item):
    """Hold outlet-branded drafts; never replace source names with our own."""
    text = "\n".join(str((item or {}).get(k) or "") for k in ("title", "summary", "body"))
    if re.search(r"\b(?:BBC(?:\s+Sport)?|ESPN|Sky\s+Sports|Reuters|Associated\s+Press|BasketNews|TalkBasket|Eurohoops|Yahoo\s+Sports|The\s+Athletic|B92(?:\.sport|\.net)?|Mozzart\s+Sport|Marca|The\s+Guardian|Sportschau|Motorsport\.com)\b", text, re.I):
        return "publisher_branding"
    return None


def gossip_news_reason(item):
    """Reject tabloid/personal gossip and unconfirmed sports rumours before AI."""
    title = str((item or {}).get("title") or "").casefold()
    summary = str((item or {}).get("summary") or "").casefold()
    url = str((item or {}).get("url") or "")
    if not title:
        return None
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = (parts.path or "").casefold()
    except ValueError:
        host = ""
        path = ""

    # Known off-field/tabloid lanes that should never enter NinkoSports News.
    if host == "isport.blesk.cz" and path.startswith("/clanek/blesk-sport/"):
        return "gossip_tabloid_section"
    if any(token in path for token in (
        "/gossip/", "/celebrity/", "/celebrities/", "/wags/", "/lifestyle/",
        "/entertainment/",
    )):
        return "gossip_tabloid_section"

    personal_patterns = (
        r"\b(?:wife|husband|girlfriend|boyfriend|fianc[eé]e?|spouse|partner)\b",
        r"\b(?:ex[- ]?wife|ex[- ]?husband|ex[- ]?girlfriend|ex[- ]?boyfriend)\b",
        r"\b(?:dating|romance|relationship|divorce|split up|breakup|break-up)\b",
        r"\b(?:wedding|marries|married|pregnan\w*|newborn|baby|first child)\b",
        r"\b(?:mansion|luxury home|luxury car|holiday photos?|vacation photos?)\b",
        r"\b(?:instagram|tiktok|viral post|viral photo|social media feud|claps back|fires back)\b",
        r"\b(?:bivš\w* suprug\w*|bivs\w* suprug\w*|suprug\w*|devojk\w*|djevojk\w*|razvod\w*|ljubav\w*|privatni život|privatni zivot)\b",
        r"\b(?:exmanžel\w*|manžel\w*|rozvod\w*|přítelkyn\w*|partnerk\w*)\b",
        r"\b(?:namorad\w*|espos\w*|ex-mulher|casamento|divórci\w*|divorci\w*)\b",
        r"\b(?:novia|novio|esposa|esposo|exmujer|ex mujer|divorcio|romance)\b",
    )
    personal = any(re.search(pattern, title, re.I) for pattern in personal_patterns)

    # Personal matters are allowed only when the headline itself makes a concrete
    # competitive consequence the actual story (e.g. withdrawal/absence).
    competitive_impact = re.search(
        r"\b(?:miss(?:es|ed|ing)?|withdraw\w*|ruled out|unavailable|return\w*|"
        r"injur\w*|suspend\w*|ban(?:ned)?|retires?|retirement|"
        r"match|game|race|final|tournament|championship|qualif\w*)\b",
        title,
        re.I,
    )
    if personal and not competitive_impact:
        return "gossip_personal_life"

    # Rumour/speculation is not NinkoSports news. Confirmed transactions are.
    speculation_patterns = (
        r"\btransfer gossip\b",
        r"\b(?:rumou?r|rumou?rs)\b",
        r"\blinked (?:with|to)\b",
        r"\b(?:could|might|may) (?:join|sign|move|leave)\b",
        r"\b(?:eyeing|monitoring|considering) (?:a |an |the )?(?:move|deal|transfer|player)\b",
        r"\breportedly (?:interested|keen|considering|targeting|wants?)\b",
        r"\b(?:transfer target|on the radar|tipped to join|set sights on)\b",
        r"\b(?:navodno|mogao bi|mogla bi|mogući transfer|moguci transfer|moguć transfer|moguc transfer|могућ трансфер|наводно|могао би)\b",
    )
    speculative = any(re.search(pattern, title, re.I) for pattern in speculation_patterns)
    confirmed = re.search(
        r"\b(?:official(?:ly)?|confirm(?:s|ed)?|announce(?:s|d)?|signed|signs|"
        r"joined|joins|completed|completes|agreement|agreed deal|new contract|"
        r"contract extension|loan completed|club confirms?)\b",
        title,
        re.I,
    )
    if speculative and not confirmed:
        return "gossip_unconfirmed_rumour"

    # Explicit gossip/rumour roundups are rejected even if a summary contains
    # sports terms. This is title-led so normal factual reports are unaffected.
    if re.search(r"\b(?:gossip|rumour mill|rumor mill|transfer whispers)\b", title, re.I):
        return "gossip_roundup"

    # NinkoSports main News is current reporting, not nostalgia/opinion around
    # old matches. Keep genuinely new factual events, reject retrospective copy.
    retrospective = re.search(
        r"\b(?:look(?:s|ed)? back|looking back|recall(?:s|ed)?|remember(?:s|ed)?|"
        r"revisit(?:s|ed)?|reflect(?:s|ed)? on|years? on|anniversary|"
        r"cast in new light|in new light|nostalgia|opinion|column|commentary)\b",
        title,
        re.I,
    )
    new_fact = re.search(
        r"\b(?:wins?|won|beats?|defeats?|signs?|signed|joins?|joined|"
        r"confirm(?:s|ed)?|announce(?:s|d)?|appoint(?:s|ed)?|sack(?:s|ed)?|"
        r"injur\w*|ruled out|suspend\w*|ban(?:ned)?|qualif\w*|"
        r"record|contract|transfer completed|agreed deal)\b",
        title,
        re.I,
    )
    current_year = datetime.now(UTC).year
    old_year_reference = any(
        int(value) < current_year
        for value in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)
    )
    reflective_old_story = old_year_reference and re.search(
        r"\b(?:credits?|recalls?|remembers?|reflects?|opens up|looks back|"
        r"revisits?|reveals?|reminisces?|explains what|says? .* meant)\b",
        title,
        re.I,
    )
    if (retrospective or reflective_old_story) and not new_fact:
        return "non_news_retrospective_commentary"

    return None


def non_sports_personal_life_reason(item):
    """Reject clearly personal/lifestyle headlines unless sport is the actual event."""
    title = str((item or {}).get("title") or "").casefold()
    if not title:
        return None

    personal_patterns = (
        r"\b(?:wedding|marries|married|pregnan\w*|newborn|first child)\b",
        r"\b(?:becomes?|became|welcomes?)\s+(?:a\s+)?(?:mother|father|mum|mom|dad)\b",
        r"\bhochzeit\b|\bheirat\w*\b|\bschwanger\w*\b|\bmama geworden\b|\bpapa geworden\b",
        r"\bcasamento\b|\bgrávida\b|\bgravida\b|\bprimeiro filho\b|\bprimeira filha\b",
        r"\bboda\b|\bembarazad\w*\b|\bprimer hijo\b|\bprimera hija\b",
    )
    if not any(re.search(pattern, title, re.I) for pattern in personal_patterns):
        return None

    # Keep a personal-life headline only when the title itself says the story
    # materially affects competition, selection or playing status.
    sport_impact_patterns = (
        r"\b(?:match|game|race|round|final|semi[- ]?final|tournament|season|league|cup|championship|qualif\w*)\b",
        r"\b(?:miss(?:es|ed|ing)?|withdraw\w*|ruled out|return\w*|retir\w*|injur\w*|suspend\w*|ban(?:ned)?|transfer\w*|sign\w*)\b",
        r"\b(?:spiel\w*|rennen\w*|saison|liga|meisterschaft|qualifikation|ausfall|verletzt\w*|rückkehr|kader)\b",
        r"\b(?:partid\w*|jogo\w*|corrida|temporada|campeonato|qualifica\w*|les[aã]o|desfalque|regresso)\b",
    )
    if any(re.search(pattern, title, re.I) for pattern in sport_impact_patterns):
        return None
    return "non_sports_personal_life"


def candidate_readiness_score(item):
    """Cheap admission-readiness hint; never grants publication permission."""
    score = 0
    title = str((item or {}).get("title") or "")
    # Quote-heavy interview headlines are valid news but are harder for the
    # automated no-direct-quote lane. Prefer clean factual reports first while
    # retaining these candidates for later in the same fair queue.
    if re.search(r'["“”‘’][^"“”‘’]{6,}["“”‘’]', title):
        score -= 2
    extracted = str((item or {}).get("_extracted") or "").strip()
    summary = str((item or {}).get("summary") or "").strip()
    if extracted:
        score += 4
    else:
        summary_words = len(re.findall(r"\b\w+\b", summary, re.UNICODE))
        if summary_words >= 25:
            # The ingest path accepts 25+ clean RSS words as a factual fallback
            # when a publisher page is JS-only/202. Try these before candidates
            # that depend entirely on a later page extraction.
            score += 4
        elif 0 < summary_words < 12:
            score -= 2
    if str((item or {}).get("_extracted_image") or "").strip():
        score += 3
    elif (item or {}).get("image_candidates") or (item or {}).get("image"):
        score += 2
    feed = (item or {}).get("feed") or {}
    if feed.get("kind") == "league" and feed.get("sport"):
        score += 1
    if feed.get("verified_official") is True:
        score += 2
    return score


def queue_priority_score(item, now):
    """Blend editorial value with freshness; today's verified news comes first."""
    score = newsworthiness_score(item)
    stamp = publication_time(item.get("published_at"))
    if stamp is None:
        return score
    try:
        editorial_tz = ZoneInfo(os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney")
    except Exception:
        editorial_tz = UTC
    if stamp.astimezone(editorial_tz).date() == now.astimezone(editorial_tz).date():
        score += 12
    age_hours = max(0.0, (now - stamp).total_seconds() / 3600.0)
    if age_hours <= 2:
        score += 6
    elif age_hours <= 6:
        score += 5
    elif age_hours <= 12:
        score += 4
    elif age_hours <= 24:
        score += 3
    elif age_hours <= 48:
        score += 1
    return score


def fair_news_queue(
    items,
    classify,
    *,
    now=None,
    max_age_hours=72,
    sport_order=(),
    sport_inventory=None,
    coverage_floor=6,
    same_day_timezone=None,
    prioritize_major_sports=False,
):
    """Newest per sport, then round robin; classify evidence before spending AI.

    Rotate starting sport across time slots so a small per-cycle budget does not
    permanently favor alphabetically early sports. No source date is changed.
    """
    now = now or datetime.now(UTC)
    buckets = defaultdict(list)
    rejected = defaultdict(int)
    seen = set()
    for item in items:
        reason = freshness_reason(item.get('published_at'), now, max_age_hours)
        if not reason and same_day_timezone:
            reason = editorial_day_reason(item.get('published_at'), now, same_day_timezone)
        url = canonical_news_url(item.get('url'))
        if reason or not url:
            rejected[reason or 'invalid_source_url'] += 1; continue
        if url in seen:
            rejected['duplicate_source_url'] += 1; continue
        editorial_reason = (
            non_article_news_reason(item)
            or gossip_news_reason(item)
            or non_sports_personal_life_reason(item)
        )
        if editorial_reason:
            rejected[editorial_reason] += 1; continue
        tags = classify(item)
        sport = getattr(tags, 'sport', None)
        if not sport:
            rejected['unknown_sport'] += 1; continue
        seen.add(url)
        # Retain exact source URL for provenance and existing database identity.
        buckets[sport].append(item)
    order = [s for s in sport_order if s in buckets]
    order += sorted(set(buckets) - set(order))
    if order:
        offset = int(now.timestamp() // 600) % len(order)
        rotated = order[offset:] + order[:offset]
        rotation_rank = {sport: index for index, sport in enumerate(rotated)}
        inventory = {
            sport: max(0, int((sport_inventory or {}).get(sport, 0) or 0))
            for sport in order
        }
        floor = max(0, int(coverage_floor or 0))
        underfilled = {sport for sport in order if inventory[sport] < floor}

        if underfilled:
            # Coverage debt beats headline score. A sport with 0-5 current
            # public stories gets the scarce writer slot before a sport with
            # dozens/hundreds. Newsworthiness and rotation only break ties
            # between equally underfilled sports.
            order = sorted(
                order,
                key=lambda sport: (
                    0 if sport in underfilled else 1,
                    inventory[sport],
                    -max(candidate_readiness_score(item) for item in buckets[sport]),
                    -max(queue_priority_score(item, now) for item in buckets[sport]),
                    rotation_rank[sport],
                ),
            )
        else:
            # Once every candidate sport has a basic floor, keep the inventory
            # balanced instead of letting one source-rich sport dominate.
            order = sorted(
                order,
                key=lambda sport: (
                    inventory[sport],
                    -max(candidate_readiness_score(item) for item in buckets[sport]),
                    -max(queue_priority_score(item, now) for item in buckets[sport]),
                    rotation_rank[sport],
                ),
            )

        # Keep one early lane for source-rich headline sports while they are
        # still thin, without taking the first slot away from the emptiest sport.
        # This prevents football/basketball/tennis etc. from sitting at only a
        # handful of stories while the fairness floor is being built across
        # dozens of smaller sports. The anchor rotates every 30 minutes and is
        # disabled once that sport reaches its own modest target.
        if sport_inventory is not None and len(order) > 1:
            anchor_targets = {
                "football": 12,
                "basketball": 8,
                "tennis": 8,
                "cricket": 8,
                "rugby": 8,
                "motorsport": 8,
            }
            anchor_candidates = [
                sport
                for sport, target in anchor_targets.items()
                if sport in buckets and inventory.get(sport, 0) < target
            ]
            if anchor_candidates:
                anchor_index = int(now.timestamp() // 1800) % len(anchor_candidates)
                anchor = anchor_candidates[anchor_index]
                if anchor in order and order[0] != anchor:
                    order.remove(anchor)
                    order.insert(1, anchor)
    queues = {
        sport: deque(
            sorted(
                buckets[sport],
                key=lambda item: (
                    candidate_readiness_score(item),
                    queue_priority_score(item, now),
                    publication_time(item['published_at']),
                ),
                reverse=True,
            )
        )
        for sport in order
    }
    if prioritize_major_sports:
        # Editorial priority: Football, Basketball, another major sport, then
        # a protected coverage lane. All candidates already passed the same
        # freshness/content gates above; priority never creates supply.
        major_weights = {
            "football": 6, "basketball": 4, "tennis": 3,
            "american-football": 2, "cricket": 2, "rugby": 2,
            "rugby-league": 2, "australian-rules": 2, "motorsport": 2,
            "baseball": 2, "ice-hockey": 2, "golf": 1,
            "boxing": 1, "mma": 1, "cycling": 1, "athletics": 1,
        }
        scheduled = defaultdict(int)
        breadth = deque(s for s in order if s not in major_weights)
        major_rank = {s: n for n, s in enumerate(major_weights)}

        def major(exclude=()):
            choices = [s for s in major_weights if queues.get(s) and s not in exclude]
            if not choices:
                return None
            return min(choices, key=lambda s: (
                (max(0, int((sport_inventory or {}).get(s, 0) or 0)) + scheduled[s]) / major_weights[s],
                major_rank[s],
            ))

        def coverage():
            for _ in range(len(breadth)):
                sport = breadth.popleft()
                breadth.append(sport)
                if queues[sport]:
                    return sport
            return None

        output = []
        while any(queues.values()):
            for lane in ("football", "basketball", "major", "coverage"):
                sport = lane if queues.get(lane) else None
                if lane == "major":
                    sport = major(exclude=("football", "basketball"))
                elif lane == "coverage":
                    sport = coverage()
                sport = sport or major() or coverage()
                if sport:
                    output.append(queues[sport].popleft())
                    scheduled[sport] += 1
        return output, dict(rejected)
    output = []
    while any(queues.values()):
        for s in order:
            if queues[s]: output.append(queues[s].popleft())
    return output, dict(rejected)


def original_draft_reason(draft, source_title, source_body):
    """Conservative automated draft gate; passing is NOT editorial verification."""
    if not isinstance(draft, dict): return 'missing_original_draft'
    title, summary, body = (draft.get(k) for k in ('title', 'summary', 'body'))
    if not all(isinstance(x, str) and x.strip() for x in (title, summary, body)):
        return 'missing_original_draft'
    admission = (non_article_news_reason(draft) or publisher_branding_reason(draft)
                 or gossip_news_reason(draft))
    if admission:
        return admission
    source = f'{source_title}\n{source_body}'
    output = f'{title}\n{summary}\n{body}'
    if re.search(r'https?://|www\.', output, re.I): return 'external_link_in_copy'
    if re.search(r'read (?:the )?(?:full|original) (?:story|article)|appeared first on', output, re.I):
        return 'publisher_redirect_copy'
    if re.search(r'(?im)^\s*(?:source|sources|powered by|originally published)\s*:', output):
        return 'publisher_footer'
    # Do not rewrite a source quote into an invented quote. For this automated
    # path use paraphrase with necessary in-sentence attribution instead.
    if re.search(r'[“\"]([^”\"\n]{8,})[”\"]', output): return 'direct_quote_requires_review'
    source_title_norm = " ".join(re.findall(r"[\w]+", source_title.casefold()))
    draft_title_norm = " ".join(re.findall(r"[\w]+", title.casefold()))
    source_title_words = source_title_norm.split()
    if len(source_title_words) >= 5 and draft_title_norm == source_title_norm:
        return 'copied_source_headline'
    if (
        len(source_title_words) >= 7
        and len(draft_title_norm.split()) >= 7
        and SequenceMatcher(None, source_title_norm, draft_title_norm).ratio() > 0.88
    ):
        return 'headline_too_similar_to_source'
    if numeric_tokens(output) - numeric_tokens(source): return 'unsupported_number'
    tokens = lambda text: re.findall(r"[\w]+", text.lower())
    src, dst = tokens(source_body), tokens(body)
    if len(dst) < 25: return 'insufficient_original_body'
    # A concise rewrite may legitimately omit secondary source names.
    # What it must never do is introduce/rename a multi-word proper name that
    # was not present in the bounded writer input.
    # Proper names are validated by the separate factual validator, which
    # receives the source and returns changed_names explicitly. Avoid a brittle
    # regex gate here: literary headlines and title-case phrases otherwise create
    # false holds before semantic validation can judge them.
    if src == dst: return 'copied_source_body'
    n = 8
    grams = {tuple(src[i:i+n]) for i in range(max(0, len(src)-n+1))}
    copied = sum(tuple(dst[i:i+n]) in grams for i in range(max(0, len(dst)-n+1)))
    if copied / max(1, len(dst)-n+1) > 0.20: return 'excessive_source_overlap'
    if len(src) >= 180 and len(dst) < 140: return 'summary_only_rewrite'
    if len(dst) >= 140 and len([p for p in body.split('\n\n') if p.strip()]) < 2:
        return 'missing_paragraph_structure'
    return None
