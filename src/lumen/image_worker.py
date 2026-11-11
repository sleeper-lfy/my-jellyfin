"""Private single-operation image process. Original domain validation runs here."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from .image_isolation import MAX_MESSAGE, validate_request, read_message


def perform(request):
    request = validate_request(request)
    op = request['op']
    if op == 'dimensions':
        from .artwork import _poster_dimensions, PosterPathError
        path=Path(request['path'])
        if path.is_symlink():raise PosterPathError('海报路径无效')
        current=path.stat()
        if current.st_mtime_ns != request['modified'] or current.st_size != request['size']:
            raise OSError('图片文件已变化')
        return _poster_dimensions(str(path),request['modified'],request['size'])
    if op == 'cache_poster':
        from .nfo import cache_poster
        return cache_poster(Path(request['path']),Path(request['directory']))
    from .core import Library
    from .discovery_search import cache_discovery_cover
    directory=Path(request['directory'])
    if not directory.is_dir() or not (directory/'library.sqlite').is_file():raise ValueError('资料库不存在')
    library=Library(directory,initialize=False,timeout=10)
    try:
        return cache_discovery_cover(library,request['work_id'],poster_only=request['poster_only'])
    finally:
        library.close()


def _channels(request, response):
    if not request.is_absolute() or not response.is_absolute() or request.parent != response.parent or request == response:
        raise ValueError('无效图片任务通道')
    folder=request.parent
    if folder.is_symlink() or request.is_symlink() or response.exists() or response.is_symlink():
        raise ValueError('无效图片任务通道')
    details=request.stat();parent=folder.stat()
    if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_MESSAGE or details.st_nlink != 1:
        raise ValueError('无效图片任务通道')
    if os.name != 'nt' and (parent.st_mode&0o077 or details.st_mode&0o077 or details.st_uid!=os.getuid() or parent.st_uid!=os.getuid()):
        raise ValueError('图片任务通道未受保护')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Private Lumen image worker')
    parser.add_argument('--image-worker',action='store_true')
    parser.add_argument('--request',required=True)
    parser.add_argument('--response',required=True)
    args=parser.parse_args(argv)
    source,target=Path(args.request),Path(args.response)
    try:
        _channels(source,target)
    except (OSError,ValueError):
        return 2
    # Set this even for direct module execution; never recursively spawn another image job.
    os.environ.pop('LUMEN_BACKGROUND_SERVICE',None)
    os.environ['LUMEN_IMAGE_WORKER']='1'
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    try:
        request=read_message(source)
        result={'ok':True,'result':perform(request)}
    except Exception as error:
        from .artwork import PosterPathError
        kind='PosterPathError' if isinstance(error,PosterPathError) else 'OSError' if isinstance(error,OSError) else 'ValueError' if isinstance(error,ValueError) else 'RuntimeError'
        result={'ok':False,'error':{'type':kind}}
    try:
        encoded=json.dumps(result,ensure_ascii=False).encode('utf-8')
        if len(encoded)>MAX_MESSAGE:return 2
        descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(descriptor,'wb') as output:output.write(encoded)
    except OSError:
        return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
