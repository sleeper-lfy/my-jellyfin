"""Opt-in live provider check. Local fixture tests do not substitute for this operation."""
import argparse
from pathlib import Path
import os
import tempfile
from lumen.core import Library
from lumen.plugins import Plugins

parser=argparse.ArgumentParser()
parser.add_argument('--use-environment-proxy',action='store_true',help='Use the cloud machine proxy in temporary configuration only')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='lumen-live-') as directory:
    lib=Library(directory)
    plugins=Plugins(lib)
    plugins.install(Path(__file__).parents[1]/'plugins/tvmaze')
    config={'enabled':True}
    if args.use_environment_proxy:
        config['proxy']=os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or ''
    plugins.configure('tvmaze',config)
    try:
        rows=plugins.run('tvmaze','detail',url='https://www.tvmaze.com/shows/82/game-of-thrones')
        assert rows and rows[0]['kind']=='series' and rows[0]['actors']
        work_id=plugins.merge('tvmaze',rows[0])
        work=lib.work(work_id)
        assert work['sources'] and work['thumbnail']
        print('Live TVmaze detail, cast, poster and source persistence passed.')
    finally:
        lib.close()
