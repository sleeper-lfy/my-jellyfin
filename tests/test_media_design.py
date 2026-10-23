import time
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton,QMenu
from lumen.ui import MainWindow,FilterDialog,poster_regions
from test_core import add_work


def test_card_favorite_and_watchlist_are_independent_and_do_not_navigate(qapp,tmp_path):
    window=MainWindow(tmp_path/'cards')
    for i in range(50):add_work(window.library,f'Movie {i}')
    window.resize(1280,800);window.show();window.navigate('movie');qapp.processEvents()
    item=window.cards.item(10);window.cards.scrollToItem(item);qapp.processEvents()
    position=window.cards.verticalScrollBar().value();data=item.data(Qt.ItemDataRole.UserRole)
    played=[];opened=[];window.cards.play=played.append;window.open_details=lambda work_id,**kwargs:opened.append(work_id)
    _,areas=poster_regions(window.cards.visualItemRect(item))
    QTest.mouseClick(window.cards.viewport(),Qt.MouseButton.LeftButton,pos=areas['favorite'].center())
    assert window.library.work(data['id'])['favorite']==1
    assert window.cards.verticalScrollBar().value()==position and window.detail_page is None
    QTest.mouseClick(window.cards.viewport(),Qt.MouseButton.LeftButton,pos=areas['watchlist'].center())
    assert window.library.work(data['id'])['watchlist']==1 and not played and not opened
    assert item.data(Qt.ItemDataRole.UserRole)['favorite']==1
    QTest.mouseClick(window.cards.viewport(),Qt.MouseButton.LeftButton,pos=areas['favorite'].center())
    assert window.library.work(data['id'])['favorite']==0 and window.library.work(data['id'])['watchlist']==1
    window.close()


def test_unfavorite_in_collection_removes_only_that_card(qapp,tmp_path):
    window=MainWindow(tmp_path/'collection')
    ids=[add_work(window.library,f'Favorite {i}') for i in range(3)]
    for work_id in ids:window.library.update_personal(work_id,favorite=True)
    window.show();window.open_favorites();qapp.processEvents()
    item=window.cards.item(1);work_id=item.data(Qt.ItemDataRole.UserRole)['id']
    _,areas=poster_regions(window.cards.visualItemRect(item))
    QTest.mouseClick(window.cards.viewport(),Qt.MouseButton.LeftButton,pos=areas['favorite'].center())
    assert window.cards.count()==2 and {work['id'] for work in window.current_items}==set(ids)-{work_id}
    assert window.library.work(work_id)['favorite']==0
    window.close()


def test_detail_state_changes_keep_page_and_scroll_and_rating_menu_works(qapp,tmp_path):
    window=MainWindow(tmp_path/'detail');work_id=add_work(window.library,'Detail actions')
    window.show();window.open_details(work_id,fetch=False);qapp.processEvents()
    page=window.detail_page;scroll=window.details_scroll;scroll.verticalScrollBar().setValue(100);position=scroll.verticalScrollBar().value()
    QTest.mouseClick(page.favorite_action,Qt.MouseButton.LeftButton)
    QTest.mouseClick(page.watchlist_action,Qt.MouseButton.LeftButton)
    assert window.detail_page is page and scroll.verticalScrollBar().value()==position
    assert page.favorite_action.isChecked() and page.favorite_action.text()=='已收藏'
    assert page.watchlist_action.isChecked() and page.watchlist_action.text()=='已想看'
    def choose():
        menu=qapp.activePopupWidget()
        assert isinstance(menu,QMenu)
        next(action for action in menu.actions() if action.text().endswith('9 分')).trigger();menu.close()
    QTimer.singleShot(30,choose);page.rating_action.click()
    assert window.library.work(work_id)['rating']==9 and page.rating_action.text()=='9 分'
    assert window.detail_page is page
    window.close()


def test_filter_dropdown_adds_multiple_tags_without_manual_comma(qapp):
    dialog=FilterDialog({},options={'tags':['Drama','Travel'],'actors':['Actor'],'years':[2024]});dialog.show();qapp.processEvents()
    field=dialog.fields['tags_all']
    for value in ['Drama','Travel']:
        field.showPopup();field.view().setCurrentIndex(field.model().index(field.findText(value),0))
        QTest.keyClick(field.view(),Qt.Key.Key_Return);qapp.processEvents()
    assert dialog.filters()['tags_all']==['Drama','Travel']
    buttons=[button for button in dialog.selected_tags.findChildren(QPushButton) if button.isVisible()]
    QTest.mouseClick(next(button for button in buttons if button.text()=='Drama'),Qt.MouseButton.LeftButton)
    assert dialog.filters()['tags_all']==['Travel']
    dialog.close()


def test_filter_reset_and_cancel_leave_applied_filters_untouched(qapp,tmp_path):
    window=MainWindow(tmp_path/'draft');window.filters={'tags_all':['Drama'],'actor':'Actor','rating_min':8,'watchlist':True}
    original=dict(window.filters);dialog=FilterDialog(window.filters,window,{'tags':['Drama'],'actors':['Actor']});dialog.show();qapp.processEvents()
    assert dialog.advanced.isVisible()
    dialog.reset();result=dialog.filters()
    assert not result['tags_all'] and not result['actor'] and 'rating_min' not in result and 'watchlist' not in result
    dialog.reject();assert window.filters==original
    window.close()


def test_applied_filter_chips_remove_one_condition_without_clearing_others(qapp,tmp_path):
    window=MainWindow(tmp_path/'chips');add_work(window.library,'Selected',metadata={'tags':['Drama'],'actors':[{'name':'Actor'}]})
    window.navigate('home');window.tabs.setCurrentIndex(2)
    window.filters={'tags_all':['Drama'],'actor':'Actor','year_min':2024,'year_max':2024};window.show();window.refresh();qapp.processEvents()
    control=next(button for button in window.filter_chips.findChildren(QPushButton) if button.accessibleName()=='移除筛选：Drama')
    QTest.mouseClick(control,Qt.MouseButton.LeftButton)
    assert 'tags_all' not in window.filters and window.filters['actor']=='Actor' and window.filters['year_min']==2024
    assert window.filter_control.text()=='筛选 · 2'
    window.close()


def test_compact_and_ultrawide_details_keep_primary_actions_in_view(qapp,tmp_path):
    window=MainWindow(tmp_path/'sizes');work_id=add_work(window.library,'A long title ' * 8,metadata={'tags':['Tag '+str(i) for i in range(12)],'actors':[{'name':'Actor'}]})
    window.show();window.open_details(work_id,fetch=False)
    for width,height in [(1024,700),(1280,900),(2560,1080)]:
        window.resize(width,height);qapp.processEvents();page=window.detail_page
        assert page.width()<=window.details_scroll.viewport().width()
        for control in [page.favorite_action,page.watchlist_action,page.rating_action]:
            left=control.mapTo(page,QPoint(0,0));assert left.x()>=0 and left.x()+control.width()<=page.width()
            assert control.width()>30 and control.height()>=40
    window.close()


def test_discovery_filters_apply_to_metadata_only_candidates(library):
    from lumen.browse import load_view
    selected=add_work(library,'Selected discovery',local=False,metadata={'tags':['Drama'],'actors':[{'name':'Actor'}]})
    add_work(library,'Another discovery',local=False,metadata={'tags':['Comedy'],'actors':[{'name':'Actor'}]})
    request={'section':'discover','tab':1,'filters':{'tags_all':['Drama'],'actor':'Actor','year_min':2024,'year_max':2024}}
    result=load_view(library,request)
    assert [work['id'] for work in result['items']]==[selected]
