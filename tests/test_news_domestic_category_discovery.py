from datetime import date
from types import SimpleNamespace
import pytest
from bot.news_competition_vocabulary import corrected_qualified_football_league
from bot.news_fact_guard import competition_in_source,fact_lock_reason
from bot.news_football_sections import _explicit,_norm,football_news_section
from bot.news_policy import non_article_news_reason
from bot.news_domestic_categories import HTML_INDEXES,RSS_FEEDS
from bot.news_official_indexes import _same_host_url

@pytest.mark.parametrize('phrase',[
    'Série B do Campeonato Brasileiro','Serie B do Campeonato Brasileiro',
    'Série B do Brasileiro','Campeonato Brasileiro Série B','Brasileirão Série B','Brazilian Serie B',
])
def test_exact_brazilian_qualification_is_never_italian_competition(phrase):
    assert competition_in_source('brazil-serie-b',phrase)
    assert not competition_in_source('italy-serie-b',phrase)
    assert _explicit(_norm(phrase))=='brazil-serie-b'
    assert corrected_qualified_football_league('italy-serie-b',phrase)=='brazil-serie-b'

@pytest.mark.parametrize('phrase',['Italian Serie B','Serie B match','A Brazilian player joined an Italian Serie B club','Serie B do Campeonato Brasileiro and Italian Serie B'])
def test_club_geography_or_separate_foreign_label_is_not_a_brazilian_override(phrase):
    assert corrected_qualified_football_league('italy-serie-b',phrase)=='italy-serie-b'


def test_native_body_and_english_draft_use_the_same_literal_country_evidence(monkeypatch):
    from bot import news_fact_guard as guard
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    source='O técnico analisou o jogo pela Série B do Campeonato Brasileiro.'
    draft={'title':'Coach reviews Brazilian Serie B performance','summary':'The football coach discussed the performance.','body':'The coach discussed the Brazilian Serie B match.'}
    assert fact_lock_reason(draft,'Coach reviews match',source,expected_sport='football',expected_league='brazil-serie-b') is None
    draft['body']='The coach discussed the Italian Serie B match.'
    assert fact_lock_reason(draft,'Coach reviews match',source,expected_sport='football')=='unsupported_competition:italy-serie-b'


def test_source_classification_corrects_only_explicit_brazil_label():
    from bot.fetch_sources import _classify_item
    cfg={'title':'Coach reviews match','feed':{'kind':'league','sport':'football'}}
    assert _classify_item(cfg,'The coach discussed the Série B do Campeonato Brasileiro match.').league=='brazil-serie-b'

@pytest.mark.parametrize('phrase',['NB II-es klub','Az NB II bajnokság','Nemzeti Bajnokság II'])
def test_native_second_tier_requires_literal_roman_numeral_identity(phrase):
    assert competition_in_source('hungary-nb-2',phrase)
    assert _explicit(_norm(phrase))=='hungary-nb-2'

@pytest.mark.parametrize('phrase',['NB I-es klub','NB III-es klub','NB IIX','club in Hungary'])
def test_other_or_unknown_hungarian_division_is_not_nb2(phrase):
    assert not competition_in_source('hungary-nb-2',phrase)

@pytest.mark.parametrize('suffix',['u 9. kolu','u 15 sati','u 21. minuti','u 7. kolu'])
def test_croatian_round_or_clock_preposition_does_not_invent_youth_team(suffix):
    a=SimpleNamespace(title='Dinamo i Hajduk igraju derbi',summary='SHNL utakmica igra se '+suffix+'.',content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))!='football-youth'

@pytest.mark.parametrize('marker',['U9','U15','U21','Under-17'])
def test_actual_youth_team_markers_are_preserved(marker):
    a=SimpleNamespace(title=f'{marker} squad prepares for football friendly',summary='',content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))=='football-youth'

@pytest.mark.parametrize('title',['Tanque brilha; dê suas notas','Vitória da equipe: dê sua nota','De suas notas para os jogadores'])
def test_rating_ballot_is_not_independent_news(title):
    assert non_article_news_reason({'title':title})=='non_article_fan_poll'


