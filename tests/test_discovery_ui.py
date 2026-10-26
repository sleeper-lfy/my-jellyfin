import threading
import time
from PySide6.QtCore import QEventLoop,QTimer,Qt
from PySide6.QtWidgets import QMessageBox,QInputDialog
from lumen.ui import MainWindow
from lumen.plugins import Plugins
from test_core import add_work


def settle(app,window):
    deadline=time.monotonic()+8
    while (window.jobs or window._browse_job is not None or window._browse_pending is not None or window._auxiliary_jobs or not window.discovery_images.idle) and time.monotonic()<deadline:
        loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
    app.processEvents()
    assert not window.jobs and window._browse_job is None and window._browse_pending is None


def discovered(library,title,year=2024,tags=None):
    identifier=add_work(library,title,year=year,local=False,metadata={'tags':tags or ['Space drama']})
    with library.db:
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(identifier,'site','Example',str(identifier),'https://example.org/'+str(identifier),'2026-01-01','2026-01-01',8.0))
    return identifier


def plugins(_):
    return [{'id':'site','name':'Example','capabilities':['search','discover'],'search_filters':['name','tag'],'config':{'enabled':True}}]


def test_visible_discovery_name_tag_search_and_independent_full_result_sort(qapp,tmp_path):
    window=MainWindow(tmp_path/'discovery-filters')
    try:
        window.library.set_setting('catalog_sort','title');window.library.set_setting('catalog_descending',False)
        for index in range(70):discovered(window.library,f'Movie {index:02}',year=1950+index)
        window.show();window.navigate('discover');panel=window.discovery_panel
        assert len(window.current_items)==70 and panel.isVisible() and panel.name.isVisible() and panel.tag.isVisible()
        assert panel.tag.findText('Space drama')>=0 and panel.sort.currentData()=='discovered'
        panel.name.setText('Movie 6');panel.tag.setEditText('SPACE');panel.apply_local()
        assert len(window.current_items)==10
        panel.sort.setCurrentIndex(panel.sort.findData('year'))
        assert [item['year'] for item in window.current_items]==sorted([item['year'] for item in window.current_items],reverse=True)
        panel.direction.click()
        assert [item['year'] for item in window.current_items]==sorted([item['year'] for item in window.current_items])
        assert window.library.setting('catalog_sort')=='title' and window.library.setting('catalog_descending') is False
        panel.clear();assert len(window.current_items)==70 and panel.tag.findText('Space drama')>=0
    finally:window.close()


def test_online_exact_results_keep_local_fuzzy_match_and_explicit_empty_ids(qapp,tmp_path,monkeypatch):
    from lumen import discovery_search
    monkeypatch.setattr(Plugins,'installed',plugins)
    window=MainWindow(tmp_path/'online-exact')
    local=add_work(window.library,'Different canonical title',metadata={'tags':['Original tag']})
    original=window.library.work(local)['metadata']
    discovered(window.library,'Previously discovered')
    calls=[];results=[{'ids':[local],'count':1,'errors':['Other provider is unavailable']},{'ids':[],'count':0,'errors':[]}]
    def search(library,query,**kwargs):
        calls.append((threading.get_ident(),query,kwargs));return results.pop(0)
    monkeypatch.setattr(discovery_search,'search_sites',search)
    try:
        window.show();window.navigate('discover');panel=window.discovery_panel
        panel.name.setText('Fuzzy website query');panel.tag.setEditText('Website tag');panel.site.click();settle(qapp,window)
        assert calls and calls[0][0]!=threading.get_ident()
        assert [item['id'] for item in window.current_items]==[local]
        assert panel.online_results() and panel.request_fields()=={'source':'','category':'','tag_query':''}
        assert 'query' not in window.effective_filters() and 'Other provider is unavailable' in panel.notice.text()
        assert window.library.work(local)['metadata']==original
        panel.name.setText('No matches');panel.site.click();settle(qapp,window)
        assert window.filters['ids']==[] and window.current_items==[] and window.cards.count()==0
        panel.local.click();assert panel.mode=='local' and 'ids' not in window.filters
    finally:window.close();settle(qapp,window)


