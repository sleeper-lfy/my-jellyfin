"""Shared media-library controls: vector icons, stateful actions and wrapping chips."""
from functools import lru_cache
from PySide6.QtCore import Qt,QSize,QRect,QPoint,QByteArray
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton,QLayout,QSizePolicy,QLabel
from PySide6.QtGui import QPalette


class ElidedLabel(QLabel):
    """Single-line status text never changes the surrounding layout."""
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(28)
    def setText(self,text):
        super().setText(text);self.setToolTip(text)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text=self.fontMetrics().elidedText(self.text().replace('\n',' '),Qt.TextElideMode.ElideMiddle,self.contentsRect().width())
        painter.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)

PATHS={
    'heart':'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z',
    'bookmark':'M6 3h12v18l-6-4-6 4V3Z',
    'star':'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z',
    'filter':'M4 6h16M7 12h10M10 18h4',
    'close':'m6 6 12 12M6 18 18 6',
    'more':'M5 12h.01M12 12h.01M19 12h.01',
    'play':'m8 5 11 7-11 7V5Z',
    'check':'m5 12 4 4L19 6',
    'chevron':'m6 9 6 6 6-6',
    'back':'m14 5-7 7 7 7M7 12h14',
    'search':'M21 21 16 16M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
    'shuffle':'m16 3 4 4-4 4M4 17 14 7h6M4 7h3l10 10h3m-4-4 4 4-4 4',
    'settings':'M20.00 12.00L21.81 13.95L21.24 15.83L18.65 16.44L17.66 17.66L17.56 20.31L15.83 21.24L13.56 19.85L12.00 20.00L10.05 21.81L8.17 21.24L7.56 18.65L6.34 17.66L3.69 17.56L2.76 15.83L4.15 13.56L4.00 12.00L2.19 10.05L2.76 8.17L5.35 7.56L6.34 6.34L6.44 3.69L8.17 2.76L10.44 4.15L12.00 4.00L13.95 2.19L15.83 2.76L16.44 5.35L17.66 6.34L20.31 6.44L21.24 8.17L19.85 10.44Z M16 12a4 4 0 1 0-8 0 4 4 0 0 0 8 0',
    'folder':'M3 6h7l2 2h9v12H3V6Z',
    'plus':'M12 5v14M5 12h14',
    'ban':'M5 5l14 14M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
}


@lru_cache(maxsize=128)
def icon(name,color='#dedee3',filled=False):
    fill=color if filled else 'none'
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="{PATHS[name]}" fill="{fill}" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    pixmap=QPixmap(48,48);pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap);QSvgRenderer(QByteArray(svg.encode())).render(painter);painter.end()
    return QIcon(pixmap)


class ActionButton(QPushButton):
    def __init__(self,text,name,callback=None,*,checked=None,accent='#00a4dc',parent=None):
        super().__init__(text,parent)
        self.symbol,self.accent=name,accent
        self.setObjectName('stateAction' if checked is not None else 'quietAction')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40);self.setIconSize(QSize(20,20));self.setAccessibleName(text)
        if checked is not None:
            self.setCheckable(True);self.setChecked(checked)
            self.toggled.connect(self.update_icon)
        self.update_icon()
        if callback:self.clicked.connect(callback)

    def update_icon(self,*_):
        active=self.isCheckable() and self.isChecked()
        self.setIcon(icon(self.symbol,self.accent if active else '#dedee3',active and self.symbol in {'heart','bookmark','star'}))
        self.setAccessibleDescription('已选中' if active else '未选中' if self.isCheckable() else '')

    def icon_only(self,tip=None):
        self.setToolTip(tip or self.text());self.setText('');self.setFixedSize(40,40)
        return self


class FlowLayout(QLayout):
    def __init__(self,parent=None,spacing=6):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,False)
    def sizeHint(self):return self.minimumSize()
    def minimumSize(self):
        size=QSize()
        for item in self.items:
            if not item.isEmpty():size=size.expandedTo(item.minimumSize())
        return size
    def arrange(self,rect,test):
        x,y,height=rect.x(),rect.y(),0
        for item in self.items:
            if item.isEmpty():continue
            size=item.sizeHint();width=min(size.width(),max(0,rect.width()))
            if x>rect.x() and x+width>rect.right()+1:x=rect.x();y+=height+self.spacing();height=0
            if not test:item.setGeometry(QRect(QPoint(x,y),QSize(width,size.height())))
            x+=width+self.spacing();height=max(height,size.height())
        return y+height-rect.y()


def chip(text,callback=None,removable=False):
    control=QPushButton(text)
    control.setObjectName('filterChip' if removable else 'metadataChip')
    control.setCursor(Qt.CursorShape.PointingHandCursor)
    control.setToolTip(text);control.setMaximumWidth(260);control.setMinimumHeight(30)
    control.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
    if removable:control.setIcon(icon('close','#b8cbd2'));control.setIconSize(QSize(13,13));control.setAccessibleName('移除筛选：'+text)
    if callback:control.clicked.connect(callback)
    return control
