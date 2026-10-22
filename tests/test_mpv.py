import os
import subprocess
import sys
from pathlib import Path
import pytest


def test_real_libmpv_decode_seek_tracks_and_end(video_factory):
    # Qt Multimedia and distro libmpv can load different FFmpeg builds. Keep
    # native backend checks in separate processes, as they are used in the app.
    if os.environ.get('LUMEN_REQUIRE_MPV') != '1':
        pytest.skip('Set LUMEN_REQUIRE_MPV=1 when the libmpv runtime is installed')
    source=video_factory('mpv.mp4','blue',6)
    script=Path(__file__).resolve().parents[1]/'scripts/verify-mpv-playback.py'
    result=subprocess.run([sys.executable,str(script),str(source)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stdout+'\n'+result.stderr
