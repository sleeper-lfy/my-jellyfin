"""Actual native GPU composition check. Requires a display (Xvfb also works), not offscreen Qt."""
import argparse
import sys
from pathlib import Path
import subprocess
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer, Qt
from lumen.core import tool
from lumen.ui import MainWindow

parser=argparse.ArgumentParser();parser.add_argument('--screenshot');args=parser.parse_args()
app=QApplication([])
def spin(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec();app.processEvents()
with tempfile.TemporaryDirectory(prefix='lumen-mpv-gl-') as directory:
    root=Path(directory);media=root/'media';media.mkdir()
    source=media/'Render.mp4'
    subprocess.run([tool('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24,drawbox=x=0:y=0:w=iw:h=ih/3:color=red:t=fill,drawbox=x=0:y=ih*2/3:w=iw:h=ih/3:color=blue:t=fill','-t','10','-c:v','mpeg4',str(source)],check=True)
    window=MainWindow(root/'data');window.library.import_folder(media,'movie',fast=True)
    window.show();player=window.player
    assert player.mpv_backend, player.backend_message
    errors=[];player.media.errorOccurred.connect(lambda _code,message:errors.append(message))
    player.open_file(window.library.query()[0]['files'][0]);spin(1200)
    assert player.media.position()>0 and not errors, errors
    player.enhance.setChecked(True);spin(250)
    player.subtitle_delay.setValue(.3);player.subtitle_size.setValue(26);player.subtitle_position.setValue(85)
    assert player.diagnostics()['backend']=='libmpv'
    windowed_geometry=player.geometry();windowed_flags=player.windowFlags();engine=player.media.engine
    native_handles=(int(player.winId()),int(player.canvas.winId()));position=player.media.position()
    player.toggle_fullscreen();spin(250);player.show_controls();spin(100)
    assert player.isFullScreen() and player.windowFlags()==windowed_flags
    assert player.media.engine is engine and native_handles==(int(player.winId()),int(player.canvas.winId())), 'Fullscreen recreated native video / decoder'
    assert player.media.position()>=position, 'Fullscreen reset playback position'
    assert not player.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert player.overlay.geometry()==player.rect()
    assert abs(player.media.engine.sub_delay-.3)<.01 and player.media.engine.sub_font_size==26
    if sys.platform=='win32':
        # This is the entire monitor, including the strip normally occupied by
        # Explorer's taskbar. availableGeometry() would only test fake fullscreen.
        assert player.frameGeometry()==player.screen().geometry(), (player.frameGeometry(),player.screen().geometry())
    assert player.pause.isVisible() and player.fullscreen_control.isVisible()
    # The native render host and masked Qt controls must both be visible.
    image=player.screen().grabWindow(player.winId()).toImage()
    colored=sum(1 for x in range(image.width()//4,image.width()*3//4,25)
                for y in range(image.height()//3,image.height()*2//3,25)
                if max(image.pixelColor(x,y).getRgb()[:3])-min(image.pixelColor(x,y).getRgb()[:3])>40)
    print('composition:',colored,image.size().toTuple(),player.size().toTuple(),player.media.position(),flush=True)
    if args.screenshot:image.save(args.screenshot)
    assert colored>20, 'Video hidden behind overlay / black composition'
    top=image.pixelColor(image.width()//2,image.height()//3)
    bottom=image.pixelColor(image.width()//2,image.height()*2//3)
    assert top.red()>150 and top.blue()<80 and bottom.blue()>150 and bottom.red()<80, 'Video orientation is incorrect'
    player.toggle_fullscreen();spin(200)
    assert player.media.engine is engine and native_handles==(int(player.winId()),int(player.canvas.winId()))
    assert not player.isFullScreen() and player.windowFlags()==windowed_flags
    assert player.geometry()==windowed_geometry
    player.media.pause();spin(200);player.media.setPosition(4000);spin(250)
    assert abs(player.media.position()-4000)<250
    player.close();player.open_file(window.library.query()[0]['files'][0]);spin(400)
    assert not errors, errors
    player.close();window.close();player.shutdown_mpv()
    print('libmpv native video + GPU shader + Qt controls composition / seek / reopen passed')
