import threading
import time
from PySide6.QtCore import QEventLoop, QTimer
from lumen.ui import MainWindow


def settle(app, window):
    deadline=time.monotonic()+5
    while (window._browse_job is not None or window._browse_pending is not None) and time.monotonic()<deadline:
        loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
    app.processEvents()
    assert window._browse_job is None and window._browse_pending is None


def test_nested_metadata_results_return_to_exact_source_page(qapp,tmp_path,video_factory):
    window=MainWindow(tmp_path/'navigation')
    source=video_factory('History movie.mp4')
    source.with_suffix('.nfo').write_text('<movie><title>History</title><tag>Adventure</tag><actor><name>Example actor</name></actor></movie>')
    window.library.import_folder(source.parent,'movie')
    work=window.library.query()[0]
    window.show();window.navigate('movie');window.filters={'year_min':2020};window.refresh()
    original_filters=dict(window.filters)
    window.open_details(work['id'],fetch=False)
    window.detail_page.tag_links.linkActivated.emit('0')
    assert window.heading.text()=='标签：Adventure' and window.detail_page is None
    window.open_details(work['id'],fetch=False)
    window.detail_page.actor_links.linkActivated.emit('0')
    assert window.filters=={'actor':'Example actor'}
    window.back_navigation()
    assert window.detail_page.work_id==work['id'] and window.filters=={'tags_all':['Adventure']}
    window.detail_page.accept()
    assert window.detail_page is None and window.heading.text()=='标签：Adventure'
    window.back_navigation()
    assert window.detail_page.work_id==work['id'] and window.filters==original_filters
    window.detail_page.accept()
    assert window.section=='movie' and window.filters==original_filters and not window.navigation_history
    window.navigate('recommend')
    assert window.heading.text()=='为我推荐' and window.nav_buttons['recommend'].isChecked()
    window.close()


def test_small_catalog_load_and_metadata_back_are_nonblocking_in_production(qapp,tmp_path,monkeypatch):
    from lumen import browse
    original=browse.load_view
    entered=threading.Event();release=threading.Event();threads=[]
    def slow(library,request):
        threads.append(threading.get_ident());entered.set();release.wait(3)
        return original(library,request)
    monkeypatch.setattr(MainWindow,'synchronous_small_catalog',False)
    monkeypatch.setattr(browse,'load_view',slow)
    window=MainWindow(tmp_path/'async-navigation')
    try:
        assert entered.wait(2)
        started=time.monotonic();window.navigate('recommend');window.navigate('discover')
        assert time.monotonic()-started<.5
        ticks=[];QTimer.singleShot(0,lambda:ticks.append(True));qapp.processEvents()
        assert ticks and window.section=='discover'
        release.set();settle(qapp,window)
        assert all(identifier!=threading.get_ident() for identifier in threads)
        assert window.heading.text()=='影片发现'
        window.search_metadata('actor','Example actor');settle(qapp,window)
        assert window.filters=={'actor':'Example actor'}
        window.back_navigation();settle(qapp,window)
        assert window.section=='discover' and window.filters=={}
    finally:
        release.set();settle(qapp,window);window.close()


def test_discovered_metadata_search_keeps_unimported_items_and_origin(qapp,tmp_path):
    from test_core import add_work
    window=MainWindow(tmp_path/'discovery-navigation')
    identifier=add_work(window.library,'Discovered sample',local=False,metadata={'tags':['Remote tag'],'actors':[{'name':'Remote actor'}]})
    with window.library.db:
        window.library.db.execute('INSERT INTO sources(work_id,plugin,site,source_id,url,updated) VALUES(?,?,?,?,?,?)',
            (identifier,'sample','Example','42','https://example.org/42','2026-01-01'))
    window.show();window.navigate('discover');window.tabs.setCurrentIndex(1)
    window.open_details(identifier,fetch=False)
    window.detail_page.tag_links.linkActivated.emit('0')
    assert window.section=='discover' and [item['id'] for item in window.current_items]==[identifier]
    window.search.setText('Discovered');window.search_all()
    assert window.section=='discover' and window.search.text()=='Discovered'
    window.back_navigation()
    assert window.detail_page.work_id==identifier and window.section=='discover'
    window.close()


def test_filter_facets_load_off_thread_without_replacing_typed_values_or_recommendation(qapp,tmp_path,monkeypatch):
    from lumen.core import Library
    from test_core import add_work
    entered=threading.Event();release=threading.Event();threads=[]
    def slow(library,*args,**kwargs):
        threads.append(threading.get_ident());entered.set();release.wait(3)
        return {'tags':['Drama'],'actors':['Existing actor'],'years':[2024]}
    window=MainWindow(tmp_path/'filter-responsive')
    add_work(window.library,'Matching movie',metadata={'tags':['Drama'],'actors':[{'name':'Typed actor'}]})
    window.show();window.navigate('recommend')
    monkeypatch.setattr(Library,'filter_options',slow)
    try:
        start=time.monotonic();window.filter_dialog()
        assert time.monotonic()-start<.5 and entered.wait(2)
        dialog=window._filter_dialog
        assert dialog is not None and dialog.isVisible()
        dialog.query.setText('Matching');dialog.actor.setEditText('Typed actor')
        release.set()
        deadline=time.monotonic()+5
        while window._auxiliary_jobs and time.monotonic()<deadline:
            loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
        assert dialog.actor.text()=='Typed actor' and dialog.actor.findText('Existing actor')>=0
        dialog.accept();qapp.processEvents()
        assert window.section=='recommend' and window.search.text()=='Matching'
        assert len(window.current_items)==1 and window.catalog_sort.isHidden()
        window.search.setText('Matching');window.search_all()
        assert window.section=='recommend'
    finally:
        release.set()
        if window._filter_dialog is not None:window._filter_dialog.reject()
        window.close()


def test_new_filter_supersedes_pending_history_scroll_restore(qapp,tmp_path,monkeypatch):
    from lumen import browse
    original=browse.load_view
    entered=threading.Event();release=threading.Event()
    monkeypatch.setattr(MainWindow,'synchronous_small_catalog',False)
    window=MainWindow(tmp_path/'restore-epoch');settle(qapp,window)
    window.navigate('recommend');settle(qapp,window)
    window.search_metadata('actor','Actor');settle(qapp,window)
    def slow(library,request):
        entered.set();release.wait(3);return original(library,request)
    monkeypatch.setattr(browse,'load_view',slow)
    try:
        window.back_navigation();assert entered.wait(2)
        assert window._restore_browse_state is not None
        window.filters={'query':'new result'};window.refresh()
        assert window._restore_browse_state is None and not window.cards.isEnabled()
        release.set();settle(qapp,window)
        assert window.section=='recommend' and window.cards.isEnabled()
    finally:
        release.set();settle(qapp,window);window.close()
