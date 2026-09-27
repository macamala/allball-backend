import bot.data_news as data_news


def _football(event_id='evt-1', home='Northbridge Athletic', away='Southport United',
              home_score=2, away_score=1):
    return {
        'id': event_id,
        'sport': 'football',
        'competition_key': 'england-premier-league',
        'competition': 'Premier League',
        'competition_name': 'Premier League',
        'status': 'finished',
        'home': {'name': home},
        'away': {'name': away},
        'score': {'home': home_score, 'away': away_score},
        'provider': 'MUST_NOT_LEAK',
        'source_family': 'MUST_NOT_LEAK',
    }


def test_api_base_is_fixed_to_public_ninkosports_backend(monkeypatch):
    monkeypatch.delenv('NEWS_SPORTS_API_BASE', raising=False)
    assert data_news._api_base() == 'https://allball-backend-production.up.railway.app'
    monkeypatch.setenv('NEWS_SPORTS_API_BASE', 'https://evil.example')
    assert data_news._api_base() is None


def test_data_news_requires_explicit_feature_flag(monkeypatch):
    monkeypatch.delenv('NEWS_DATA_NEWS_ENABLED', raising=False)
    assert not data_news.data_news_available()
    monkeypatch.setenv('NEWS_DATA_NEWS_ENABLED', '1')
    assert data_news.data_news_available()


def test_single_final_match_builds_original_result_brief_without_provider_branding():
    draft=data_news.build_result_brief(
        'football','england-premier-league','2026-09-27',[_football()]
    )
    assert draft
    assert draft['event_ids'] == ['evt-1']
    assert 'Northbridge Athletic beat Southport United 2-1' in draft['title']
    assert 'Northbridge Athletic beat Southport United 2-1' in draft['body']
    assert 'MUST_NOT_LEAK' not in draft['title'] + draft['summary'] + draft['body']


def test_duplicate_event_id_is_counted_once():
    row=_football()
    draft=data_news.build_result_brief(
        'football','england-premier-league','2026-09-27',[row,dict(row)]
    )
    assert draft and draft['event_ids'] == ['evt-1']
    assert draft['summary'].startswith('NinkoSports Result Brief: 1 finalized')


def test_draw_is_described_without_inventing_winner():
    draft=data_news.build_result_brief(
        'football','england-premier-league','2026-09-27',
        [_football(home_score=1,away_score=1)]
    )
    assert draft
    assert 'finished 1-1' in draft['body']
    assert ' beat ' not in draft['body'].split('This result brief',1)[0]


def test_race_winner_can_build_brief_without_team_score():
    event={
        'id':'race-1','sport':'motorsport','competition_key':'formula-1',
        'competition':'Formula 1','competition_name':'Formula 1','status':'finished',
        'winner':{'name':'Driver Example'},'race_name':'Australian Grand Prix',
    }
    draft=data_news.build_result_brief('motorsport','formula-1','2026-09-27',[event])
    assert draft
    assert 'Driver Example was recorded as the winner of Australian Grand Prix' in draft['body']


def test_event_without_final_result_fact_is_held():
    event={
        'id':'evt-empty','sport':'football','competition_key':'england-premier-league',
        'competition_name':'Premier League','status':'finished',
        'home':{'name':'Northbridge Athletic'},'away':{'name':'Southport United'},
        'score':{'home':None,'away':None},
    }
    assert data_news.build_result_brief(
        'football','england-premier-league','2026-09-27',[event]
    ) is None


def test_result_news_uses_sydney_local_day_bounds(monkeypatch):
    monkeypatch.setenv('NEWS_EDITORIAL_TIMEZONE', 'Australia/Sydney')
    start,end=data_news._day_bounds_utc('2026-09-27')
    assert start == '2026-09-26T14:00:00Z'
    assert end == '2026-09-27T13:59:59.999999Z'


def test_invalid_editorial_timezone_falls_back_safely(monkeypatch):
    monkeypatch.setenv('NEWS_EDITORIAL_TIMEZONE', 'Not/A_Real_Zone')
    start,_=data_news._day_bounds_utc('2026-09-27')
    assert start == '2026-09-26T14:00:00Z'
