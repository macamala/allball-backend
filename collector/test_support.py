"""Deterministic in-process adapters for collector tests only.

These are not production sports providers. They must be registered explicitly
by tests and must never be imported by the worker.
"""

from __future__ import annotations

from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult


class DeterministicMockAdapter:
    adapter_key = "deterministic-mock"
    source_id = "test-mock"

    def __init__(self, source_id: str = "test-mock"):
        self.source_id = source_id
        self.calls: List[FetchRequest] = []
        self.fail_times = 0
        self.restricted = False
        self.events: List[Dict[str, Any]] = []
        self.standings: List[Dict[str, Any]] = []
        self.rankings: List[Dict[str, Any]] = []
        self._failures_seen = 0

    def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request)
        if self.restricted:
            return FetchResult(
                ok=False,
                http_status=403,
                restricted=True,
                error="access restricted",
            )
        if self._failures_seen < self.fail_times:
            self._failures_seen += 1
            return FetchResult(ok=False, http_status=500, error="transient")
        events = [row for row in self.events if self._matches(row, request)]
        standings = self.standings if request.capability == "standings" else []
        rankings = self.rankings if request.capability == "rankings" else []
        if request.capability in {"live_scores", "fixtures", "results", "event", "snapshot"}:
            standings = []
            rankings = []
        return FetchResult(
            ok=True,
            http_status=200,
            payload={"events": events, "standings": standings, "rankings": rankings},
            events=events,
            standings=standings,
            rankings=rankings,
        )

    def _matches(self, row: Dict[str, Any], request: FetchRequest) -> bool:
        if request.capability == "live_scores" and str(row.get("status") or "").lower() != "live":
            return False
        if request.capability == "results" and str(row.get("status") or "").lower() not in {
            "finished",
            "ft",
            "final",
        }:
            return False
        if request.capability == "fixtures" and str(row.get("status") or "").lower() == "live":
            return True
        return True


def mock_event(**overrides: Any) -> Dict[str, Any]:
    row = {
        "id": "mock-1",
        "home": {"name": "Mock United", "id": "mock-home"},
        "away": {"name": "Fixture City", "id": "mock-away"},
        "status": "scheduled",
        "start_time": "2026-09-17T15:00:00Z",
        "score": {"home": None, "away": None},
        "competition": "",
    }
    row.update(overrides)
    return row
