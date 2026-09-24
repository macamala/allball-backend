import json

from collector.html_parse import _quoted_window_json


def _encode(payload):
    return json.dumps(payload).replace("\\", "\\\\").replace('"', '\\"')


def test_bbc_window_json_allows_spaces_around_assignment():
    payload = {"eventGroups": [{"displayLabel": "Tokyo Open"}]}
    html = f'<script>window.__INITIAL_DATA__ = "{_encode(json.dumps(payload))}";</script>'
    assert _quoted_window_json(html, "__INITIAL_DATA__") == payload


def test_bbc_window_json_keeps_legacy_assignment_shape():
    payload = {"ok": True}
    html = f'<script>window.__INITIAL_DATA__="{_encode(json.dumps(payload))}";</script>'
    assert _quoted_window_json(html, "__INITIAL_DATA__") == payload
