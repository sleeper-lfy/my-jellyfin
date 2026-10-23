import json
import httpx
import pytest
from lumen.server import LanServer, parse_range, ApiError


@pytest.fixture
def lan(library, video_factory):
    source = video_factory('LAN.2024.mp4')
    source.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nLAN subtitle\n', encoding='utf-8')
    library.import_folder(source.parent, 'movie')
    clock = [100.0]
    server = LanServer(library.directory, host='127.0.0.1', port=0, clock=lambda: clock[0], discovery_port=0)
    server.start()
    with httpx.Client(base_url=f'http://127.0.0.1:{server.port}', headers={'Authorization': 'Bearer '+server.token}, trust_env=False) as client:
        yield client, server, source, clock
    server.stop()


def test_auth_library_and_personal(lan, library):
    client, server, source, _ = lan
    assert client.get('/api/info', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/info?token='+server.token, headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/info').json()['api_version'] == 1
    data = client.get('/api/works?kind=movie&limit=1').json()
    assert data['total'] == 1
    item = data['items'][0]
    detail = client.get('/api/works/'+str(item['id'])).json()
    assert str(source.parent) not in json.dumps(detail)
    assert detail['resume_file_id'] == detail['files'][0]['id']
    assert client.get(item['cover']).content.startswith(b'\xff\xd8')
    endpoint = f"/api/works/{item['id']}/personal"
    assert client.post(endpoint, json={'favorite': True, 'rating': 9}).status_code == 200
    assert library.work(item['id'])['rating'] == 9
    assert client.get('/api/works?favorite=true').json()['total'] == 1
    assert client.get('/api/works?q=nomatch').json()['total'] == 0
    assert client.post(endpoint, json={'rating': 11}).status_code == 400
    assert client.post(endpoint, json={'favorite': 'true'}).status_code == 400
    assert client.post('/api/queue', json={'favorite': True}).json()['ids'] == [item['id']]


def test_video_ranges_and_subtitles(lan):
    client, _, source, _ = lan
    work = client.get('/api/works').json()['items'][0]
    file = client.get(f"/api/works/{work['id']}").json()['files'][0]
    route = file['stream']; content = source.read_bytes()
    assert client.get(route).content == content
    for spec, expected in [('bytes=0-31', content[:32]), ('bytes=-20', content[-20:]), ('bytes=20-', content[20:])]:
        response = client.get(route, headers={'Range': spec})
        assert response.status_code == 206
        assert response.content == expected
    response = client.head(route, headers={'Range': 'bytes=10-19'})
    assert response.status_code == 206 and response.content == b''
    assert response.headers['content-length'] == '10'
    response = client.get(route, headers={'Range': 'bytes=99999999-'})
    assert response.status_code == 416
    assert response.headers['content-range'] == f'bytes */{len(content)}'
    captions = client.get(f"/api/files/{file['id']}/subtitles").json()['items']
    assert 'LAN subtitle' in client.get(captions[0]['url']).text
    assert client.get('/api/files/999999/stream').status_code == 404


def test_watch_time_ignores_pause_seek_and_duplicate(lan, library):
    client, _, _, clock = lan
    file = library.db.execute('SELECT id FROM files').fetchone()[0]
    library.db.execute('UPDATE files SET duration=1000 WHERE id=?', (file,)); library.db.commit()
    session = client.post('/api/playback/start', json={'file_id': file}).json()['session_id']
    route = '/api/playback/'+session
    def tick(seq, position, **kwargs):
        return client.post(route+'/tick', json={'seq': seq, 'position': position, 'playing': True, **kwargs})
    assert tick(0, 0).status_code == 200
    clock[0] += 1; tick(1, 1)
    clock[0] += 1; tick(2, 2)
    assert tick(2, 2).json()['duplicate']
    clock[0] += 1; tick(3, 100, seeking=True)
    clock[0] += 1; tick(4, 100, playing=False)
    clock[0] += 20; tick(5, 100, playing=False)
    clock[0] += 1; tick(6, 100)
    clock[0] += 1; tick(7, 101)
    assert library.db.execute('SELECT watched FROM sessions WHERE id=?', (session,)).fetchone()[0] == 3
    assert tick(8, -1).status_code == 400
    assert client.post(route+'/stop', json={'seq': 8, 'position': 101, 'playing': False}).status_code == 200
    assert library.db.execute('SELECT ended FROM sessions WHERE id=?', (session,)).fetchone()[0]
    assert library.db.execute('SELECT position FROM files WHERE id=?', (file,)).fetchone()[0] == 101


