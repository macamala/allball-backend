from collector.atp_official_probe import summarize_payload


def test_atp_initial_scores_payload_summary():
    payload = {
        "liveScores": {
            "Tournaments": [
                {
                    "EventYear": 2026,
                    "Name": "Chengdu Open",
                    "EventId": "7581",
                    "Location": "Chengdu, China",
                    "FormattedDate": "23 - 29 September, 2026",
                    "ScheduleLink": "/en/scores/current/chengdu/7581/daily-schedule",
                    "Matches": [
                        {
                            "Id": "MS012",
                            "RoundTitle": "Round of 16 - Center Court",
                            "MatchType": "singles",
                            "Status": "S",
                            "StartTime": "14:30",
                            "TeamOne": {"PlayerOneName": "Player A"},
                            "TeamTwo": {"PlayerOneName": "Player B"},
                        },
                        {
                            "Id": "MS013",
                            "RoundTitle": "Round of 16 - Court 1",
                            "MatchType": "singles",
                            "Status": "F",
                        },
                    ],
                }
            ]
        }
    }
    summary = summarize_payload(payload)
    assert summary["tournaments"] == 1
    assert summary["matches"] == 2
    assert summary["samples"][0]["event_id"] == "7581"
    assert "TeamOne" in summary["samples"][0]["sample_match_keys"]
