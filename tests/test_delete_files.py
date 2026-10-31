import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from lumen.files import plan_delete, execute_delete
from lumen.ui import MainWindow
from test_core import add_work


def imported_work(library, tmp_path, name='Solo.2024'):
    folder = tmp_path / 'media'; folder.mkdir(exist_ok=True)
    video = folder / (name + '.mp4'); video.write_bytes(('video-' + name).encode())
    video.with_suffix('.nfo').write_text('<movie><title>Solo</title></movie>', encoding='utf-8')
    video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nhi\n', encoding='utf-8')
    library.import_folder(folder, 'movie', fast=True)
    return library.query({'kinds': ['movie']})[0], video


def test_execute_delete_removes_videos_sidecars_and_entry(library, tmp_path):
    work, video = imported_work(library, tmp_path)
    plan = plan_delete(library, work['id'])
    assert plan['paths'] == [str(video)] and plan['known_size']
    result = execute_delete(library, work['id'])
    assert result == {'deleted': 3}
    assert not video.exists() and not video.with_suffix('.nfo').exists() and not video.with_suffix('.srt').exists()
    assert library.query({'kinds': ['movie']}) == []
    assert not library.db.execute('SELECT 1 FROM files WHERE work_id=?', (work['id'],)).fetchone()


def test_execute_delete_aborts_when_video_missing(library, tmp_path):
    work, video = imported_work(library, tmp_path)
    video.unlink()
    try:
        execute_delete(library, work['id'])
        raise AssertionError('expected ValueError')
    except ValueError as error:
        assert '不存在或所在磁盘离线' in str(error)
    assert library.work(work['id'])['title'] == 'Solo'
    assert video.with_suffix('.nfo').exists() and video.with_suffix('.srt').exists()


def test_execute_delete_aborts_while_playback_session_open(library, tmp_path):
    work, video = imported_work(library, tmp_path)
    file_id = library.work(work['id'])['files'][0]['id']
    with library.db:
        library.db.execute('INSERT INTO sessions(id,file_id,started) VALUES (?,?,?)', (uuid.uuid4().hex, file_id, datetime.now(timezone.utc).isoformat()))
    try:
        execute_delete(library, work['id'])
        raise AssertionError('expected ValueError')
    except ValueError as error:
        assert '请先停止' in str(error)
    assert video.exists() and library.work(work['id'])['files']


class FakeBox:
    StandardButton = __import__('PySide6.QtWidgets', fromlist=['QMessageBox']).QMessageBox.StandardButton
    answer = None

    def __init__(self, *args, **kwargs):
        FakeBox.shown = self
    def setWindowTitle(self, *args): pass
    def setText(self, *args): pass
    def setDetailedText(self, *args): pass
    def setStandardButtons(self, *args): pass
    def button(self, button):
        return SimpleNamespace(setText=lambda *args: None)
    def exec(self):
        return FakeBox.answer


def test_delete_work_files_confirms_then_deletes_in_background(qapp, tmp_path, monkeypatch):
    from unittest.mock import Mock
    window = MainWindow(tmp_path/'delete-ui')
    work, video = imported_work(window.library, tmp_path)
    monkeypatch.setattr('lumen.ui.QMessageBox', FakeBox)

    class FakeProgress:
        def __call__(self, *args): pass
        def cancelled(self): return False
    progress = FakeProgress()

    def fake_run(title, function, callback=None):
        result = function(window.library, progress)
        if callback: callback(result)
    try:
        FakeBox.answer = FakeBox.StandardButton.Cancel
        window.delete_work_files(work['id'])
        assert video.exists() and window.library.work(work['id'])

        FakeBox.answer = FakeBox.StandardButton.Ok
        window.run_job = Mock(side_effect=fake_run)
        window.delete_work_files(work['id'])
        assert not video.exists() and not video.with_suffix('.srt').exists()
        assert window.library.query({'kinds': ['movie']}) == []
        assert '已删除 3 个文件' in window.status.text()
    finally:
        window.close()


class FakeAction:
    def __init__(self):
        self.triggered = SimpleNamespace(connect=lambda *args: None)
    def setCheckable(self, *args): return self
    def setChecked(self, *args): return self


from PySide6.QtWidgets import QMenu


class FakeMenu(QMenu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        FakeMenu.labels = []
    def addAction(self, *args):
        FakeMenu.labels.append(next((a for a in args if isinstance(a, str)), None))
        try:
            return super().addAction(*args)
        except TypeError:
            return FakeAction()
    def addSeparator(self):
        return super().addSeparator()
    def exec(self, position):
        return None


def test_right_click_menus_offer_delete_for_local_works(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path/'delete-menu')
    work, video = imported_work(window.library, tmp_path)
    offline = add_work(window.library, 'Discovered', local=False)
    monkeypatch.setattr('lumen.ui.QMenu', FakeMenu)
    try:
        window.navigate('movie')
        item = window.cards.item(0)
        window.card_menu(window.cards.visualItemRect(item).center())
        assert '删除本地文件…' in FakeMenu.labels and '仅移出媒体库…' in FakeMenu.labels

        window.open_details(work['id'], fetch=False)
        actions = [action.text() for action in window.detail_page.management_menu.actions()]
        assert '删除本地文件…' in actions

        window.open_details(offline, fetch=False)
        actions = [action.text() for action in window.detail_page.management_menu.actions()]
        assert '删除本地文件…' not in actions and '仅移出媒体库…' in actions
    finally:
        window.close()
