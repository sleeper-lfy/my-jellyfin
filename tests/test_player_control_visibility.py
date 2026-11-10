from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from lumen.player import Player


def test_video_click_toggles_controls_even_while_paused_and_movement_does_not_undo_it(qapp,library):
    library.set_setting('player_compat',True)
    player=Player(library);player.resize(900,540);player.show();qapp.processEvents()
    try:
        surface=player.canvas.viewport();point=QPoint(surface.width()//2,surface.height()//2)
        assert not player.header.isHidden()
        QTest.mouseClick(surface,Qt.MouseButton.LeftButton,pos=point);assert player.header.isHidden() and player.footer.isHidden()
        QTest.mouseMove(surface,point+QPoint(20,0));qapp.processEvents();player.check_pointer();assert player.header.isHidden()
        QTest.mouseClick(surface,Qt.MouseButton.LeftButton,pos=point);assert not player.header.isHidden() and not player.footer.isHidden()
        QTest.mouseClick(player.timeline,Qt.MouseButton.LeftButton);assert not player.header.isHidden()
    finally:player.close()