def test_ticket_promotion_is_distinct_from_reporting_a_sold_out_match():
    assert non_article_news_reason({'title':'Dinamo objavio informacije o ulaznicama za derbi: Svi u Split!'})=='non_article_ticket_promotion'
    assert non_article_news_reason({'title':'Dinamo rasprodao sve ulaznice za derbi na Poljudu'}) is None
    assert non_article_news_reason({'title':'Club criticised after ticket price increase'}) is None


def test_all_added_desks_use_existing_admission_and_do_not_force_a_league():
    from bot.news_football_sources import HTML_INDEXES as all_indexes,RSS_FEEDS as all_feeds
    from bot.feeds import enabled_feeds
    assert len(HTML_INDEXES)==4 and len(RSS_FEEDS)==1
    assert all(c in all_indexes for c in HTML_INDEXES)
    assert all(c in all_feeds for c in RSS_FEEDS)
    assert all(not c.get('league') and c['sport']=='football' for c in (*HTML_INDEXES,*RSS_FEEDS))
    assert RSS_FEEDS[0]['article_body_required'] is True
    assert len({r['url'] for r in enabled_feeds()})==len(enabled_feeds())

@pytest.mark.parametrize('source,path',[
    ('sweden-allsvenskan-category','/damallsvenskan/story/'),
    ('sweden-superettan-category','/allsvenskan/story/'),
    ('brazil-serie-b-category','/sp/basketball/noticia/2026/10/03/story.ghtml'),
    ('croatia-hnl-category','/vijesti/clanak/politics/123.aspx'),
])
def test_wrong_sport_or_unreviewed_article_path_cannot_enter(source,path):
    cfg=next(c for c in HTML_INDEXES if c['id']==source)
    assert _same_host_url(cfg['url'],'https://'+cfg['host']+path,cfg['host'],cfg) is None


def test_exact_brazil_article_route_and_cross_host_rejection():
    cfg=next(c for c in HTML_INDEXES if c['id']=='brazil-serie-b-category')
    url='https://ge.globo.com/sc/futebol/times/avai/noticia/2026/10/02/club-update.ghtml'
    assert _same_host_url(cfg['url'],url,cfg['host'],cfg)==url
    assert _same_host_url(cfg['url'],url.replace('ge.globo.com','evil.example'),cfg['host'],cfg) is None


REGIONAL_URL='https://ge.globo.com/sp/campinas-e-regiao/futebol/times/ponte-preta/noticia/2026/10/02/ponte-preta-pode-amargar-nova-marca-negativa-com-rebaixamento-mais-precoce-da-serie-b.ghtml'

@pytest.mark.parametrize('source',[REGIONAL_URL,REGIONAL_URL+'?utm_source=test'])
def test_regional_bare_serie_b_does_not_default_to_italy_or_invent_brazilian_membership(monkeypatch,source):
    from bot import news_football_sections as sections
    from bot.news_football_priority import candidate_football_section
    monkeypatch.setattr(sections,'_club_section',lambda *args:None)
    a=SimpleNamespace(title='Ponte Preta pode ter o rebaixamento mais precoce da Série B | Ge',
        summary='Levantamento leva em conta a era dos pontos corridos na divisão.',content='',source_url=source,published_at='2026-10-02')
    assert sections.football_news_section(a,today=date(2026,10,3)) is None
    item={'title':a.title,'summary':a.summary,'url':source,'published_at':a.published_at}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='italy-serie-b'),today=date(2026,10,3)) is None


def test_current_brazilian_club_evidence_can_associate_the_regional_story_without_factual_stamp(monkeypatch):
    from bot import news_football_sections as sections
    catalogue={'brazil-serie-b':{'clubs':['Ponte Preta','Avai','Ceara','Athletic Club'],'valid_from':'2026-10-01','valid_until':'2026-10-05'}}
    monkeypatch.setattr(sections,'memberships_for_news',lambda:catalogue)
    monkeypatch.setattr(sections,'_CLUBS',{'valid_from':'2026-01-01','valid_until':'2026-12-31','leagues':{}})
    a=SimpleNamespace(title='Ponte Preta faces early relegation from Serie B',summary='',content='',source_url=REGIONAL_URL,published_at='2026-10-02')
    original=dict(vars(a))
    assert sections.football_news_section(a,today=date(2026,10,3))=='brazil-serie-b'
    assert vars(a)==original

