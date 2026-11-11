from types import SimpleNamespace

from PySide6.QtCore import QObject,Signal,Qt,QPoint
from PySide6.QtTest import QTest

from lumen import updates
from lumen.updates_ui import UpdatePanel


class Controller(QObject):
    changed=Signal(object)

    def __init__(self,library):
        super().__init__();self.window=SimpleNamespace(library=library);self.candidate=None

    def state(self):
        return dict(message='',progress=0,busy=False,downloading=False,candidate=self.candidate is not None,staged=False,notes='')

    def check(self):pass
    def download(self):pass
    def install(self):pass
    def cancel(self):pass
    def option(self,key,value):pass


def click_channel(panel):
    label=panel.channel
    x=label.fontMetrics().horizontalAdvance('更新渠道：')+label.fontMetrics().horizontalAdvance('GitHub Releases')//2
    QTest.mouseClick(label,Qt.MouseButton.LeftButton,pos=QPoint(x,label.height()//2))


def test_update_channel_opens_public_releases_without_a_candidate(qapp,library,monkeypatch):
    opened=[];monkeypatch.setattr('lumen.updates_ui.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    controller=Controller(library);panel=UpdatePanel(controller);panel.resize(650,560);panel.show();qapp.processEvents()
    try:
        click_channel(panel)
        assert opened==[f'https://github.com/{updates.REPO}/releases']
        assert panel.channel.focusPolicy()==Qt.FocusPolicy.StrongFocus
        assert panel.channel.textInteractionFlags()&Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        assert '更新渠道' in panel.channel.accessibleName()
    finally:panel.close()


def test_update_channel_follows_candidate_and_returns_to_release_list(qapp,library,monkeypatch):
    opened=[];monkeypatch.setattr('lumen.updates_ui.QDesktopServices.openUrl',lambda url:opened.append(url.toString()) or True)
    controller=Controller(library);panel=UpdatePanel(controller);panel.resize(650,560);panel.show()
    try:
        controller.candidate=updates.Candidate('0.4.21',updates.release_url(updates.INSTALLER,'v0.4.21'),4096,'a'*64)
        controller.changed.emit(controller.state());qapp.processEvents();click_channel(panel)
        assert opened==[f'https://github.com/{updates.REPO}/releases/tag/v0.4.21']
        assert '0.4.21' in panel.channel.accessibleName()
        controller.candidate=None;controller.changed.emit(controller.state());qapp.processEvents();click_channel(panel)
        assert opened[-1]==f'https://github.com/{updates.REPO}/releases'
    finally:panel.close()