@pytest.mark.parametrize('value', ['bytes=-0', 'bytes=4-2', 'bytes=0-1,3-4', 'abc', 'bytes=-'])
def test_invalid_ranges(value):
    with pytest.raises(ApiError): parse_range(value, 20)


def test_http_video_decodes_and_outside_root_is_denied(lan, library):
    import subprocess
    client, server, _, _ = lan
    row = library.db.execute('SELECT id FROM files').fetchone()
    route = f'/api/files/{row[0]}/stream'
    result = subprocess.run(['ffmpeg', '-v', 'error', '-headers', 'Authorization: Bearer '+server.token+'\r\n',
                             '-i', str(client.base_url).rstrip('/')+route, '-frames:v', '1', '-f', 'null', '-'],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode()
    library.db.execute("UPDATE files SET root='/nonexistent-media-root' WHERE id=?", (row[0],)); library.db.commit()
    assert client.get(route).status_code == 403


def test_valid_watch_threshold_and_full_queue(lan, library):
    from test_core import add_work
    client, server, _, clock = lan
    for i in range(45): add_work(library, f'Queue {i}')
    add_work(library, 'Metadata only', local=False)
    # Only local playable works belong to query/queue; adding metadata must not create broken playback entries.
    ids = client.post('/api/queue', json={}).json()['ids']
    assert len(ids) == 46
    assert set(ids) == {w['id'] for w in library.query({})}
    file = library.db.execute('SELECT id FROM files').fetchone()[0]
    library.db.execute('UPDATE files SET duration=1000 WHERE id=?', (file,)); library.db.commit()
    key = client.post('/api/playback/start', json={'file_id': file}).json()['session_id']
    # Exercise the same persistence and monotonic timing path without 600 HTTP roundtrips.
    server.tick(library, key, {'seq': 0, 'position': 0, 'playing': True})
    for second in range(1, 602):
        clock[0] += 1
        server.tick(library, key, {'seq': second, 'position': second, 'playing': True})
        if second == 600: assert library.stats()['valid'] == 0
    assert client.get('/api/stats').json()['valid'] == 1


def test_discovery_has_no_secrets_and_stops_with_server(lan):
    import socket
    import secrets
    client,server,_,_ = lan
    nonce = secrets.token_hex(16)
    discovery = server.discovery
    assert discovery is not None
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(.6)
        sock.sendto(b'LUMEN_DISCOVER_V1 '+nonce.encode(),('127.0.0.1',discovery.port))
        data,_ = sock.recvfrom(1024)
        result = json.loads(data)
        assert result['nonce'] == nonce and result['port'] == server.port
        assert result['service'] == 'lumen'
        assert server.token.encode() not in data and b'path' not in data
        sock.sendto(b'LUMEN_DISCOVER_V1 bad',('127.0.0.1',discovery.port))
        with pytest.raises(socket.timeout): sock.recvfrom(1024)
    assert client.get('/api/filters',headers={'Authorization':''}).status_code == 401
    server.stop()
    assert not discovery.thread.is_alive() and server.discovery is None


def test_lan_facets_and_combined_filters_apply_before_pagination_and_queue(lan,library):
    from test_core import add_work
    client,_,_,_ = lan
    for i in range(35): add_work(library,f'Filters {i}',year=2020+i%2,metadata={'tags':['Target' if i%2 else 'Other'],'actors':[{'name':'Actress','aliases':['Alias']}]})
    add_work(library,'Nonlocal',local=False,metadata={'tags':['Hidden']})
    options=client.get('/api/filters?kind=movie').json()
    assert 'Target' in options['tags'] and 'Hidden' not in options['tags']
    assert 'Alias' in options['actors']
    path='/api/works?tag=Target&actor=Alias&year=2021&limit=1'
    result=client.get(path).json()
    assert result['total']==17 and len(result['items'])==1
    assert client.get('/api/works?tag=Target&year=2020').json()['total']==0
    assert client.get('/api/works?year=oops').status_code==400
    assert client.get('/api/works?year=9999').status_code==400
    ids=client.post('/api/queue',json={'tag':'Target','actor':'Alias','year':'2021'}).json()['ids']
    assert len(ids)==17
    recommended=client.get('/api/recommendations?tag=Target&year=2021').json()['items']
    assert {item['id'] for item in recommended}==set(ids)
