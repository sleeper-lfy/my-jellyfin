"""Exercise responsive layouts and the scope of the desktop navigation actions."""
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QPushButton,QMessageBox
from lumen.ui import MainWindow
from test_core import add_work


def settle(app):
    for _ in range(6):app.processEvents()


def actions(menu):
    result=[]
    for action in menu.actions():
        result.append(action.text())
        if action.menu():result.extend(actions(action.menu()))
    return result


def test_narrow_desktop_keeps_controls_readable_and_detail_actions_inside_viewport(qapp,tmp_path):
    window=MainWindow(tmp_path/'responsive')
    identifier=add_work(window.library,'长标题验证：从海岸到森林的旅程与那些尚未讲完的故事',metadata={
        'overview':'沿着海岸穿过清晨港口，寻找风景与日常的故事。'*30,
        'tags':['纪录片','自然风光','旅行','四季变化','独立摄影','海岸线','森林','更多标签'],
        'actors':[{'name':'演员姓名测试'+str(i),'gender':'female'} for i in range(12)]})
    try:
        window.library.set_setting('poster_width',300)
        window.resize(1024,700);window.show();window.navigate('movie');settle(qapp)
        assert window.drawer.isVisible() and not window.job_area.isVisible()
        for index in range(window.toolbar.count()):
            control=window.toolbar.itemAt(index).widget()
            if control and control.isVisible():
                assert control.width()>=control.minimumSizeHint().width()
                assert control.geometry().right()<=window.browse_page.width()
        window.open_details(identifier,fetch=False);settle(qapp)
        page=window.detail_page;scroll=window.details_scroll
        assert scroll.horizontalScrollBar().maximum()==0
        for control in (page.favorite_action,page.watchlist_action,page.rating_action):
            right=control.mapTo(page,QPoint(control.width(),0)).x()
            assert right<=scroll.viewport().width()
        assert page.files_heading.y()<page.actor_links.y()
        assert page.layout().indexOf(page.files)<page.layout().indexOf(page.gallery_heading)
        assert page.files_heading.y()<scroll.viewport().height()
        assert page.poster.width()<=210
        assert any(button.text()=='展开简介' for button in page.findChildren(QPushButton))
        assert any('展开全部 12 位演员'==button.text() for button in page.findChildren(QPushButton))
    finally:window.close()


def test_detail_menu_scope_and_named_queue_entry(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'scope');identifier=add_work(window.library,'Scope')
    seen=[];monkeypatch.setattr('lumen.catalog_ui.queue_editor',lambda parent:seen.append('queue'))
    try:
        window.show();window.open_details(identifier,fetch=False);settle(qapp)
        menu=window.detail_page.management_menu
        assert [action.text() for action in menu.actions() if action.menu()]==['播放与观看','资料与图片','文件与版本']
        text=actions(menu)
        assert '版本对比 / 默认播放…' in text and '导出 NFO 与图片…' in text
        assert '图片大小…' not in text and '全局显示大小…' not in text
        queue=next(button for button in window.findChildren(QPushButton) if button.accessibleName()=='电脑播放队列')
        queue.click();assert seen==['queue']
        notified=[];monkeypatch.setattr(QMessageBox,'information',lambda *args:notified.append(args[2]))
        window.export_nfo();assert notified and '当前影片' in notified[0]
    finally:window.close()


def test_personal_navigation_and_batch_export_have_explicit_targets(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'personal');a=add_work(window.library,'First');b=add_work(window.library,'Second')
    window.library.update_personal(a,watchlist=True);window.library.update_personal(b,favorite=True)
    try:
        window.show();window.open_watchlist();settle(qapp)
        assert [item['id'] for item in window.current_items]==[a]
        assert window.nav_buttons['watchlist'].isChecked()
        window.open_favorites();assert [item['id'] for item in window.current_items]==[b]
        window.navigate('movie');settle(qapp)
        assert not window.batch_bar.isVisible()
        window.batch_select.setChecked(True);settle(qapp)
        assert window.batch_bar.isVisible() and not window.batch_export.isEnabled()
        window.cards.item(0).setSelected(True);settle(qapp)
        target=window.cards.item(0).data(Qt.ItemDataRole.UserRole)['id'];exports=[]
        monkeypatch.setattr(window,'export_nfo',lambda ids:exports.append(ids))
        window.batch_export.click();assert exports==[[target]] and window.batch_count.text()=='已选 1 部'
        window.navigate('series');settle(qapp)
        assert not window.batch_select.isChecked() and not window.batch_bar.isVisible() and window.drawer.isVisible()
    finally:window.close()


def test_home_categories_keep_readable_width_and_continue_is_first(qapp,tmp_path):
    window=MainWindow(tmp_path/'home');add_work(window.library,'Category sample')
    try:
        window.resize(1024,700);window.show();window.navigate('home');settle(qapp)
        assert all(tile.width()>=160 for tile in window.home_page.tiles.values())
        assert window.home_page.layout.itemAt(0).widget() is window.home_page.sections['继续观看'][0]
        assert not window.view_mode.isVisible()
    finally:window.close()


