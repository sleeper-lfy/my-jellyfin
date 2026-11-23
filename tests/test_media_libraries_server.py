import httpx
from lumen import media_libraries as ml
from lumen.server import LanServer


def test_lan_named_libraries_are_authenticated_read_only_and_do_not_expose_paths(library,tmp_path):
    item=ml.save(library,'私人电影','movie',{'roots':[{'path':str(tmp_path/'secret-directory')}],'plugin':'private-provider'})
    server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            assert client.get('/api/media-libraries',headers={'Authorization':''}).status_code==401
            assert client.get('/api/info').json()['media_libraries'] is True
            data=client.get('/api/media-libraries').json();assert data=={'items':[{'id':item['id'],'name':'私人电影','kind':'movie','count':0}]}
            assert str(tmp_path) not in str(data) and 'private-provider' not in str(data)
            assert client.post('/api/media-libraries',json={'name':'新建'}).status_code==403
            assert client.post('/api/media-libraries/'+str(item['id']),json={'name':'修改'}).status_code==403
            assert ml.get(library,item['id'])['name']=='私人电影'
    finally:server.stop()


def test_lan_browse_detail_resume_facets_and_shuffle_keep_the_selected_library(library,tmp_path):
    identifiers=[]
    for label in ['A','B']:
        root=tmp_path/label;root.mkdir();(root/'Shared.2024.mp4').write_bytes(b'same-content')
        item=ml.save(library,label,'movie',{'roots':[{'path':str(root)}]});library.import_folder(root,'movie',fast=True);identifiers.append(item['id'])
    a,b=identifiers;work=library.query()[0];bf=library.work(work['id'],b)['files'][0]
    with library.db:library.db.execute('UPDATE files SET position=22 WHERE id=?',(bf['id'],))
    server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            data=client.get(f'/api/works?media_library_id={a}').json();assert data['total']==1 and data['items'][0]['file_count']==1
            detail=client.get(f"/api/works/{work['id']}?media_library_id={a}").json();assert len(detail['files'])==1 and detail['files'][0]['id']!=bf['id'] and detail['resume_file_id']!=bf['id']
            assert client.get(f'/api/works?media_library_id={a}&watch_state=progress').json()['total']==0
            assert client.get(f'/api/works?media_library_id={b}&watch_state=progress').json()['total']==1
            assert client.get(f'/api/filters?media_library_id={a}').json()['years']==[2024]
            assert client.post('/api/queue/from-browse',json={'browse_path':f'/api/works?media_library_id={a}'}).json()['ids']==[work['id']]
            assert client.post('/api/queue',json={'media_library_id':a}).json()['ids']==[work['id']]
            assert client.post(f"/api/works/{work['id']}/watched?media_library_id={a}",json={'state':'completed'}).status_code==200
            assert library.work(work['id'],a)['files'][0]['completed']==1
            assert library.work(work['id'],b)['files'][0]['position']==22 and not library.work(work['id'],b)['files'][0]['completed']
            for bad in ['0','-1','bad','9999999']:
                assert client.get('/api/works?media_library_id='+bad).status_code==400
                assert client.post('/api/queue',json={'media_library_id':bad}).status_code==400
    finally:server.stop()


def test_builtin_scope_hides_named_files_without_changing_the_all_library_view(library,tmp_path):
    from lumen.media_tools import add_bookmark

    builtin = tmp_path/'builtin'; builtin.mkdir()
    (builtin/'Shared.2024.mp4').write_bytes(b'builtin copy')
    library.import_folder(builtin,'movie',fast=True)
    named = tmp_path/'named'; named.mkdir()
    (named/'Shared.2024.mp4').write_bytes(b'named copy')
    (named/'Private.2025.mp4').write_bytes(b'named exclusive')
    item = ml.save(library,'自定义电影','movie',{'roots':[{'path':str(named)}]})
    library.import_folder(named,'movie',fast=True)
    works = {work['title']: work for work in library.query()}
    shared_id = works['Shared']['id']; private_id = works['Private']['id']
    own_file = library.work(shared_id, ml.BUILTIN_SCOPE)['files'][0]['id']
    named_file = library.work(shared_id, item['id'])['files'][0]['id']
    add_bookmark(library, own_file, 1, '默认书签')
    add_bookmark(library, named_file, 2, '自定义书签')
    with library.db:
        library.db.execute('UPDATE files SET position=30 WHERE id=?', (named_file,))
        library.db.execute('INSERT INTO lists VALUES (?,?)', ('自带电影', '{"media_library_id":"builtin"}'))

    scope = '?media_library_id=builtin'
    server = LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None); server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            assert client.get('/api/info').json()['builtin_library_scope'] is True
            data = client.get('/api/works'+scope+'&kind=movie').json()
            assert data['total'] == 1 and data['items'][0]['id'] == shared_id
            assert data['items'][0]['file_count'] == 1 and data['items'][0]['watch_state'] == 'unwatched'
            assert client.get('/api/works'+scope+'&q=Private').json()['total'] == 0
            assert client.get('/api/filters'+scope+'&kind=movie').json()['years'] == [2024]
            assert client.get('/api/works?list=自带电影').json()['items'][0]['file_count'] == 1
            detail = client.get(f'/api/works/{shared_id}'+scope).json()
            assert [file['id'] for file in detail['files']] == [own_file]
            assert detail['resume_file_id'] == own_file
            assert [bookmark['file_id'] for bookmark in detail['bookmarks']] == [own_file]
            assert client.get(f'/api/works/{private_id}'+scope).status_code == 400
            assert client.post(f'/api/works/{shared_id}/watched'+scope,json={'state':'completed'}).status_code == 200
            assert library.work(shared_id, item['id'])['files'][0]['position'] == 30
            assert client.post('/api/queue/from-browse',json={'browse_path':'/api/works'+scope+'&kind=movie'}).json()['ids'] == [shared_id]
            assert set(client.post('/api/queue/from-browse',json={'browse_path':'/api/works?kind=movie'}).json()['ids']) == {shared_id, private_id}
            assert client.get('/api/works?kind=movie').json()['total'] == 2
    finally:server.stop()
