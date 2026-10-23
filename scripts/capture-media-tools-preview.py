"""Capture actual PC tools with an isolated generated test clip, never user media."""
from pathlib import Path
import argparse
import subprocess
import tempfile
import time
from PySide6.QtWidgets import QApplication,QDialog,QTabWidget
from PySide6.QtGui import QFont
from lumen.core import tool
from lumen.ui import MainWindow
from lumen.theme import STYLE
from lumen.media_tools import add_bookmark,capture_bookmark,preferences,audit_library
from lumen.library_tools_ui import LibraryTools

parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/screenshots');args=parser.parse_args()
output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setFont(QFont('Noto Sans CJK SC',10));app.setStyleSheet(STYLE)
def settle(seconds=.25):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.01)
with tempfile.TemporaryDirectory(prefix='lumen-tools-preview-') as directory:
    root=Path(directory);media=root/'示例媒体';media.mkdir();video=media/'功能演示.2024.mp4'
    subprocess.run([tool('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-f','lavfi','-i','sine=frequency=440','-t','8','-c:v','mpeg4','-c:a','aac',str(video)],check=True)
    nfo=video.with_suffix('.nfo');nfo.write_text('<movie><title>功能演示 · 示例视频</title><year>2024</year><plot>独立测试库中的生成视频，用于验证书签、字幕和诊断界面。</plot><genre>功能预览</genre></movie>',encoding='utf-8')
    window=MainWindow(root/'data');window.resize(1280,900);window.library.import_folder(media,'movie');work=window.library.query()[0];file=work['files'][0]
    for seconds,title,note in [(1,'第一个镜头','点击书签可从此处继续播放'),(4,'画面变化','截图与原视频时间点对应')]:
        mark=add_bookmark(window.library,file['id'],seconds,title,note);capture_bookmark(window.library,mark['id'])
    preferences(window.library,file['id'],{'subtitle_delay':.3,'subtitle_size':28,'subtitle_position':85})
    window.library.set_setting('watched_folders',[{'path':str(media),'kind':'movie','enabled':True,'settle_seconds':15}])
    window.show();window.navigate('movie');window.open_details(work['id'],fetch=False);settle();window.grab().save(str(output/'tools-bookmarks-pc.png'))
    # A damaged demonstration sidecar produces a real read-only audit finding.
    nfo.write_text('<movie>incomplete',encoding='utf-8');audit_library(window.library)
    tools=LibraryTools(window);tools.show();settle();tools.grab().save(str(output/'tools-monitor-pc.png'))
    tools.findChild(QTabWidget).setCurrentIndex(1);settle();tools.grab().save(str(output/'tools-health-pc.png'));tools.close()
    window.player.open_file(file);settle(.6);window.player.media.pause();window.player.show_settings();settle();window.player.track_dialog.grab().save(str(output/'tools-subtitles-pc.png'));window.player.track_dialog.close()
    window.player.show_diagnostics();settle()
    diagnostics=next(dialog for dialog in window.player.findChildren(QDialog) if dialog.windowTitle()=='播放诊断');diagnostics.grab().save(str(output/'tools-diagnostics-pc.png'));diagnostics.close();window.player.close();window.close();settle()
