"""Exercise the real process protocol using a tiny synthetic JavSP API.

These tests make no claim about live provider availability.
"""
import json
from pathlib import Path
import shutil
import sys
import time
import pytest
from lumen.javsp_bridge import ID,code,normalize,probe,validate_settings
from lumen.plugins import Plugins
from lumen.core import ImportCancelled
from lumen.numbered_sources import resolve


@pytest.fixture
def engine(tmp_path):
    root=tmp_path/'JavSP';package=root/'javsp';web=package/'web';web.mkdir(parents=True)
    (package/'__init__.py').write_text('')
    (web/'__init__.py').write_text('')
    (package/'config.py').write_text("from types import SimpleNamespace\nclass Cfg:\n    def __init__(self):\n        self.crawler=SimpleNamespace(selection={'normal':['fixture'],'fc2':['fixture']})\n")
    (package/'datatype.py').write_text('class MovieInfo:\n    def __init__(self,dvdid):self.dvdid=dvdid\n')
    (web/'fixture.py').write_text("""from pathlib import Path
def parse_data(info):
    root=Path(__file__).parents[2]
    marker=root/'calls.txt'
    marker.write_text(marker.read_text()+'x' if marker.exists() else 'x')
    info.title='测试影片'
    info.url='https://source.example/'+info.dvdid
    info.plot='测试剧情'
    info.publish_date='2024-06-01'
    info.actress=['测试演员']
    info.actress_pics={'测试演员':'https://image.example/actor.jpg'}
    info.genre=['剧情']
    info.cover='https://image.example/poster.jpg'
    info.preview_pics=['https://image.example/still.jpg']
    info.score='8.2'
    info.magnet='magnet:?secret'
""",encoding='utf-8')
    (root/'config.yml').write_text('fixture: true')
    return {'python':str(Path(sys.executable).absolute()),'root':str(root),'config':'','image_domains':['image.example']}


def enable(library,engine):
    manager=Plugins(library);manager.update_builtin_numbered_plugin(ID)
    library.set_setting('javsp',validate_settings(engine));manager.configure(ID,{'enabled':True})
    return manager


def test_external_process_search_detail_cache_and_vr_resolution(library,engine):
    manager=enable(library,engine)
    candidate=manager.run(ID,'search',query='abc_123')[0]
    assert candidate['id']=='ABC-123' and candidate['title']=='测试影片'
    assert candidate['actors'][0]['photo']=='https://image.example/actor.jpg'
    assert candidate['year']==2024 and candidate['rating']==8.2 and candidate['tags']==['剧情']
    assert candidate['stills']==['https://image.example/still.jpg']
    assert 'magnet' not in json.dumps(candidate) and 'download_url' not in candidate
    assert manager.run(ID,'detail',url=candidate['url'])==[candidate]
    result=resolve(library,{'kind':'vr','title':'ABC-123','files':[],'year':None},ID)
    assert result['candidate']==candidate and result['plugin']==ID
    assert (Path(engine['root'])/'calls.txt').read_text()=='x'
    assert not list(library.directory.glob('javsp-*'))


def test_probe_imports_dependencies_but_never_crawls_or_installs(library,engine):
    result=probe(library,engine)
    assert result['ready'] and result['sources']['fc2']==['fixture']
    assert not (Path(engine['root'])/'calls.txt').exists()
    assert not Plugins(library).installed() and library.setting('javsp') is None


def test_packaged_bridge_runs_from_application_assets(library,engine,tmp_path,monkeypatch):
    packaged=tmp_path/'bundle';destination=packaged/'plugins'/ID
    shutil.copytree(Plugins.builtin_numbered_plugin(ID),destination)
    monkeypatch.setattr(sys,'_MEIPASS',str(packaged),raising=False)
    assert probe(library,engine)['ready']


def test_fc2_translation_in_real_worker(library,engine):
    candidate=enable(library,engine).run(ID,'search',query='FC2-PPV-123456')[0]
    assert candidate['id']=='FC2-PPV-123456'
    assert candidate['url'].endswith('/FC2-123456')


