from bot.rewrite_ai import _is_quota_error, _parse_openai_error


class _FakeResp:
    def __init__(self, payload, headers=None, text=""):
        self._payload = payload
        self.headers = headers or {}
        self.content = b"{}" if payload is not None else b""
        self.text = text

    def json(self):
        return self._payload


def test_parse_insufficient_quota_body():
    resp = _FakeResp(
        {
            "error": {
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }
        }
    )
    info = _parse_openai_error(resp)
    assert info["code"] == "insufficient_quota"
    assert _is_quota_error(info) is True


def test_parse_rate_limit_body_is_not_quota():
    resp = _FakeResp(
        {
            "error": {
                "message": "Rate limit reached for gpt-4.1-mini in tokens per min.",
                "type": "tokens",
                "code": "rate_limit_exceeded",
            }
        },
        headers={"retry-after": "8"},
    )
    info = _parse_openai_error(resp)
    assert info["code"] == "rate_limit_exceeded"
    assert info["retry_after"] == "8"
    assert _is_quota_error(info) is False
