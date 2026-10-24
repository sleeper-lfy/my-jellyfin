"""Capture the actual Qt player with generated media and a temporary library."""
from pathlib import Path
import subprocess,tempfile,time
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from lumen.core import Library
from lumen.player import Player
from lumen.theme import STYLE

app=QApplication([]);app.setStyleSheet(STYLE);app.setFont(QFont('Noto Sans CJK SC',10))
def settle(seconds=.3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.01)
with tempfile.TemporaryDirectory(prefix='lumen-player-preview-') as root:
    root=Path(root);source=root/'山海纪行 · 独立示例.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x173545:s=1280x720:r=24','-t','8','-c:v','mpeg4','-y',str(source)],check=True)
    lib=Library(root/'data');lib.import_folder(root,'movie');work=lib.query()[0];lib.update_personal(work['id'],rating=9,favorite=True,liked=True)
    player=Player(lib);player.resize(1280,720);player.open_file(work['files'][0]);settle(.6);player.media.pause();player.show_controls();settle()
    output=Path('docs/screenshots');output.mkdir(exist_ok=True);player.grab().save(str(output/'player-personal-pc.png'))
    player.resize(640,360);player.show_controls();settle();player.grab().save(str(output/'player-personal-pc-compact.png'));player.close();lib.close()
