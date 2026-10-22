"""Keep vertical wheel gestures on the page while hovering a horizontal gallery."""
from PySide6.QtCore import Qt,QPoint,QCoreApplication
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QScrollArea


def route_vertical_wheel(widget,event):
    delta=event.pixelDelta() if not event.pixelDelta().isNull() else event.angleDelta()
    if event.modifiers()&Qt.KeyboardModifier.ShiftModifier or not delta.y() or abs(delta.x())>abs(delta.y()):return False
    parent=widget.parentWidget()
    while parent is not None and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
    if parent is None:return False
    viewport=parent.viewport()
    local=viewport.mapFromGlobal(event.globalPosition().toPoint())
    forwarded=QWheelEvent(local,event.globalPosition(),QPoint(0,event.pixelDelta().y()),QPoint(0,event.angleDelta().y()),
                          event.buttons(),event.modifiers(),event.phase(),event.inverted(),event.source())
    QCoreApplication.sendEvent(viewport,forwarded)
    event.accept();return True
