"""Reviewed official club feeds in the existing News intake (2026-10-03).

A publisher identity is not a current league or a men's first-team label.
Every item still needs its own date, visible body, photograph and accepted
original reporting. Quiet feeds stay quiet; they are not historical backfills.
"""
import re
from urllib.parse import urlsplit

CLUB_PROFILES = {
    'www.fkvojvodina.rs': {'body_class': 'post-content'},
    'www.fkradnicki.com': {'body_class': 'entry-content'},
    'fkradnickinis.rs': {'body_class': 'entry-content'},
}

RSS_FEEDS = tuple(
    {'url': 'https://' + host + '/feed/', 'publisher': name,
     'kind': 'league', 'sport': 'football', 'enabled': True,
     'verified_official': True, 'article_body_required': True,
     'article_https_host': host, 'article_path_re': r'^/[^/]+/?$',
     'excluded_article_paths': ('/category/', '/tag/', '/wp-', '/feed/', '/shop/', '/page/'),
     'note': 'Same-host visible article body and own social image verified. No blanket league, gender or current-story claim.'}
    for host, name in (
        ('www.fkvojvodina.rs', 'FK Vojvodina'),
        ('www.fkradnicki.com', 'FK Radnicki 1923'),
        ('fkradnickinis.rs', 'FK Radnicki Nis'),
    )
)


def explicit_women_club_headline(canonical, title):
    """Only this reviewed article's own headline establishes the qualifier.

    Never inspect menus, links, recommendation cards, publisher name or an
    incidental paragraph to guess gender. The writer still must retain the
    explicit qualifier in its lead.
    """
    try:
        parts = urlsplit(canonical or '')
        if (parts.scheme != 'https' or parts.hostname not in CLUB_PROFILES
                or parts.username or parts.password or parts.port not in (None, 443)
                or not re.fullmatch(r'/[^/]+/?', parts.path)):
            return False
    except (TypeError, ValueError):
        return False
    return bool(re.search(r'\b(?:жфк|žfk|zfk|женск(?:и|а|е|ог|ој)|žensk(?:i|a|e|og|oj))\b',
                          str(title or ''), re.I))
