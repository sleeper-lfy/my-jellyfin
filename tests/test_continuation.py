from pathlib import Path
import httpx
from lumen.continuation import continue_works
from lumen.server import LanServer
from lumen.ui import MainWindow
from test_core import add_work


def played(library,file_id,stamp,position=120,completed=False):
    with library.db:
        library.db.execute('UPDATE files SET position=?,completed=? WHERE id=?',(position,int(completed),file_id))
        library.db.execute('INSERT INTO sessions(id,file_id,started,ended,watched) VALUES (?,?,?,?,?)',('s-'+str(file_id)+'-'+stamp,file_id,stamp,stamp,120))


def test_continuing_uses_recent_sessions_and_exact_file(library):
    first=add_work(library,'First');second=add_work(library,'Second')
    first_file=library.work(first)['files'][0]['id'];second_file=library.work(second)['files'][0]['id']
    played(library,second_file,'2026-11-01T10:00:00Z')
    played(library,first_file,'2026-11-04T10:00:00Z',300)
    rows=continue_works(library)
    assert [row['id'] for row in rows]==[first,second]
    assert rows[0]['_resume']['file_id']==first_file
    assert rows[0]['_resume']['remaining']==700
    assert '5:00' in rows[0]['_subtitle']
    with library.db:
        new=library.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',(first,'/media/Alternate.mp4','alternate','/media',500)).lastrowid
    played(library,new,'2026-11-04T11:00:00Z',90)
    assert library.resume_file(first)['id']==new
    assert continue_works(library)[0]['_resume']['file_id']==new


def test_finished_episode_keeps_next_episode_but_finished_show_disappears(library):
    identifier=add_work(library,'Show',kind='series');first=library.work(identifier)['files'][0]
    with library.db:
        second=library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',(identifier,'/media/Show.S01E02.mp4','ep2','/media',2000,1,2)).lastrowid
    played(library,first['id'],'2026-11-04T10:00:00Z',1000,True)
    rows=continue_works(library)
    assert len(rows)==1 and rows[0]['_resume']['file_id']==second
    assert rows[0]['_resume']['position']==0 and '下一集 S01E02' in rows[0]['_subtitle']
    played(library,second,'2026-11-04T11:00:00Z',2000,True)
    assert continue_works(library)==[]


def test_default_version_checked_against_work_and_availability(library,tmp_path):
    identifier=add_work(library,'Film');first=library.work(identifier)['files'][0]
    path=tmp_path/'preferred.mp4';path.write_bytes(b'video')
    with library.db:
        second=library.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',(identifier,str(path),'pref',str(tmp_path),1000)).lastrowid
    library.set_setting('preferred-file:'+str(identifier),second)
    assert library.resume_file(identifier)['id']==second
    path.unlink();assert library.resume_file(identifier)['id']==first['id']
    library.set_setting('preferred-file:'+str(identifier),None)
    normal=library.resume_file(identifier)['id']
    library.set_setting('preferred-file:'+str(identifier),999999)
    assert library.resume_file(identifier)['id']==normal


def test_home_shows_next_episode_with_subtitle(qapp,tmp_path):
    window=MainWindow(tmp_path/'home')
    try:
        identifier=add_work(window.library,'Show',kind='series');first=window.library.work(identifier)['files'][0]
        with window.library.db:
            window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',(identifier,'/media/S01E02.mp4','next','/media',200,1,2))
        played(window.library,first['id'],'2026-11-04T10:00:00Z',1000,True)
        window.navigate('home')
        heading,cards=window.home_page.sections['继续观看']
        assert cards.count()==1 and '下一集' in cards.item(0).toolTip()
        window.tabs.setCurrentIndex(1)
        assert window.cards.count()==1
    finally:window.close()


def test_lan_continue_is_authenticated_bounded_and_has_no_private_paths(library):
    identifier=add_work(library,'Film');file=library.work(identifier)['files'][0]
    played(library,file['id'],'2026-11-04T10:00:00Z',123)
    server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',trust_env=False) as client:
            assert client.get('/api/continue').status_code==401
            response=client.get('/api/continue?limit=1',headers={'Authorization':'Bearer '+server.token})
            assert response.status_code==200
            result=response.json();assert len(result['items'])==1 and result['items'][0]['resume']['file_id']==file['id']
            assert '/media/' not in response.text and 'path' not in result['items'][0]['resume']
    finally:server.stop()
