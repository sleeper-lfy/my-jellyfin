from lumen import tasks
import pytest


def test_task_scopes_filter_before_pagination(library):
    with library.db:
        library.db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',[
            (str(i),'background','done','{}','{}',None,f'2026-11-04 12:{i:03}') for i in range(105)])
        library.db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',[
            ('failure','import','failed','{}','{}','failed','2026-11-01'),
            ('partial','scrape','partial','{}','{}',None,'2026-11-01'),
            ('running','background','running','{}','{}',None,'2026-11-01'),
            ('confirm','ingest','pending','{}','{}',None,'2026-11-01'),
            ('retry','ingest','retry','{}','{}',None,'2026-11-01')])
    assert {row['id'] for row in tasks.snapshot(library.directory,0,'failed')}=={'failure','partial'}
    assert [row['id'] for row in tasks.snapshot(library.directory,0,'active')]==['running']
    assert {row['id'] for row in tasks.snapshot(library.directory,0,'pending')}=={'confirm','retry'}
    assert len(tasks.snapshot(library.directory,100,'history'))==5
    assert {row['id'] for row in tasks.snapshot(library.directory,0,True)}=={'confirm','retry'}
    assert len(tasks.snapshot(library.directory))==100


def test_unknown_task_scope_does_not_silently_select_everything(library):
    with pytest.raises(ValueError,match='未知任务筛选'):
        tasks.snapshot(library.directory,0,'not-a-scope')
