"""Read bounded, named public CMS components without executing page scripts."""
import json
from html.parser import HTMLParser


class _Components(HTMLParser):
    def __init__(self, wanted):
        super().__init__(convert_charrefs=True)
        self.wanted = set(wanted)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        row = dict(attrs)
        name = row.get("data-component")
        if name not in self.wanted or name in self.values:
            return
        raw = row.get("data-props") or ""
        if not raw or len(raw) > 500_000:
            return
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return
        if isinstance(value, dict):
            self.values[name] = value


def public_components(html, names):
    parser = _Components(names)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return {}
    return parser.values
