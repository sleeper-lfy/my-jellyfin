"""Real mixed-format import and HTTP decoding; this is not Android device decoding."""
import subprocess
import pytest
from lumen.server import LanServer


@pytest.mark.parametrize('suffix,options', [
    ('.mp4', ['-c:v','libx264','-preset','ultrafast','-c:a','aac']),
    ('.mkv', ['-c:v','libx265','-preset','ultrafast','-pix_fmt','yuv420p10le','-x265-params','pools=1:frame-threads=1:log-level=error','-c:a','eac3']),
    ('.webm', ['-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-c:a','libopus']),
    ('.mkv', ['-c:v','libaom-av1','-cpu-used','8','-c:a','flac']),
    ('.avi', ['-c:v','mpeg4','-c:a','libmp3lame']),
    ('.asf', ['-c:v','wmv2','-c:a','wmav2']),
    ('.vob', ['-c:v','mpeg2video','-c:a','ac3','-f','vob']),
    ('.rm', ['-c:v','rv20','-an']),
])
def test_mixed_formats_import_and_stream(library, tmp_path, suffix, options):
    folder=tmp_path/'media';folder.mkdir();target=folder/('Mixed.2024'+suffix)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=25',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.6',
                    '-threads','2',*options,'-y',str(target)],check=True,capture_output=True,timeout=30)
    result=library.import_folder(folder,'movie')
    assert result['imported']==1, result['errors']
    file_id=library.db.execute('SELECT id FROM files').fetchone()[0]
    server=LanServer(library.directory,host='127.0.0.1',port=0);server.start()
    try:
        result=subprocess.run(['ffmpeg','-v','error','-headers','Authorization: Bearer '+server.token+'\r\n',
            '-i',f'http://127.0.0.1:{server.port}/api/files/{file_id}/stream','-frames:v','1','-f','null','-'],
            capture_output=True,timeout=20)
        assert result.returncode==0, result.stderr.decode()
    finally:server.stop()