def test_mismatch_never_becomes_candidate(library,engine):
    parser=Path(engine['root'])/'javsp/web/fixture.py'
    parser.write_text(parser.read_text(encoding='utf-8')+"    info.dvdid='XYZ-999'\n",encoding='utf-8')
    with pytest.raises(ValueError,match='编号一致'):enable(library,engine).run(ID,'search',query='ABC-123')
    assert not list((library.directory/'cache/javsp').glob('*.json'))


def test_external_worker_cancels_while_site_is_blocked(library,engine):
    parser=Path(engine['root'])/'javsp/web/fixture.py'
    parser.write_text('import time\ndef parse_data(info):time.sleep(60)\n')
    manager=enable(library,engine);start=time.monotonic()
    with pytest.raises(ImportCancelled):
        manager.run(ID,'search',query='ABC-123',cancelled=lambda:time.monotonic()-start>.4)
    assert time.monotonic()-start<5
    assert library.db.execute("SELECT status FROM tasks WHERE kind='scrape'").fetchone()[0]=='cancelled'
    assert not list(library.directory.glob('javsp-*'))


def test_environment_changes_and_expiry_invalidate_cache(library,engine):
    manager=enable(library,engine);candidate=manager.run(ID,'search',query='ABC-123')[0]
    config=Path(engine['root'])/'config.yml';config.write_text('changed: true')
    with pytest.raises(ValueError,match='过期'):manager.run(ID,'detail',url=candidate['url'])
    manager.run(ID,'search',query='ABC-123')
    assert (Path(engine['root'])/'calls.txt').read_text()=='xx'
    for cache in (library.directory/'cache/javsp').glob('*.json'):
        data=json.loads(cache.read_text());data['created']=time.time()-601;cache.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='过期'):manager.run(ID,'detail',url=candidate['url'])


def test_worker_timeout_is_reported_and_task_fails(library,engine,monkeypatch):
    import subprocess
    from lumen import javsp_bridge
    manager=enable(library,engine)
    def timeout(command,seconds,cancelled):raise subprocess.TimeoutExpired(command,seconds)
    monkeypatch.setattr(javsp_bridge,'media_process',timeout)
    with pytest.raises(ValueError,match='180 秒'):manager.run(ID,'search',query='ABC-123')
    assert library.db.execute("SELECT status FROM tasks WHERE kind='scrape'").fetchone()[0]=='failed'


def test_explicit_install_enable_and_image_permissions(library,engine,tmp_path):
    manager=Plugins(library);manager.update_builtin_numbered_plugin(ID)
    with pytest.raises(ValueError,match='未启用'):manager.run(ID,'search',query='ABC-123')
    copy=tmp_path/'fake';shutil.copytree(Plugins.builtin_numbered_plugin(ID),copy)
    with pytest.raises(ValueError,match='内置副本'):manager.install(copy)
    manager=enable(library,engine);plugin=manager.installed()[0]
    assert 'image.example' in plugin['domains']
    with pytest.raises(ValueError):manager.fetch(plugin,'https://unlisted.example/private')
    manager.update_builtin_numbered_plugin(ID)
    assert library.setting('plugin:'+ID)['enabled'] and library.setting('javsp')['root']==engine['root']


@pytest.mark.parametrize('query',['name','ABC-123 XYZ-999','https://site.example/ABC-123','../ABC-123',''])
def test_only_explicit_codes(query):
    with pytest.raises(ValueError):code(query)


def test_invalid_configuration_and_missing_dependencies(library,engine):
    with pytest.raises(ValueError):validate_settings({**engine,'image_domains':['*.example.com']})
    with pytest.raises(ValueError):validate_settings({**engine,'python':engine['root']})
    (Path(engine['root'])/'javsp/config.py').write_text("raise ImportError('secret token must not leak')")
    with pytest.raises(ValueError,match='ImportError') as error:probe(library,engine)
    assert 'secret' not in str(error.value)


