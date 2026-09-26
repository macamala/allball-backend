"""Bounded public RSS transport with robots checks; never bypasses access denial."""
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = 'NinkoSportsNewsBot/1.0 (+https://ninkosports.com)'
MAX_BYTES = 2_000_000


def validate_public_url(url):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or
            parts.password or parts.port not in (None, 443)):
        raise ValueError('invalid_public_feed_url')
    addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('nonpublic_feed_address')


def _read(client, url, deadline, allowed=None):
    for _ in range(4):
        if time.monotonic() > deadline:
            raise ValueError('feed_deadline')
        validate_public_url(url)
        if allowed is not None and not allowed(url):
            raise ValueError('feed_robots_disallowed')
        with client.stream('GET', url) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get('location', ''))
                old = (urlsplit(url).hostname or '').removeprefix('www.')
                new = (urlsplit(target).hostname or '').removeprefix('www.')
                if not response.headers.get('location') or old != new:
                    raise ValueError('feed_redirect_requires_review')
                url = target
                continue
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError('feed_response_limit')
            return response.status_code, url, bytes(data)
    raise ValueError('feed_redirect_limit')


def read_news_feed(url):
    """Return only a successful allowed feed body. No implicit parse-time I/O.

    The body and read deadline are bounded. DNS and socket establishment still
    depend on the platform resolver; this is not a network sandbox guarantee.
    """
    validate_public_url(url)
    parts = urlsplit(url)
    robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
    deadline = time.monotonic() + 20
    with httpx.Client(timeout=8, follow_redirects=False,
                      headers={'User-Agent': USER_AGENT}) as client:
        status, _, robots_body = _read(client, robots_url, deadline)
        robots = None
        if status == 200:
            robots = RobotFileParser()
            robots.parse(robots_body.decode('utf-8', 'replace').splitlines())
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError('feed_robots_disallowed')
        elif status not in (404, 410):
            raise ValueError('feed_robots_unverified')
        status, final_url, body = _read(client, url, deadline,
            (lambda target: robots.can_fetch(USER_AGENT, target)) if robots else None)
        if robots and not robots.can_fetch(USER_AGENT, final_url):
            raise ValueError('feed_redirect_robots_disallowed')
        if status != 200:
            raise ValueError(f'feed_http_{status}')
        return body
