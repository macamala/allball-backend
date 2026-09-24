import json

from types import SimpleNamespace

from collector.bbc_tennis_breadth import _competition_id, _source, parse_bbc_tennis_html


def _bbc_html(payload):
    encoded = json.dumps(payload, ensure_ascii=True).replace("\\", "\\\\").replace('"', '\\"')
    return f'__INITIAL_DATA__="{encoded}"'


def test_bbc_tennis_board_keeps_real_tournament_identity():
    html = _bbc_html({
        "eventGroups": [{
            "displayLabel": "Tokyo Open",
            "secondaryGroups": [{
                "events": [{
                    "id": "match-1",
                    "home": {"name": "Player A"},
                    "away": {"name": "Player B"},
                    "startTime": "2026-09-25T03:00:00Z",
                    "status": "scheduled",
                }]
            }],
        }]
    })
    events = parse_bbc_tennis_html(html)
    assert len(events) == 1
    assert events[0]["competition"] == "Tokyo Open"
    assert events[0]["competition_key"].startswith("tennis-bbc-")
    assert events[0]["sport"] == "tennis"
    assert events[0]["event_family"] == "individual_match"
    assert events[0]["source_event_ids"]["bbc-sport"] == "match-1"


def test_bbc_tennis_competition_id_is_stable():
    assert _competition_id("Tokyo Open") == _competition_id("Tokyo Open")



def test_bbc_tennis_breadth_uses_dedicated_global_source():
    source = SimpleNamespace(
        source_id="bbc-tennis-global",
        enabled=True,
        public_branding_required=False,
        licensed=False,
        requires_credentials=False,
        credential_env=None,
    )

    class FakeDb:
        def __init__(self):
            self.requested = []

        def get(self, model, source_id):
            self.requested.append(source_id)
            return source if source_id == "bbc-tennis-global" else None

    db = FakeDb()
    assert _source(db) is source
    assert db.requested == ["bbc-tennis-global"]
