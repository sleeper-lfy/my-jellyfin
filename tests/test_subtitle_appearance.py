"""Subtitle style changes keep the video visible outside individual glyphs."""
import json
import os
import subprocess
import sys

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect,QWidget

from lumen.player import Player


def test_caption_background_stays_transparent_after_restoring_preferences(qapp,library):
    player=Player(library)
    player.subtitle_preferences={'subtitle_size':30,'subtitle_position':75,'subtitle_delay':1}
    player.apply_subtitle_preferences()
    assert 'background:transparent' in player.caption.styleSheet()
    assert '30px' in player.caption.styleSheet()
    shadow=player.caption.graphicsEffect()
    assert isinstance(shadow,QGraphicsDropShadowEffect) and shadow.color().alpha()>0
    # Render over a known video-like color. Empty areas of the full-width
    # caption must keep that exact color instead of receiving the former box.
    surface=QWidget();surface.resize(640,140);surface.setStyleSheet('background:#397ab5;')
    caption=player.caption;caption.setParent(surface);caption.setGeometry(10,20,620,100)
    caption.setText('Subtitle example\nSecond line');caption.show();surface.show();qapp.processEvents()
    picture=surface.grab().toImage();background=QColor('#397ab5')
    for point in [(12,22),(25,45),(615,45),(320,24),(320,115)]:
        assert picture.pixelColor(*point)==background
    light=sum(picture.pixelColor(x,y).red()>220 and picture.pixelColor(x,y).green()>220 and picture.pixelColor(x,y).blue()>220
              for y in range(25,115) for x in range(160,480))
    dark=sum(picture.pixelColor(x,y).red()<40 and picture.pixelColor(x,y).green()<70
             for y in range(25,115) for x in range(160,480))
    assert light>100 and dark>30
    # The unchanged cue timing still uses the restored delay.
    player.cues=[(0,2,'Timed subtitle')];player.position_changed(500);assert caption.text()==''
    player.position_changed(1500);assert caption.text()=='Timed subtitle'
    surface.close();player.close()


def test_real_mpv_removes_ass_box_pixels_without_switching_track_or_restarting(video_factory,tmp_path):
    if os.environ.get('LUMEN_REQUIRE_MPV')!='1':
        pytest.skip('Set LUMEN_REQUIRE_MPV=1 when the libmpv runtime is installed')
    source=video_factory('Subtitle box.mp4','blue',6)
    ass=tmp_path/'boxed.ass'
    ass.write_text('''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,32,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,8,0,2,10,10,25,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,Subtitle example
''',encoding='utf-8')
    script=r'''
import json,sys
from PySide6.QtCore import QCoreApplication,QUrl,QEventLoop,QTimer
from lumen.mpv_backend import MpvMedia
app=QCoreApplication([])
def spin(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
def pixels(engine):
    picture=engine.command('screenshot-raw','subtitles');raw=picture['data']
    assert picture['format']=='bgr0'
    dark=light=0
    for i in range(0,len(raw),4):
        blue,green,red=raw[i:i+3]
        dark+=red<30 and green<30 and blue<30
        light+=red>220 and green>220 and blue>220
    return {'dark':dark,'light':light}
media=MpvMedia(headless=True)
try:
    media.engine.sub_ass_override='no';media.engine.sub_ass_style_overrides=[]
    media.setSource(QUrl.fromLocalFile(sys.argv[1]));media.play();spin(250)
    media.engine.command('sub-add',sys.argv[2],'select');spin(300)
    before=pixels(media.engine);position=media.position();track=media.engine.sid
    assert before['dark']>100 and before['light']>10
    media.set_subtitle_style(0,64,90);spin(150)
    after=pixels(media.engine)
    assert after['light']>10,(before,after)
    assert after['dark']<before['dark']*.2,(before,after)
    assert before['dark']/before['light']>5*after['dark']/after['light'],(before,after)
    assert media.engine.sid==track and media.engine.sub_text=='Subtitle example'
    assert media.position()>=position-50 and media.playbackState().name=='PlayingState'
    print(json.dumps({'before':before,'after':after,'position_before':position,'position_after':media.position()}))
finally:media.shutdown()
'''
    result=subprocess.run([sys.executable,'-c',script,str(source),str(ass)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    metrics=json.loads(result.stdout.strip().splitlines()[-1])
    assert metrics['after']['dark']<metrics['before']['dark']*.2
