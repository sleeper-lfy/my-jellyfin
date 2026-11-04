import json

from test_server import lan


def test_task_center_is_authenticated_bounded_and_never_returns_private_reports(lan, library):
    client, server, source, _ = lan
    work_id = library.query()[0]['id']
    secret = 'private-access-token-123'
    directory = r'C:\Users\Private\Videos'
    library.task('private-job', 'ingest', 'pending', {
        'work_id': work_id, 'stage': 'identify', 'destination': directory,
        'title': directory, 'password': secret, 'candidates': [{'url': 'https://host/?token='+secret}],
    }, {'raw_data': 'x'*200_000, 'path': directory}, '未找到唯一匹配 '+directory+' '+secret)
    library.task('network-job', 'download-library', 'failed', {'work_id': work_id},
                 error='HTTP 403 https://private.example/?token='+secret)
    library.task('background-job', 'background', 'running', {
        'title': '快速导入 · '+directory,
        'progress': {'completed': 4, 'total': 10, 'stage': directory+' '+secret, 'units_per_second': 1, 'unit': 'items'},
    })
    assert client.get('/api/tasks', headers={'Authorization': ''}).status_code == 401
    response = client.get('/api/tasks?state=pending&limit=1').json()
    assert response['read_only'] is True and response['total'] == 1
    item = response['items'][0]
    assert item['id'] == 'private-job' and item['work_id'] == work_id
    assert item['device'] == 'computer' and item['actions'] == []
    assert item['stage'] == '识别与补充资料' and '匹配需要确认' in item['reason']
    failed = client.get('/api/tasks?state=failed').json()
    assert any('网络请求未完成' in task['reason'] for task in failed['items'])
    running = client.get('/api/tasks?state=active').json()
    task = next(item for item in running['items'] if item['id'] == 'background-job')
    assert task['label'] == '扫描入库' and task['progress'] == {'completed': 4, 'total': 10, 'unit': 'items'}
    serialized = json.dumps([response, failed, running], ensure_ascii=False)
    for private in (secret, directory, str(source.parent), 'raw_data', 'password', 'payload', 'private.example'):
        assert private not in serialized
    # This API is intentionally read-only; no misleading state-only cancellation.
    assert client.post('/api/tasks/private-job/cancel', json={}).status_code == 404
    assert library.db.execute('SELECT status FROM tasks WHERE id=?', ('private-job',)).fetchone()[0] == 'pending'


def test_task_center_groups_pagination_work_scope_and_old_payloads(lan, library):
    from test_core import add_work
    client, _, _, _ = lan
    with library.db: library.db.execute('DELETE FROM tasks')
    first = library.query()[0]['id']
    second = add_work(library, 'Different work')
    for index, state in enumerate(('queued', 'running', 'importing', 'paused', 'pending', 'retry', 'failed', 'partial', 'done', 'cancelled', 'external')):
        library.task('task-'+str(index), 'ingest', state, {'work_id': first if index % 2 == 0 else second})
    assert client.get('/api/tasks?state=active').json()['total'] == 4
    assert client.get('/api/tasks?state=pending').json()['total'] == 2
    assert client.get('/api/tasks?state=failed').json()['total'] == 2
    assert client.get('/api/tasks?state=history').json()['total'] == 3
    result = client.get('/api/tasks?work_id='+str(first)+'&limit=2').json()
    assert result['total'] == 6 and len(result['items']) == 2
    assert all(task['work_id'] == first for task in result['items'])
    next_page = client.get('/api/tasks?work_id='+str(first)+'&limit=2&offset=2').json()
    assert not {task['id'] for task in result['items']} & {task['id'] for task in next_page['items']}
    with library.db:
        library.db.execute("UPDATE tasks SET payload='broken legacy payload' WHERE id='task-0'")
    assert client.get('/api/tasks').status_code == 200
    assert client.get('/api/tasks?work_id='+str(first)).json()['total'] == 5
    assert client.get('/api/tasks?state=invalid').status_code == 400
    assert client.get('/api/tasks?work_id=-1').status_code == 400
    assert client.get('/api/tasks?limit=invalid').status_code == 400
    assert client.get('/api/tasks?limit=10000').json()['limit'] == 100


def test_watchlist_is_available_in_mobile_library_random_queue_and_saved_lists(lan, library):
    from test_core import add_work
    client, _, _, _ = lan
    wanted = library.query()[0]['id']
    add_work(library, 'Not on the watchlist')
    library.update_personal(wanted, watchlist=True)
    assert [work['id'] for work in client.get('/api/works?watchlist=true').json()['items']] == [wanted]
    assert client.post('/api/queue', json={'watchlist': True}).json()['ids'] == [wanted]
    assert client.post('/api/lists', json={'name': 'My watchlist', 'filters': {'watchlist': True}}).status_code == 200
    assert [work['id'] for work in client.get('/api/works?list=My+watchlist').json()['items']] == [wanted]
    assert client.get('/api/works?watchlist=false').json()['total'] == 2
