import json
import pytest
from test_core import add_work
from test_server import lan
from lumen.discovery_catalog import query_discovery,discovery_facets
from lumen.browse import load_view


def discovered(library,title,*,tags=None,score=None,date=None,year=2024,plugin='sample',local=False):
    work=add_work(library,title,year=year,metadata={'tags':tags or [],'aliases':['Alternative '+title],
                                                'discovery_categories':[plugin+':latest']},local=local)
    with library.db:
        library.db.execute('INSERT INTO sources(work_id,plugin,site,source_id,url,updated,site_added,rating) VALUES(?,?,?,?,?,?,?,?)',
                           (work,plugin,plugin,str(work),'https://example.org/'+str(work),'now',date,score))
    return work


def test_discovery_name_and_fuzzy_tag_search_full_catalog_beyond_recommendation_limit(library):
    for i in range(70):discovered(library,f'Documentary {i:02}',tags=['Travel Documentary'],score=i%10)
    wanted=discovered(library,'Far coast',tags=['Travel Documentary'],score=2)
    request={'section':'discover','tab':0,'filters':{'query':'ALTERNATIVE FAR','sort':'title','descending':False},'tag_query':'document'}
    result=load_view(library,request)
    assert [work['id'] for work in result['items']]==[wanted]
    assert result['facets']['tags']==['Travel Documentary']
    assert len(query_discovery(library,{'sort':'title'},tag_query='TRAVEL'))==71
    assert not query_discovery(library,{'query':'Far'},tag_query='missing')


def test_discovery_sort_scores_dates_nulls_and_equal_values_consistent(library):
    unknown=discovered(library,'Unknown',year=None,date=None)
    first=discovered(library,'Alpha',score=8,date='2024-01-03',year=2024)
    tie=discovered(library,'Beta',score=8,date='2024-01-02',year=2020)
    low=discovered(library,'Gamma',score=0,date='not-a-date',year=2022)
    assert [w['id'] for w in query_discovery(library,{'sort':'community_rating'})]==[first,tie,low,unknown]
    assert [w['id'] for w in query_discovery(library,{'sort':'community_rating','descending':False})]==[low,first,tie,unknown]
    assert [w['id'] for w in query_discovery(library,{'sort':'site_added','descending':False})]==[tie,first,unknown,low]
    assert [w['id'] for w in query_discovery(library,{'sort':'year'})]==[first,low,tie,unknown]
    with pytest.raises(ValueError):query_discovery(library,{'sort':'invalid'})


def test_exact_online_hits_allow_safe_local_matches_and_empty_hits_do_not_show_entire_catalog(library):
    local=add_work(library,'Local safe match')
    remote=discovered(library,'Remote match',tags=['Tag'])
    assert [work['id'] for work in query_discovery(library)]==[remote]
    assert [work['id'] for work in query_discovery(library,{'ids':[local]})]==[local]
    assert query_discovery(library,{'ids':[]})==[]
    assert query_discovery(library,{'query':'/media/Remote'})==[]


def test_discovery_lan_search_sort_before_pagination_and_filters_are_independent(lan,library):
    client,_,_,_=lan
    ids=[discovered(library,f'Site {i:02}',tags=['Outdoor Travel'],score=i/10,date=f'2024-01-{i%20+1:02}') for i in range(65)]
    extra=discovered(library,'Other source',tags=['Comedy'],plugin='other')
    response=client.get('/api/discover',params={'q':'Site','tag_q':'TRAVEL','sort':'title','direction':'asc','limit':5,'offset':60})
    assert response.status_code==200,response.text
    assert response.json()['total']==65
    assert [work['id'] for work in response.json()['items']]==ids[60:]
    result=client.get('/api/discover',params={'source':'other','sort':'community_rating'}).json()
    assert [work['id'] for work in result['items']]==[extra]
    assert client.get('/api/discover?ids=').json()['total']==0
    assert client.get('/api/discover?sort=invalid').status_code==400
    assert client.get('/api/discover?ids=not-an-id').status_code==400
    assert set(client.get('/api/filters?discover=true').json()['tags'])=={'Outdoor Travel','Comedy'}


def test_source_filter_and_categories_happen_before_date_sort(library):
    a=discovered(library,'A',plugin='one',date='2022-01-01')
    b=discovered(library,'B',plugin='two',date='2024-01-01')
    with library.db:
        library.db.execute('INSERT INTO sources(work_id,plugin,site,source_id,url,updated,site_added) VALUES(?,?,?,?,?,?,?)',
                           (a,'two','two','extra','https://example.org/extra','now','2025-01-01'))
    assert [work['id'] for work in query_discovery(library,{'sort':'site_added'},source='two')]==[a,b]
    assert [work['id'] for work in query_discovery(library,{'sort':'site_added'},category='two:latest')]==[b]
    assert set(discovery_facets(library)['categories'])=={'one:latest','two:latest'}