def test_saved_list_restores_sort_controls_and_first_toggle_preserves_scope(qapp,tmp_path,monkeypatch):
    import json
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QListWidget
    window=MainWindow(tmp_path/'list-sort')
    a=add_work(window.library,'Alpha',metadata={'tags':['keep']});b=add_work(window.library,'Bravo',metadata={'tags':['keep']})
    add_work(window.library,'Outside',metadata={'tags':['outside']})
    for identifier in (a,b):window.library.update_personal(identifier,favorite=True)
    saved={'kinds':['movie'],'tags_all':['keep'],'favorite':True,'sort':'title','descending':False}
    with window.library.db:window.library.db.execute('INSERT INTO lists VALUES (?,?)',('Saved scope',json.dumps(saved)))
    played=[];monkeypatch.setattr(window,'play_work',lambda work_id,random=False:played.append(work_id))
    try:
        window.show()
        def choose():
            dialog=qapp.activeModalWidget();choices=dialog.findChild(QListWidget,'smartListChoices');choices.setCurrentRow(0)
            dialog.findChild(QPushButton,'openSmartList').click()
        QTimer.singleShot(0,choose);window.load_list();settle(qapp)
        assert [item['id'] for item in window.current_items]==[a,b]
        assert window.catalog_sort.currentData()=='title' and window.catalog_direction.text()=='升序'
        window.flip_catalog_sort();settle(qapp)
        assert [item['id'] for item in window.current_items]==[b,a]
        assert window.catalog_direction.text()=='降序'
        window.catalog_sort.setCurrentIndex(window.catalog_sort.findData('year'));settle(qapp)
        assert window.filters['tags_all']==['keep'] and window.filters['favorite']
        window.shuffle();assert set(window.library.setting('queue')['ids'])=={a,b} and played
        assert json.loads(window.library.db.execute('SELECT filters FROM lists').fetchone()[0])==saved
    finally:window.close()


def test_random_list_uses_complete_results_beyond_rendered_page(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'all-results')
    wanted={add_work(window.library,f'Movie {i:03}',metadata={'tags':['included']}) for i in range(75)}
    for i in range(5):add_work(window.library,f'Outside {i}',metadata={'tags':['outside']})
    monkeypatch.setattr(window,'play_work',lambda *args,**kwargs:None)
    try:
        window.show();window.navigate('movie');window.filters={'tags_all':['included']};window.refresh();settle(qapp)
        assert len(window.current_items)==75 and window.cards.count()==60
        window.shuffle();assert set(window.library.setting('queue')['ids'])==wanted
        assert window.library.setting('queue')['filters']['tags_all']==['included']
    finally:window.close()


def test_random_recommendations_and_continue_match_visible_result_scope(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'derived-scope')
    a=add_work(window.library,'Allowed one');b=add_work(window.library,'Allowed two')
    disliked=add_work(window.library,'Disliked');window.library.update_personal(disliked,disliked=True)
    add_work(window.library,'Other video',kind='other');add_work(window.library,'Author',kind='fans')
    monkeypatch.setattr(window,'play_work',lambda *args,**kwargs:None)
    try:
        window.show();window.navigate('recommend');settle(qapp)
        assert {item['id'] for item in window.current_items}=={a,b}
        window.shuffle();assert set(window.library.setting('queue')['ids'])=={a,b}
        series=add_work(window.library,'Next episode',kind='series')
        movie_path=tmp_path/'resuming.mp4';movie_path.write_bytes(b'fixture')
        first=tmp_path/'episode-one.mp4';first.write_bytes(b'fixture')
        second=tmp_path/'episode-two.mp4';second.write_bytes(b'fixture')
        with window.library.db:
            window.library.db.execute('UPDATE files SET path=?,position=100 WHERE work_id=?',(str(movie_path),a))
            window.library.db.execute('UPDATE files SET path=?,completed=1 WHERE work_id=?',(str(first),series))
            window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',
                (series,str(second),'second-episode',str(tmp_path),1000,1,2))
        window.navigate('home');window.tabs.setCurrentIndex(1);settle(qapp)
        assert {item['id'] for item in window.current_items}=={a,series}
        window.shuffle();assert set(window.library.setting('queue')['ids'])=={a,series}
    finally:window.close()


def test_filtering_continue_keeps_resume_scope_and_unstarted_next_episode(qapp,tmp_path):
    import time
    from PySide6.QtTest import QTest
    window=MainWindow(tmp_path/'continue-filter')
    resuming=add_work(window.library,'Resume',metadata={'tags':['Keep']})
    fresh=add_work(window.library,'Not started',metadata={'tags':['Keep']})
    outside=add_work(window.library,'Other resume',metadata={'tags':['Other']})
    series=add_work(window.library,'Series next',kind='series',metadata={'tags':['Keep']})
    try:
        with window.library.db:
            for identifier in (resuming,fresh,outside,series):
                path=tmp_path/f'{identifier}.mp4';path.write_bytes(b'fixture')
                window.library.db.execute('UPDATE files SET path=?,position=?,completed=? WHERE work_id=?',
                    (str(path),100 if identifier in (resuming,outside) else 0,int(identifier==series),identifier))
            next_path=tmp_path/'next.mp4';next_path.write_bytes(b'fixture')
            window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',
                (series,str(next_path),'scope-next',str(tmp_path),1000,1,2))
        window.show();window.navigate('home');window.tabs.setCurrentIndex(1);settle(qapp)
        assert {item['id'] for item in window.current_items}=={resuming,outside,series}
        window.filter_dialog();dialog=window._filter_dialog
        dialog.fields['tags_all'].setEditText('Keep');dialog.accept();settle(qapp)
        assert window.section=='home' and window.subtab==1
        assert {item['id'] for item in window.current_items}=={resuming,series}
        assert window.effective_filters()['continue'] and window.filters['tags_all']==['Keep']
        deadline=time.monotonic()+5
        while window._auxiliary_jobs and time.monotonic()<deadline:QTest.qWait(10)
        assert not window._auxiliary_jobs
    finally:window.close()