def test_python_venv_symlink_is_preserved(engine,tmp_path,monkeypatch):
    executable=tmp_path/'env/bin/python';executable.parent.mkdir(parents=True)
    try:executable.symlink_to(sys.executable)
    except OSError:
        # Windows accounts without link privileges model the same path alias.
        executable.write_bytes(b'python launcher')
        original=Path.resolve
        monkeypatch.setattr(Path,'resolve',lambda path,*a,**kw:original(Path(sys.executable)) if path==executable else original(path,*a,**kw))
    assert validate_settings({**engine,'python':str(executable)})['python']==str(executable)


def test_normalize_exact_identity_and_url_protocol():
    raw={'dvdid':'ABC-123','title':'Fixture','url':'https://source.example/123','cover':'file:///private','actress':['Test'],'actress_pics':{'Test':'javascript:bad'},'score':'nan'}
    result=normalize({'records':[{'info':raw}]},'ABC-123')
    assert 'poster' not in result and 'photo' not in result['actors'][0] and 'rating' not in result
    with pytest.raises(ValueError):normalize({'records':[{'info':raw}]},'XYZ-999')


def test_automatic_ingest_uses_javsp_fallback_and_keeps_vr(library,engine,tmp_path,monkeypatch):
    from test_ingestion import imported
    from lumen.ingestion import enqueue,process_pending
    manager=enable(library,engine)
    video,work=imported(library,tmp_path)
    # An unavailable primary must reach this actual external process provider.
    library.set_setting('numbered_fallbacks:vr',[ID])
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(_ for _ in ()).throw(ValueError('offline images')))
    enqueue(library,work,'disabled-primary','')
    assert process_pending(library)['completed']==1
    current=library.work(work['id'])
    assert current['kind']=='vr' and current['title']=='测试影片'
    assert current['sources'][0]['plugin']==ID and current['metadata']['overview']=='测试剧情'
    assert video.is_file() and len(library.query())==1


def test_settings_ui_save_detects_then_installs_explicitly(qapp,tmp_path,engine,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLineEdit,QCheckBox,QPushButton,QPlainTextEdit
    from lumen.ui import MainWindow
    from lumen.javsp_ui import show_javsp_settings
    window=MainWindow(tmp_path/'ui-save');saved=[]
    monkeypatch.setattr(window,'run_job',lambda title,run,done:done(run(window.library,SimpleNamespace(cancelled=lambda:False))))
    try:
        dialog=show_javsp_settings(window,lambda:saved.append(True))
        assert show_javsp_settings(window) is dialog
        for key in ('python','root','config'):dialog.findChild(QLineEdit,'javsp_'+key).setText(engine[key])
        dialog.findChild(QLineEdit,'javsp_image_domains').setText('image.example')
        dialog.findChild(QPushButton,'javsp_probe').click()
        assert not Plugins(window.library).installed() and not saved
        dialog.findChild(QCheckBox,'javsp_enabled').setChecked(True)
        dialog.findChild(QPushButton,'javsp_save').click()
        assert '已保存' in dialog.findChild(QPlainTextEdit,'javsp_status').toPlainText()
        assert window.library.setting('plugin:'+ID)['enabled'] and saved==[True]
        assert window.library.setting('javsp')['image_domains']==['image.example']
        dialog.close()
    finally:window.close()


def test_settings_ui_entry_and_invalid_save_does_not_enable(qapp,tmp_path):
    from PySide6.QtWidgets import QPushButton,QPlainTextEdit
    from lumen.ui import MainWindow
    from lumen.numbered_sources_ui import show_numbered_providers
    window=MainWindow(tmp_path/'ui')
    try:
        sources=show_numbered_providers(window);sources.findChild(QPushButton,'configureJavSP').click()
        dialog=window.javsp_settings_dialog
        assert dialog and not Plugins(window.library).installed()
        dialog.findChild(QPushButton,'javsp_save').click()
        assert 'Python' in dialog.findChild(QPlainTextEdit,'javsp_status').toPlainText()
        assert not window.library.setting('plugin:'+ID,{})
        dialog.close();sources.close()
    finally:window.close()
