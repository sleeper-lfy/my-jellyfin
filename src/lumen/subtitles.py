"""Text subtitle decoding via FFmpeg; subtitle timestamps never count as watch time."""
import html
from pathlib import Path
import re
import subprocess
import os
from .core import tool


def read_subtitles(path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError('字幕文件过大')
    result = subprocess.run([tool('ffmpeg') or 'ffmpeg','-hide_banner','-loglevel','error','-i',str(path),'-f','srt','-'],
                            capture_output=True,check=True,timeout=20,creationflags=0x08000000 if os.name=='nt' else 0)
    text = result.stdout.decode('utf-8-sig')
    pattern = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.*?)(?=\n\s*\n|\Z)',re.S)
    cues = []
    for match in pattern.finditer(text):
        values = match.groups()
        def stamp(offset):
            return int(values[offset])*3600 + int(values[offset+1])*60 + int(values[offset+2]) + int(values[offset+3])/1000
        body = html.unescape(re.sub(r'<[^>]*>|\{[^}]*\}', '', values[8])).strip()
        cues.append((stamp(0),stamp(4),body))
    return cues
