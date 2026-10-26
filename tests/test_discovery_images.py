"""Visible-only cover downloads must not block or replace another browse page."""
import threading
import time

import pytest
from PySide6.QtCore import QEventLoop,QTimer,QSize,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QListWidget,QListWidgetItem,QAbstractItemView

from lumen import discovery_images


def spin(app,ms=25):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec();app.processEvents()


def until(app,predicate,seconds=6):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:spin(app)
    assert predicate()


@pytest.fixture
def view(qapp,library):
    window=QWidget();window.resize(540,410)
    window.library=library;window.section='discover';window._closing=False
    window._browse_epoch=1;window._rendered_view_key='initial';window.current_items=[]
    layout=QVBoxLayout(window);window.cards=QListWidget();layout.addWidget(window.cards)
    cards=window.cards;cards.setViewMode(QListWidget.ViewMode.IconMode)
    cards.setResizeMode(QListWidget.ResizeMode.Adjust);cards.setMovement(QListWidget.Movement.Static)
    cards.setUniformItemSizes(True);cards.setSpacing(4)
    cards.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    for index in range(160):
        record={'id':index+1,'kind':'movie','title':str(index+1),'files':[],'thumbnail':None}
        item=QListWidgetItem(record['title']);item.setSizeHint(QSize(120,150));item.setData(Qt.ItemDataRole.UserRole,record);cards.addItem(item)
        window.current_items.append(dict(record))
    window.show();spin(qapp)
    controller=discovery_images.DiscoveryImages(window)
    yield window,controller
    controller.stop();until(qapp,lambda:controller.idle)
    window.close();window.deleteLater();spin(qapp)


def all_visible_ids(cards):
    return {cards.item(index).data(Qt.ItemDataRole.UserRole)['id'] for index in range(cards.count())
            if cards.visualItemRect(cards.item(index)).intersects(cards.viewport().rect())}


def test_visible_grid_lookup_handles_deep_scroll_without_enumerating_full_catalog(qapp,view):
    window,controller=view;cards=window.cards
    for index in (0,37,85,155):
        cards.scrollToItem(cards.item(index),QAbstractItemView.ScrollHint.PositionAtTop);spin(qapp)
        expected=all_visible_ids(cards)
        actual={item.data(Qt.ItemDataRole.UserRole)['id'] for item in discovery_images.visible_items(cards)}
        assert actual==expected
        assert len(actual)<25


def test_slow_visible_downloads_are_bounded_and_gui_ticks_while_scrolling(qapp,view,monkeypatch):
    window,controller=view;cards=window.cards;release=threading.Event();calls=[]
    def slow(library,work_id):
        assert threading.current_thread() is not threading.main_thread()
        calls.append(work_id);release.wait(5)
        return str(library.directory/'cache'/f'{work_id}.jpg')
    monkeypatch.setattr(discovery_images,'cache_discovery_cover',slow)
    initial=all_visible_ids(cards);ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    try:
        controller.refresh_visible();until(qapp,lambda:len(calls)==3);spin(qapp,100)
        assert len(ticks)>=5 and len(controller.active)==3
        assert len(controller.pending)<=12 and set(calls)<=initial
        first_calls=set(calls)
        cards.scrollToItem(cards.item(110),QAbstractItemView.ScrollHint.PositionAtTop);spin(qapp)
        later=all_visible_ids(cards);controller.refresh_visible();spin(qapp)
        release.set()
        until(qapp,lambda:all(cards.item(index).data(Qt.ItemDataRole.UserRole).get('thumbnail')
                              for index in range(cards.count()) if cards.item(index).data(Qt.ItemDataRole.UserRole)['id'] in later))
        assert set(calls)-first_calls<=later
        assert len(controller.pending)<=12 and cards.count()==160
    finally:timer.stop();release.set()


def test_page_generation_rejects_old_callbacks_and_only_updates_current_card(qapp,view,monkeypatch):
    window,controller=view;cards=window.cards;release=threading.Event();entered=threading.Event()
    def slow(library,work_id):
        entered.set();release.wait(5);return '/old-page-cover.jpg'
    monkeypatch.setattr(discovery_images,'cache_discovery_cover',slow)
    try:
        controller.refresh_visible();until(qapp,entered.is_set)
        old_generation=controller.generation
        window._browse_epoch+=1;window._rendered_view_key='replacement'
        cards.clear();replacement={'id':1,'kind':'movie','title':'Replacement','files':[],'thumbnail':'/new-cover.jpg','_cover':'/new-cover.jpg'}
        item=QListWidgetItem('Replacement');item.setSizeHint(QSize(120,150));item.setData(Qt.ItemDataRole.UserRole,replacement);cards.addItem(item)
        window.current_items=[dict(replacement)];controller.refresh_visible()
        assert controller.generation>old_generation
        release.set();until(qapp,lambda:controller.idle);spin(qapp)
        assert cards.item(0) is item and item.data(Qt.ItemDataRole.UserRole)==replacement
        assert window.current_items[0]['thumbnail']=='/new-cover.jpg'
    finally:release.set()


def test_local_cards_are_never_requested_and_stopping_can_resume(qapp,view,monkeypatch):
    window,controller=view;cards=window.cards;calls=[]
    for index in range(cards.count()):
        item=cards.item(index);record=item.data(Qt.ItemDataRole.UserRole)
        record['files']=[{'id':index+1}];item.setData(Qt.ItemDataRole.UserRole,record)
    monkeypatch.setattr(discovery_images,'cache_discovery_cover',lambda library,work_id:calls.append(work_id))
    controller.refresh_visible();spin(qapp,70);assert not calls and controller.idle
    controller.stop();window.section='movie';controller.refresh_visible();spin(qapp);assert not calls
    window.section='discover';controller.resume();spin(qapp);assert not calls and not controller.stopped