@pytest.mark.parametrize('label',['Italian Serie B','Serie B italiana','Serie B in Italy','Serie Bkt'])
def test_explicit_italian_topic_survives_an_unrelated_publisher_region(label):
    from bot.news_competition_vocabulary import conflicting_regional_serie_alias
    assert not conflicting_regional_serie_alias('italy-serie-b',REGIONAL_URL,label)

@pytest.mark.parametrize('source',[
    REGIONAL_URL.replace('ge.globo.com','ge.globo.com.evil.example'),
    REGIONAL_URL.replace('https://','http://'),
    REGIONAL_URL.replace('https://','https://user:pass@'),
    REGIONAL_URL.replace('ge.globo.com','ge.globo.com:444'),
    'https://ge.globo.com/futebol/futebol-internacional/futebol-italiano/noticia/2026/10/02/story.ghtml',
    'https://ge.globo.com/futebol/brasileirao-serie-b/',None,{},
])
def test_only_reviewed_regional_article_identity_can_block_the_bare_default(source):
    from bot.news_competition_vocabulary import conflicting_regional_serie_alias
    assert not conflicting_regional_serie_alias('italy-serie-b',source,'Serie B match')


def test_explicit_brazilian_label_is_not_suppressed_by_the_regional_guard():
    from bot.news_competition_vocabulary import conflicting_regional_serie_alias
    assert not conflicting_regional_serie_alias('brazil-serie-b',REGIONAL_URL,'Brazilian Serie B')


@pytest.mark.parametrize('phrase',['NB I-es hazai csapat','Az NB I tabellája','Hungarian NB I'])
def test_native_hungarian_first_tier_is_not_hidden_by_second_tier_vocabulary(phrase):
    assert _explicit(_norm(phrase))=='hungary-nb-1'
    assert competition_in_source('hungary-nb-1',phrase)
    assert not competition_in_source('hungary-nb-2',phrase)


def test_mixed_hungarian_friendly_lead_preserves_headline_club_not_opponents_division(monkeypatch):
    from bot import news_football_sections as sections
    from bot.news_football_priority import candidate_football_section
    monkeypatch.setattr(sections,'_club_section',lambda title,*args:'hungary-nb-1' if 'kisvarda' in title else None)
    lead='A Kisvárda fogadta az NB II-es Diósgyőrt. Az NB I tabelláján nyolcadik hazai csapat nyert.'
    assert _explicit(_norm(lead)) is None
    a=SimpleNamespace(title='Hatgólos meccsen a Kisvárda nyert',summary=lead,content='',published_at='2026-10-02')
    assert football_news_section(a,today=date(2026,10,3))=='hungary-nb-1'
    assert candidate_football_section({'title':a.title,'summary':lead,'published_at':a.published_at},SimpleNamespace(sport='football',league='hungary-nb-2'),today=date(2026,10,3))=='hungary-nb-1'


@pytest.mark.parametrize('body',[
    'A felkészülési találkozón a Diósgyőr kétszer is betalált.',
    'The sides met in a club friendly.',
    'The two clubs played a friendly match during the break.',
])
@pytest.mark.parametrize('known',[True,False])
def test_a_friendly_opponents_division_cannot_override_headline_club_or_unknown(monkeypatch,body,known):
    from bot import news_football_sections as sections
    from bot.news_football_priority import candidate_football_section
    monkeypatch.setattr(sections,'_club_section',lambda title,*args:'hungary-nb-1' if known and 'kisvarda' in title else None)
    a=SimpleNamespace(title='Kisvárda wins preparation game',summary='The club hosted NB II side Diósgyőr.',content=body,published_at='2026-10-02')
    expected='hungary-nb-1' if known else None
    assert football_news_section(a,today=date(2026,10,3))==expected
    item={'title':a.title,'summary':a.summary,'_classification_text':body,'published_at':a.published_at}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='hungary-nb-2'),today=date(2026,10,3))==expected


def test_reported_competitive_and_headline_divisions_still_survive(monkeypatch):
    from bot import news_football_sections as sections
    monkeypatch.setattr(sections,'_club_section',lambda *args:'hungary-nb-1')
    competitive=SimpleNamespace(title='Club prepares for its next match',summary='The club will play its next NB II league fixture.',content='A competitive league match.',published_at='2026-10-02')
    assert football_news_section(competitive,today=date(2026,10,3))=='hungary-nb-2'
    explicit=SimpleNamespace(title='NB II club wins a friendly match',summary='',content='A friendly game.',published_at='2026-10-02')
    assert football_news_section(explicit,today=date(2026,10,3))=='hungary-nb-2'


