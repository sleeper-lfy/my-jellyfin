"""The headless parent stays Qt-free while original image rules run in a child."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import zlib

import pytest

from lumen import image_isolation as isolation
from lumen import image_worker
from lumen.artwork import PosterPathError, _poster_dimensions
from lumen.core import ImportCancelled, identity, now


def png(path, width=64, height=96):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    raw = (b'\0' + bytes((72, 118, 132)) * width) * height
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return path


def work(library, metadata=None):
    with library.db:
        cursor=library.db.execute('INSERT INTO works(identity,kind,title,year,metadata,added) VALUES (?,?,?,?,?,?)',
                                  (identity('Coast Journal',2025,'movie'),'movie','Coast Journal',2025,json.dumps(metadata or {}),now()))
    return cursor.lastrowid


def arguments(path):
    details=path.stat()
    return {'path':str(path.absolute()),'modified':details.st_mtime_ns,'size':details.st_size}


def environment():
    result=os.environ.copy();result['LUMEN_BACKGROUND_SERVICE']='1';result.pop('LUMEN_IMAGE_WORKER',None)
    source=str(Path(__file__).resolve().parents[1]/'src')
    result['PYTHONPATH']=source+(os.pathsep+result['PYTHONPATH'] if result.get('PYTHONPATH') else '')
    return result


@pytest.fixture(autouse=True)
def reset_isolation(monkeypatch):
    monkeypatch.delenv('LUMEN_BACKGROUND_SERVICE',raising=False)
    monkeypatch.delenv('LUMEN_IMAGE_WORKER',raising=False)
    isolation.register_shutdown_event(None)
    _poster_dimensions.cache_clear()
    yield
    isolation.register_shutdown_event(None)
    _poster_dimensions.cache_clear()


def test_real_image_roundtrips_never_import_qt_into_the_service_parent(library,tmp_path):
    source=png(tmp_path/'coast.png');identifier=work(library)
    script='''
import json,sys
from pathlib import Path
from lumen.core import Library
from lumen.nfo import cache_poster
from lumen.artwork import _poster_dimensions
from lumen.discovery_search import cache_discovery_cover
source,directory=map(Path,sys.argv[1:3]);identifier=int(sys.argv[3])
library=Library(directory,initialize=False)
try:
    cached=cache_poster(source,directory)
    path=Path(cached);details=path.stat()
    dimensions=_poster_dimensions(cached,details.st_mtime_ns,details.st_size)
    library.set_setting('artwork_'+str(identifier),{'poster':cached})
    selected=cache_discovery_cover(library,identifier,poster_only=True)
    print(json.dumps({'dimensions':dimensions,'same_cache':selected==cached,'cache_exists':path.is_file(),
                      'qt_loaded':any(name=='PySide6' or name.startswith('PySide6.') for name in sys.modules)}))
finally:library.close()
'''
    result=subprocess.run([sys.executable,'-c',script,str(source),str(library.directory),str(identifier)],env=environment(),capture_output=True,text=True,timeout=35,check=True)
    assert json.loads(result.stdout)=={'dimensions':[64,96],'same_cache':True,'cache_exists':True,'qt_loaded':False}


def test_gui_and_worker_modes_keep_the_original_reader_and_do_not_spawn(tmp_path,monkeypatch):
    source=png(tmp_path/'coast.png');values=arguments(source)
    monkeypatch.setattr(isolation,'run_image_operation',lambda *args,**kwargs:pytest.fail('GUI/worker path must not delegate'))
    assert _poster_dimensions(**values)==(64,96)
    _poster_dimensions.cache_clear();monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1');monkeypatch.setenv('LUMEN_IMAGE_WORKER','1')
    assert _poster_dimensions(**values)==(64,96)


def test_all_three_headless_entries_delegate_before_any_gui_helper(library,tmp_path,monkeypatch):
    from lumen.nfo import cache_poster
    from lumen.discovery_search import cache_discovery_cover
    source=png(tmp_path/'coast.png');calls=[]
    def invoke(op,**values):
        calls.append((op,values))
        return (64,96) if op=='dimensions' else str(source) if op=='cache_poster' else None
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1');monkeypatch.setattr(isolation,'run_image_operation',invoke)
    assert _poster_dimensions(**arguments(source))==(64,96)
    assert cache_poster(source,library.directory)==str(source)
    assert cache_discovery_cover(library,42,poster_only=True) is None
    assert [item[0] for item in calls]==['dimensions','cache_poster','cache_discovery_cover']
    assert calls[-1][1]=={'directory':str(library.directory.absolute()),'work_id':42,'poster_only':True}


def test_original_poster_path_authorization_error_survives_worker_roundtrip(library,tmp_path,monkeypatch):
    from lumen.discovery_search import cache_discovery_cover
    identifier=work(library);outside=png(tmp_path/'private-outside-cache.png')
    library.set_setting(f'artwork_{identifier}',{'poster':str(outside)})
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    with pytest.raises(PosterPathError) as raised:
        cache_discovery_cover(library,identifier,poster_only=True)
    assert str(outside) not in str(raised.value)
    assert library.setting(f'artwork_{identifier}')=={'poster':str(outside)}


def test_discovery_worker_still_requires_the_original_enabled_provider_and_domain(library,monkeypatch):
    from lumen.discovery_search import cache_discovery_cover
    identifier=work(library,{'poster':'https://unapproved.invalid/no-network.png'})
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    assert cache_discovery_cover(library,identifier,poster_only=True) is None
    assert not library.work(identifier)['thumbnail']
    assert library.work(identifier)['metadata']=={'poster':'https://unapproved.invalid/no-network.png'}


def test_local_poster_size_boundary_is_still_applied_in_the_worker(library,tmp_path,monkeypatch):
    from lumen.nfo import cache_poster
    source=tmp_path/'too-large.png'
    with source.open('wb') as stream:stream.truncate(20_000_001)
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    with pytest.raises(ValueError):cache_poster(source,library.directory)
    assert not list((library.directory/'cache').glob('nfo-*'))


def test_dimension_revision_is_checked_before_decode_and_stale_input_is_not_cached(tmp_path,monkeypatch):
    source=png(tmp_path/'coast.png');values=arguments(source);values['modified']+=1
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    with pytest.raises(OSError):_poster_dimensions(**values)
    assert _poster_dimensions(**arguments(source))==(64,96)


def sleeping_worker(monkeypatch):
    created=threading.Event();processes=[];folders=[];original=subprocess.Popen
    def command(request,response):
        folders.append(request.parent)
        return [sys.executable,'-c','import time; time.sleep(60)']
    def launch(*args,**kwargs):
        process=original(*args,**kwargs);processes.append(process);created.set();return process
    monkeypatch.setattr(isolation,'_command',command);monkeypatch.setattr(isolation.subprocess,'Popen',launch)
    return created,processes,folders


def test_timeout_terminates_the_real_worker_and_cleans_the_private_messages(tmp_path,monkeypatch):
    source=png(tmp_path/'coast.png');created,processes,folders=sleeping_worker(monkeypatch);start=time.monotonic()
    with pytest.raises(TimeoutError,match='图片处理超时'):
        isolation.run_image_operation('dimensions',timeout=.2,**arguments(source))
    assert created.is_set() and processes[0].poll() is not None
    assert time.monotonic()-start<4
    assert folders and all(not folder.exists() for folder in folders)


def test_service_shutdown_cancels_an_active_real_worker_and_reaps_it(tmp_path,monkeypatch):
    source=png(tmp_path/'coast.png');created,processes,folders=sleeping_worker(monkeypatch);stop=threading.Event();isolation.register_shutdown_event(stop)
    def cancel():
        if created.wait(2):stop.set()
    thread=threading.Thread(target=cancel);thread.start()
    try:
        with pytest.raises(ImportCancelled):isolation.run_image_operation('dimensions',timeout=5,**arguments(source))
    finally:thread.join(timeout=3)
    assert created.is_set() and processes[0].poll() is not None
    assert folders and all(not folder.exists() for folder in folders)


@pytest.mark.parametrize('payload',[
    {'op':'eval','path':'/tmp/source'},
    {'op':'dimensions','path':'relative.png','modified':1,'size':1},
    {'op':'dimensions','path':'/tmp/source','modified':True,'size':1},
    {'op':'dimensions','path':'/tmp/source','modified':1,'size':1,'command':['anything']},
    {'op':'cache_discovery_cover','directory':'/tmp/data','work_id':True,'poster_only':True},
    {'op':'cache_discovery_cover','directory':'/tmp/data','work_id':1,'poster_only':'true'},
])
def test_worker_accepts_only_the_closed_local_operation_schema(payload):
    with pytest.raises(ValueError):isolation.validate_request(payload)


def test_worker_never_overwrites_a_response_or_reads_a_public_request(tmp_path,monkeypatch):
    folder=tmp_path/'private';folder.mkdir(mode=0o700);source=folder/'request.json';target=folder/'response.json'
    source.write_text(json.dumps({'op':'dimensions',**arguments(png(folder/'coast.png'))}));source.chmod(0o600)
    monkeypatch.setattr(image_worker,'perform',lambda request:pytest.fail('Invalid channels must fail before dispatch'))
    target.write_text('keep original')
    assert image_worker.main(['--request',str(source),'--response',str(target)])==2
    assert target.read_text()=='keep original'
    target.unlink()
    if os.name!='nt':
        source.chmod(0o644)
        assert image_worker.main(['--request',str(source),'--response',str(target)])==2
        assert not target.exists()


def test_worker_ignores_arbitrary_exception_messages_and_response_shape(tmp_path,monkeypatch):
    folder=tmp_path/'private';folder.mkdir(mode=0o700);source=folder/'request.json';target=folder/'response.json'
    source.write_text(json.dumps({'op':'dimensions',**arguments(png(folder/'coast.png'))}));source.chmod(0o600)
    def fail(request):raise ValueError('/private/location secret-token https://user:password@example.invalid')
    monkeypatch.setattr(image_worker,'perform',fail)
    assert image_worker.main(['--image-worker','--request',str(source),'--response',str(target)])==0
    assert json.loads(target.read_text())=={'ok':False,'error':{'type':'ValueError'}}
    target.write_text(json.dumps({'ok':True,'result':[True,96]}))
    with pytest.raises(RuntimeError,match='尺寸'):isolation._read_response(target,'dimensions')


def test_source_and_frozen_commands_are_explicit_and_worker_environment_cannot_recurse(tmp_path,monkeypatch):
    source,target=tmp_path/'request.json',tmp_path/'response.json';monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    assert isolation._command(source,target)==[sys.executable,'-m','lumen.image_worker','--image-worker','--request',str(source),'--response',str(target)]
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    assert isolation._command(source,target)==[sys.executable,'--image-worker','--request',str(source),'--response',str(target)]
    result=isolation._environment();assert 'LUMEN_BACKGROUND_SERVICE' not in result and result['LUMEN_IMAGE_WORKER']=='1'
