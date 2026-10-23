import json
import threading
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QTableWidget,QPlainTextEdit,QPushButton
from lumen import tasks
from lumen.core import ImportCancelled
from lumen.ui import MainWindow


def spin(app,seconds=.05):
    loop=QEventLoop();QTimer.singleShot(round(seconds*1000),loop.quit);loop.exec();app.processEvents()


def until(app,predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:spin(app,.02)
    assert predicate()


def test_large_reports_are_bounded_in_summary_and_preview_but_export_is_complete(library,tmp_path):
    result={'errors':[{'path':'D:/a/long/media/file/'+str(i),'reason':'Failure'} for i in range(15000)]}
    library.task('large','import','partial',{'root':'D:/a','kind':'series'},result)
    summary=tasks.snapshot(library.directory)[0];assert len(summary['result'])<=240
    preview=tasks.record(library.directory,'large',preview=True);assert preview['truncated'] and len(preview['text'])<=220000
    destination=tmp_path/'report.json';tasks.export(library.directory,'large',destination)
    assert json.loads(destination.read_text())['result']==result
    original=destination.read_bytes()
    with pytest.raises(ImportCancelled):tasks.export(library.directory,'large',destination,lambda:True)
    assert destination.read_bytes()==original and not destination.with_suffix('.json.part').exists()
    assert len(tasks.record(library.directory,'large',retry=True)['candidates'])==15000


def test_opening_task_browser_never_waits_for_loader_or_resizes_to_large_reports(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'tasks-ui');window.show()
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    entered=threading.Event();release=threading.Event();read=tasks.snapshot
    window.library.task('large','import','running',{'root':'D:/a','progress':{'completed':1,'total':10,'stage':'Import'}},{'errors':['long error '*10000]})
    def slow(directory,offset=0):
        assert threading.current_thread() is not threading.main_thread()
        entered.set();release.wait(4);return read(directory,offset)
    monkeypatch.setattr(tasks,'snapshot',slow)
    try:
        ticks=[];timer=QTimer(window);timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
        window.show_tasks();dialog=window.tasks_dialog;table=dialog.findChild(QTableWidget)
        until(qapp,entered.is_set);spin(qapp,.1)
        assert len(ticks)>=3 and table.rowCount()==0 and dialog.isVisible()
        release.set();until(qapp,lambda:table.rowCount()==1)
        assert not table.wordWrap() and len(table.item(0,3).text())<=2000
        window.show_tasks();assert window.tasks_dialog is dialog
        table.selectRow(0)
        next(button for button in dialog.findChildren(QPushButton) if button.text()=='查看完整进度 / 结果 / 错误').click()
        until(qapp,lambda:any(editor.toPlainText()!='正在后台读取任务详情…' for editor in dialog.findChildren(QPlainTextEdit)))
        assert not any(editor.lineWrapMode()!=QPlainTextEdit.LineWrapMode.NoWrap for editor in dialog.findChildren(QPlainTextEdit))
        dialog.close()
    finally:
        release.set();window.close();until(qapp,lambda:not window._auxiliary_jobs and not window.jobs and not window.isVisible())


def test_task_history_is_browsable_in_bounded_pages(library):
    with library.db:
        library.db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',[(str(i),'background','done','{}','{}',None,f'2026-10-24 {i:04}') for i in range(105)])
    first=tasks.snapshot(library.directory);second=tasks.snapshot(library.directory,100)
    assert len(first)==100 and len(second)==5 and not {row['id'] for row in first}&{row['id'] for row in second}
