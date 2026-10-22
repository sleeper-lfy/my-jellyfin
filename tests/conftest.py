import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_MEDIA_BACKEND', 'ffmpeg')
import subprocess
from pathlib import Path
import pytest
from lumen.core import Library


@pytest.fixture
def library(tmp_path):
    lib = Library(tmp_path / 'data')
    yield lib
    lib.close()


@pytest.fixture(scope='session')
def video_factory(tmp_path_factory):
    root = tmp_path_factory.mktemp('real-videos')
    cache = {}
    def make(name='Sample.2024.mp4', color='blue', seconds=4):
        key = (name, color, seconds)
        if key not in cache:
            target = root / str(len(cache)) / name
            target.parent.mkdir(parents=True)
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c={color}:s=320x180:r=24',
                            '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t',str(seconds),'-c:v','mpeg4','-c:a','aac','-y',str(target)],check=True,timeout=30)
            cache[key] = target
        return cache[key]
    return make


@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