def test_exact_native_friendly_source_and_truncated_rss_lead_remain_in_primary_club_menu(monkeypatch):
    from bot import news_football_sections as sections
    from bot.news_football_priority import candidate_football_section
    monkeypatch.setattr(sections,'_club_section',lambda title,*args:'hungary-nb-1' if 'kisvarda' in title else None)
    body='A felkészülési találkozón a Diósgyőr kétszer is betalált, de ez kevés volt a Kisvárda ellen.\n\nA háromhetes bajnoki szünetben sem maradt mérkőzés nélkül a Kisvárda, amely pénteken felkészülési találkozón fogadta az NB II-es Diósgyőrt. Az NB I tabelláján nyolcadik helyen álló hazai csapat 4–2-re nyert.\n\nA Kisvárdánál a még nem teljesen egészséges Gyurkó Máté mellett a megbetegedő Szikszai Hennagyij és Babják Miroszlav sem léphetett pályára, Oláh Bálint eltiltása pedig erre a mérkőzésre is vonatkozott – jelezte a Kisvárda.\n\nA hazaiak Marko Matanovics szabadrúgásgóljával szerezték meg a vezetést, majd bő negyedórával később Jasmin Mesanovic pörgetett belsővel a bal alsó sarokba, így kétgólos előnnyel vonulhatott szünetre a Kisvárda.\n\nA fordulásra szinte teljes sort cserélt a hazai csapat, a kezdők közül csak a két legfrissebb szerzemény, Amos Youga és Besim Sebecic maradt a pályán. Az NB II-es Diósgyőr büntetőből szépített, majd a korábban nagy helyzetet hibázó Pascal Okoronkwo is betalált.\n\nA hajrában még egyszer-egyszer megzörrent a háló: a vendégek újabb gólja után Martin Chlumecky fejese alakította ki a 4–2-es végeredményt.\n\nA Diósgyőr nemrég edzőváltáson esett át, Feczkó Tamás irányításával azonban jól kezdett a csapat: előbb a Vidi elleni kupameccset, majd a Gyirmót elleni bajnokit is megnyerte. Ezt a sorozatot „szakította meg” most az NB I nyolcadik helyén álló Kisvárda.\n\nKISVÁRDA. 1. félidő: Papp Zs. – Nagy K., Lippai, Serbecic, Soltész D. – Melnik, Youga – Matanovics, Ch. Herc, Ésik Á. – Mesanovic. 2. félidő: Kovács M. – Osztrovka, Serbecic, Chlumecky, Körmendi – Mbock, Youga (Szőr) – Novothny, Bíró B., T. Balogun – Okoronkwo\n\nDIÓSGYŐR: Gróf (Megyeri G.) – Szekszárdi M. (Tóth B.), Szatmári Cs. (Kecskés Á.), Bárdos (Ádám L.) – Révész M (Sáreczki), Gálfi (Vass L.), Holdampf )Khier Bek), Bokros Sz. (Váradi S.) – Galántai (Kiss L.), Borvető (Nagy M.), Medgyes Z. (Gombás)\n\nGólszerző: Matanovics (1–0) a 15., Mesanovic (2–0) a 33., Borveto (11-esből, 2–1) az 54., Okoronkwo (3–1) a 75., Nagy M. (3–2) a 87., Chlumecky (4–2) a 89. percben'
    title='Hatgólos meccsen „szakította meg” a Kisvárda Feczkó Tamás sorozatát'
    # RSS can omit the native source's first paragraph and truncate before
    # its NBI label. Its opponent descriptor cannot become the event identity.
    summary='A háromhetes bajnoki szünetben sem maradt mérkőzés nélkül a Kisvárda, amely pénteken felkészülési találkozón fogadta az NB II-es Diósgyőrt.'
    for lead in [summary,'Az NB II-es Diósgyőr ellen nyert a Kisvárda.']:
        item={'title':title,'summary':lead,'_classification_text':body,'published_at':'2026-10-02'}
        before=dict(item)
        assert candidate_football_section(item,SimpleNamespace(sport='football',league='hungary-nb-2'),today=date(2026,10,3))=='hungary-nb-1'
        assert item==before
