import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import pytest
from public_index import _correct_confirmed_football_prose, repair_recent_gossip_news

SNAPSHOT=json.loads((Path(__file__).parent/'fixtures/news_duffy_22632.json').read_text())


def original(**changes):
    fields={**SNAPSHOT,'ai_generated':True,'ai_content':SNAPSHOT['content']}
    fields.update(changes)
    return SimpleNamespace(**fields)


def test_only_confirmed_clauses_change_and_every_other_field_is_preserved():
    a=original();before=vars(a).copy()
    changes=_correct_confirmed_football_prose(a)
    assert set(changes)=={'content','ai_content'}
    assert a.content==a.ai_content
    assert hashlib.sha256(a.content.encode()).hexdigest()=='8642b95115a95d990c904f91b841c11702576bde004b4bad6c0f595b48c8cf8b'
    assert 'Tranmere Rovers' in a.content and 'stood down from those duties' not in a.content
    assert {k:v for k,v in vars(a).items() if k not in changes}=={k:v for k,v in before.items() if k not in changes}
    assert _correct_confirmed_football_prose(a)=={}


@pytest.mark.parametrize('changed',[
    {'id':22633}, {'source_url':'https://other.example/story'}, {'title':'Different headline'},
    {'ai_generated':False}, {'sport':'basketball'}, {'content':SNAPSHOT['content']+' Editor update.'},
    {'ai_content':SNAPSHOT['content'].replace('Tranmere Town','Tranmere Rovers')},
])
def test_mismatched_or_already_edited_rows_cannot_be_overwritten(changed):
    a=original(**changed);before=vars(a).copy()
    assert _correct_confirmed_football_prose(a)=={} and vars(a)==before


@pytest.mark.parametrize('public',[True,False])
def test_existing_repair_records_one_incident_and_never_unholds_a_row(public):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Article,ArticleTaxonomyResolution,NewsIncident
    from taxonomy_resolver import RESOLVER_VERSION
    engine=create_engine('sqlite:///:memory:')
    for model in (Article,ArticleTaxonomyResolution,NewsIncident):model.__table__.create(engine)
    with Session(engine) as db:
        a=Article(id=22632,title=SNAPSHOT['title'],summary=SNAPSHOT['summary'],content=SNAPSHOT['content'],
            ai_content=SNAPSHOT['content'],ai_generated=True,slug='duffy-audit',external_id='duffy-audit',
            sport='football',league=None,published_at=datetime.utcnow(),source_url=SNAPSHOT['source_url'])
        db.add(a);db.flush()
        tax=ArticleTaxonomyResolution(article_id=a.id,resolved_sport='football',resolved_competition=None,
            resolver_version=RESOLVER_VERSION,public_ok=public)
        db.add(tax);db.commit();stamp=a.published_at
        assert repair_recent_gossip_news(db)==int(public)
        assert tax.public_ok==public and a.published_at==stamp
        events=db.query(NewsIncident).filter_by(article_id=a.id,status='auto_corrected').all()
        assert len(events)==int(public)
        if public:assert 'neil-danns-stands-down' in events[0].details_json
        assert repair_recent_gossip_news(db)==0
    engine.dispose()