def test_online_failure_is_visible_and_retryable(qapp,tmp_path,monkeypatch):
    from lumen import discovery_search
    monkeypatch.setattr(Plugins,'installed',plugins)
    def fail(*args,**kwargs):raise RuntimeError('All providers failed')
    monkeypatch.setattr(discovery_search,'search_sites',fail)
    warnings=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:warnings.append(args))
    window=MainWindow(tmp_path/'online-failed')
    try:
        window.show();window.navigate('discover');panel=window.discovery_panel
        panel.name.setText('Example');panel.site.click();settle(qapp,window)
        assert 'All providers failed' in panel.notice.text() and warnings
        assert '保留上次结果' in panel.notice.text()
        assert panel.site.isEnabled() and not panel.online_results()
        assert '0 部作品' not in panel.notice.text()
    finally:window.close();settle(qapp,window)


def test_search_completion_during_detail_does_not_leave_permanent_loading_notice(qapp,tmp_path,monkeypatch):
    from lumen import discovery_search
    monkeypatch.setattr(Plugins,'installed',plugins)
    entered=threading.Event();release=threading.Event()
    window=MainWindow(tmp_path/'search-detail-completion')
    identifier=discovered(window.library,'Existing result')
    def slow(*args,**kwargs):
        entered.set();release.wait(5);return {'ids':[identifier],'count':1,'errors':[]}
    monkeypatch.setattr(discovery_search,'search_sites',slow)
    try:
        window.show();window.navigate('discover');panel=window.discovery_panel
        panel.name.setText('New search');panel.site.click();assert entered.wait(2)
        snapshot=panel.snapshot();assert '正在后台搜索' not in snapshot['notice']
        window.open_details(identifier,fetch=False);release.set();settle(qapp,window)
        assert window.detail_page.work_id==identifier and '已完成' in panel.notice.text()
        window.back_details();panel.restore(snapshot)
        assert '正在后台搜索' not in panel.notice.text() and panel.site.isEnabled()
    finally:release.set();window.close();settle(qapp,window)


def test_detail_metadata_navigation_restores_discovery_controls_and_sort(qapp,tmp_path,monkeypatch):
    monkeypatch.setattr(Plugins,'installed',plugins)
    window=MainWindow(tmp_path/'discovery-return')
    work_id=discovered(window.library,'Matching title',tags=['Space drama'])
    try:
        window.show();window.navigate('discover');panel=window.discovery_panel
        panel.name.setText('Matching');panel.tag.setEditText('Space');panel.apply_local()
        panel.sort.setCurrentIndex(panel.sort.findData('title'));panel.direction.click()
        state=panel.snapshot();window.open_details(work_id,fetch=False)
        window.detail_page.tag_links.linkActivated.emit('0')
        assert panel.mode=='local' and panel.name.text()==''
        window.back_navigation()
        assert window.detail_page.work_id==work_id and panel.snapshot()==state
        window.back_details()
        assert window.detail_page is None and panel.snapshot()==state
        assert [item['id'] for item in window.current_items]==[work_id]
    finally:window.close()


def test_builtin_site_update_is_explicit_preserves_proxy_and_enables_tag_search(qapp,tmp_path,monkeypatch):
    import json
    from pathlib import Path
    window=MainWindow(tmp_path/'site-update');manager=Plugins(window.library)
    manager.install(Path(__file__).resolve().parents[1]/'plugins'/'internet-archive')
    manager.configure('internet-archive',{'enabled':False,'proxy':'http://127.0.0.1:18888','priority':9})
    path=manager.root/'internet-archive'/'manifest.json';manifest=json.loads(path.read_text());manifest.pop('search_filters',None);manifest['version']='1.0.0';path.write_text(json.dumps(manifest))
    prompts=[]
    def choose(parent,title,label,choices,*args):
        prompts.append((title,label,choices));return choices[1],True
    monkeypatch.setattr(QInputDialog,'getItem',choose)
    try:
        window.show();window.navigate('discover');panel=window.discovery_panel
        assert not panel.site.isEnabled()
        panel.install.click();settle(qapp,window)
        config=window.library.setting('plugin:internet-archive')
        assert config['enabled'] and config['proxy']=='http://127.0.0.1:18888' and config['priority']==9
        assert panel.site.isEnabled() and '名称、标签' in panel.capability.text()
        assert prompts and '并启用' in prompts[0][0] and 'archive.org' in prompts[0][2][1]
        assert 'tag' in Plugins(window.library).installed()[0]['search_filters']
    finally:window.close();settle(qapp,window)
