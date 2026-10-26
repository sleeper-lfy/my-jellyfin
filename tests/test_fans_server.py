from test_core import add_work
from test_server import lan


def test_fans_queries_and_authenticated_folder_merge_preserve_file_history(lan,library):
    client,_,_,_=lan
    first=add_work(library,'Creator one','fans',metadata={'creator':'Creator one','fans_roots':['/media/creator-one']})
    second=add_work(library,'Creator alternate folder','fans',metadata={'creator':'Creator alternate folder','fans_roots':['/media/creator-alternate']})
    source_file=library.work(second)['files'][0]['id']
    with library.db:
        library.db.execute('UPDATE files SET season=NULL,episode=NULL WHERE work_id IN (?,?)',(first,second))
        library.db.execute('UPDATE files SET position=42 WHERE id=?',(source_file,))
        library.db.execute("INSERT INTO sessions VALUES('fans-history',?,'now','now',11)",(source_file,))
        library.db.execute("INSERT INTO bookmarks VALUES('fans-mark',?,22,'point','','','now')",(source_file,))
    result=client.get('/api/works?kind=fans&sort=title&direction=asc').json()
    assert result['total']==2 and all(work['kind']=='fans' for work in result['items'])
    assert client.get(f'/api/works/{first}').json()['creator']=='Creator one'
    body={'ids':[first,second],'target_id':first,'creator':'One author'}
    assert client.post('/api/fans/merge',json=body,headers={'Authorization':''}).status_code==401
    response=client.post('/api/fans/merge',json=body)
    assert response.status_code==200,response.text
    assert response.json()['work']['kind']=='fans' and response.json()['work']['creator']=='One author'
    assert response.json()['work']['file_count']==2
    file=next(file for file in library.work(first)['files'] if file['id']==source_file)
    assert file['position']==42 and file['season'] is None and file['episode'] is None
    assert library.db.execute("SELECT file_id FROM bookmarks WHERE id='fans-mark'").fetchone()[0]==source_file
    assert library.db.execute("SELECT watched FROM sessions WHERE id='fans-history'").fetchone()[0]==11
    assert client.get('/api/works?kind=fans').json()['total']==1
    regular=library.query({'kinds':['movie']})[0]['id']
    assert client.post('/api/fans/merge',json={'ids':[first,regular],'target_id':first}).status_code==400
    assert len(library.work(first)['files'])==2
