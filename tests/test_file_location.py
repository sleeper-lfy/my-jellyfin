from pathlib import Path
import pytest
from lumen import file_location


def test_windows_selection_uses_arguments_and_preserves_special_filename(tmp_path,monkeypatch):
    video=tmp_path/'a & b [test] movie.mp4';video.touch();seen=[]
    monkeypatch.setattr(file_location.sys,'platform','win32')
    monkeypatch.setattr(file_location.QProcess,'startDetached',lambda command,args:(seen.append((command,args)) or (True,42)))
    assert file_location.reveal_video(video)==video.resolve()
    assert seen==[('explorer.exe',['/select,',str(video.resolve())])]


def test_offline_file_never_opens_an_unrelated_folder(tmp_path,monkeypatch):
    monkeypatch.setattr(file_location.QDesktopServices,'openUrl',lambda *args:pytest.fail('offline file must not open'))
    with pytest.raises(FileNotFoundError):file_location.reveal_video(tmp_path/'offline.mp4')


def test_native_manager_failure_is_reported(tmp_path,monkeypatch):
    video=tmp_path/'file.mp4';video.touch();monkeypatch.setattr(file_location.sys,'platform','darwin')
    monkeypatch.setattr(file_location.QProcess,'startDetached',lambda *args:(False,0))
    with pytest.raises(OSError,match='文件管理器'):file_location.reveal_video(video)


def test_linux_opens_the_containing_folder(tmp_path,monkeypatch):
    video=tmp_path/'file.mp4';video.touch();seen=[];monkeypatch.setattr(file_location.sys,'platform','linux')
    monkeypatch.setattr(file_location.QDesktopServices,'openUrl',lambda url:(seen.append(url.toLocalFile()) or True))
    file_location.reveal_video(video);assert len(seen)==1 and Path(seen[0])==tmp_path


def test_multi_file_selection_can_cancel_and_targets_the_selected_file(qapp,tmp_path,monkeypatch):
    from lumen.ui import MainWindow,QInputDialog
    from test_core import add_work
    window=MainWindow(tmp_path/'locations');identifier=add_work(window.library,'Multiple')
    with window.library.db:
        window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES(?,?,?,?,?)',(identifier,str(tmp_path/'second video.mp4'),'second',str(tmp_path),100))
    opened=[];monkeypatch.setattr(window,'reveal_file_path',lambda path:opened.append(path))
    try:
        monkeypatch.setattr(QInputDialog,'getItem',lambda *args:('',False))
        window.reveal_work_file(identifier);assert not opened
        target=window.library.work(identifier)['files'][-1]['path']
        monkeypatch.setattr(QInputDialog,'getItem',lambda *args:(target,True))
        window.reveal_work_file(identifier);assert opened==[target]
    finally:window.close()
