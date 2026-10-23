"""Capture repaired PC import / bookmark controls using only an isolated generated clip."""
from pathlib import Path
import subprocess,tempfile,time
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QLineEdit,QPlainTextEdit
from PySide6.QtGui import QFont
from lumen.core import tool
from lumen.ui import MainWindow
from lumen.theme import STYLE

output=Path('docs/screenshots');output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setFont(QFont('Noto Sans CJK SC',10));app.setStyleSheet(STYLE)
def spin(seconds=.2):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:app.processEvents();time.sleep(.01)
with tempfile.TemporaryDirectory(prefix='lumen-stability-preview-') as directory:
    root=Path(directory);media=root/'示例影片';media.mkdir();video=media/'书签演示.mp4'
    subprocess.run([tool('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-t','8','-c:v','mpeg4',str(video)],check=True)
    video.with_suffix('.nfo').write_text('<movie><title>时间点书签 · 功能演示</title><plot>独立生成的视频，用于查看导入与书签界面。</plot></movie>',encoding='utf-8')
    window=MainWindow(root/'data');window.resize(1280,900)
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler):timer.stop()
    window.library.import_folder(media,'movie');work=window.library.query()[0]
    window.show();window.import_path(media);spin();window.import_form.grab().save(str(output/'fix-import-dialog-pc.png'));window.import_form.reject()
    window.open_details(work['id'],fetch=False);player=window.player;player.open_file(work['files'][0]);spin(.5);player.media.pause();player.timeline.setValue(1000);player.seek();player.auto_hide.setChecked(False)
    player.grab().save(str(output/'fix-player-bookmark-pc.png'))
    form=player.add_bookmark();form.findChild(QLineEdit,'bookmarkName').setText('第一个镜头');form.findChild(QPlainTextEdit,'bookmarkNote').setPlainText('保存的是打开编辑窗口时的时间点。');spin();form.grab().save(str(output/'fix-bookmark-editor-pc.png'))
    form.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    deadline=time.monotonic()+10
    while window.jobs and time.monotonic()<deadline:spin(.05)
    player.close();spin();window.detail_page.refresh_bookmarks();window.grab().save(str(output/'fix-bookmarks-detail-pc.png'));window.close();spin()
