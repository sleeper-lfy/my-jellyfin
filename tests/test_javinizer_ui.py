from pathlib import Path
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox, QTabWidget

from lumen import javinizer as engine
from lumen.import_ui import ImportDialog
from lumen.javinizer_ui import JavinizerPanel
from lumen.matching import CandidatePicker
from lumen.settings import Settings
from lumen.ui import MainWindow
from test_core import add_work
from test_javinizer import raw


def wait(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate()


def test_settings_save_order_and_sources_appear_only_for_supported_media(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path / 'settings')
    executable = tmp_path / 'component.exe'; executable.write_bytes(b'component')
    monkeypatch.setattr(engine, 'executable_path', lambda library: executable)
    try:
        dialog = Settings(window)
        panel = dialog.findChild(JavinizerPanel)
        assert panel and not panel.enabled.isChecked()
        panel.sources.setCurrentRow(1); panel.move_source(-1)
        panel.enabled.setChecked(True)
        panel.proxy.setText('http://127.0.0.1:7890')
        assert panel.save(inform=False)
        saved = engine.settings(window.library)
        assert saved['sources'] == ['libredmm', 'r18dev', 'javbus']
        assert saved['proxy'] == 'http://127.0.0.1:7890'
        from lumen.media_management_ui import CategoryRules
        rules = CategoryRules(window)
        rules.kind.setCurrentIndex(rules.kind.findData('movie')); rules.reload()
        assert rules.primary.findData(engine.ENGINE_ID) >= 0
        rules.kind.setCurrentIndex(rules.kind.findData('series')); rules.reload()
        assert rules.primary.findData(engine.ENGINE_ID) == -1
        rules.deleteLater()
        assert not dialog.plugins  # Native code is never presented as an installable JS script.
        importing = ImportDialog(window)
        importing.kind.setCurrentIndex(importing.kind.findData('movie')); importing.sync_kind()
        assert importing.scraper.findData(engine.ENGINE_ID) > 0
        importing.kind.setCurrentIndex(importing.kind.findData('series'))
        assert importing.scraper.findData(engine.ENGINE_ID) == -1
        importing.kind.setCurrentIndex(importing.kind.findData('vr'))
        assert importing.scraper.findData(engine.ENGINE_ID) > 0
        importing.close(); dialog.close()
    finally:
        window.close()


def test_manual_match_prefills_file_code_and_saves_without_querying_again(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path / 'matching')
    engine.save_settings(window.library, {'enabled': True})
    work_id = add_work(window.library, 'Readable NFO title', kind='vr')
    with window.library.db:
        window.library.db.execute('UPDATE files SET path=? WHERE work_id=?',
                                 (str(tmp_path / 'IPX-535-C.mp4'), work_id))
    monkeypatch.setattr(engine, 'verified_executable', lambda *_: tmp_path / 'engine.exe')
    calls = []
    def query(lib, executable, source, code, config, cancelled):
        calls.append((source, code))
        return engine.metadata(raw(poster_url='', actresses=[], screenshot_urls=[]), source, code)
    monkeypatch.setattr(engine, 'query_source', query)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (args[3][0], True))
    prompts = []
    def text(*args, **kwargs):
        prompts.append((args[2], kwargs['text']))
        return kwargs['text'], True
    monkeypatch.setattr(QInputDialog, 'getText', text)
    def pick(dialog):
        assert len(dialog.records) == 1
        dialog.items.setCurrentRow(0)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(CandidatePicker, 'exec', pick)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args))
    try:
        window.open_details(work_id, fetch=False)
        window.detail_page.scrape()
        wait(qapp, lambda: not window.jobs and not window.job_queue)
        assert calls == [('r18dev', 'IPX-535')]
        assert '番号' in prompts[0][0] and prompts[0][1] == 'IPX-535'
        assert not errors
        work = window.library.work(work_id)
        assert work['title'] == 'Source title' and work['kind'] == 'vr'
        assert work['sources'][0]['plugin'] == engine.ENGINE_ID
    finally:
        window.close()
