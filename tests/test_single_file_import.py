import json
from pathlib import Path
import pytest
from PySide6.QtGui import QDropEvent
from lumen.ui import MainWindow
from test_drag_drop import drag_event


@pytest.mark.parametrize('kind',['movie','series','vr','other','fans'])
def test_single_file_import_never_scans_siblings(library,tmp_path,kind):
    folder=tmp_path/'Author';folder.mkdir()
    selected=folder/'Selected.S01E01.MP4';selected.write_bytes(b'selected video')
    sibling=folder/'Unselected.S01E02.mp4';sibling.write_bytes(b'other video')
    selected.with_suffix('.nfo').write_text('<movie><title>Selected title</title></movie>')
    result=library.import_folder(selected,kind,fast=True,include_work_ids=True)
    assert result['imported']==1 and not result['errors']
    rows=list(library.db.execute('SELECT path FROM files'))
    assert [Path(row[0]) for row in rows]==[selected]
    assert selected.is_file() and sibling.is_file()
    payload=json.loads(library.db.execute("SELECT payload FROM tasks WHERE kind='import' ORDER BY rowid DESC LIMIT 1").fetchone()[0])
    assert [Path(path) for path in payload['candidates']]==[selected.resolve()]
    assert library.import_folder(selected,kind,fast=True)['duplicates']==1
    assert library.db.execute('SELECT count(*) FROM files').fetchone()[0]==1


def test_drop_mixed_files_and_folders_keeps_each_selected_path(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    folder=tmp_path/'folder';folder.mkdir()
    video=tmp_path/'single.mp4';video.write_bytes(b'video')
    try:
        window.dropEvent(drag_event([str(video),str(folder),str(video)],QDropEvent))
        assert window.import_form.path.text()==str(video)
        assert window.import_form.pending==[str(folder)]
        other=tmp_path/'other.mkv';other.write_bytes(b'video')
        window.dropEvent(drag_event([str(other)],QDropEvent))
        assert window.import_form.pending==[str(folder),str(other)]
    finally:window.close()


def test_non_video_file_is_rejected(library,tmp_path):
    text=tmp_path/'note.txt';text.write_text('not video')
    with pytest.raises(ValueError,match='视频文件'):library.import_folder(text,'movie',fast=True)
    assert not library.query()
