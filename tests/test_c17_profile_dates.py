import pytest
from collector.profile_dates import profile_date
from collector.player_enrichment import parse_profile

@pytest.mark.parametrize('value,expected',[
 (1735689600000,'2025-01-01'),(1735603200000,'2024-12-31'),(1614556800000,'2021-03-01'),
 (1735689600,'2025-01-01'),(1735689600000.0,'2025-01-01'),
 ('2025-01-01T00:00:00.000Z','2025-01-01'),('2025-01-01','2025-01-01'),
 (None,None),('',None),(0,None),(-1,None),(True,None),(float('inf'),None),(float('nan'),None),
 (10**400,None),('2025-02-31',None),('unknown',None),({},None),([],None),
])
def test_optional_profile_date_formats(value,expected):
 assert profile_date(value)==expected

def test_numeric_career_date_does_not_erase_verified_player_fields():
 root={'id':1090170,'name':'Katarina Dybvik Sunde','primaryTeam':{'teamId':4500,'teamName':'Aalesund'},
       'birthDate':{'utcTime':'1997-11-14T00:00:00.000Z'},'marketValues':None,
       'positionDescription':{'primaryPosition':{'label':'Striker'}},
       'careerHistory':{'careerItems':{'senior':{'teamEntries':[
        {'teamId':4500,'team':'Aalesund','startDate':1735689600000,'endDate':'','active':True},
        {'teamId':121521,'team':'Åsane','startDate':1614556800000,'endDate':1735603200000},
        {'teamId':4499,'team':'Arna-Bjørnar','startDate':'','endDate':''}]}}}}
 facts=parse_profile(root,'1090170','Katarina Dybvik Sunde')
 assert facts['current_club']['id']=='4500' and facts['birth_date']=='1997-11-14' and facts['position']=='Striker'
 assert [(x['start'],x['end']) for x in facts['career']]==[('2025-01-01',None),('2021-03-01','2024-12-31'),(None,None)]
 assert 'market_value' not in facts and all(x['appearances'] is None for x in facts['career'])
