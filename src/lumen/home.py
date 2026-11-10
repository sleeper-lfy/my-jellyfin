"""Jellyfin-style media shortcuts and horizontal rows, backed exclusively by the library."""
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QPainter, QPixmap, QColor, QLinearGradient, QFont
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QPushButton,QListWidget,QListWidgetItem,QAbstractItemView,QLabel,QSizePolicy


class MediaTile(QPushButton):
    def __init__(self, title, subtitle, cover, action):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.cover_path=cover
        from .images import image_cache
        image_cache().changed.connect(self.update)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumWidth(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(action)
        self.setAccessibleName(title)
        self.setToolTip(title)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(1, round((width-16) * 9 / 16)+90)

    def sizeHint(self):
        return QSize(280, 239)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),QColor('#181818'))
        from .images import image_cache
        cover=image_cache().request(self.cover_path,QSize(960,540))
        if not cover.isNull():
            artwork=QRect(8,8,self.width()-16,round((self.width()-16)*9/16))
            image=cover.scaled(artwork.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            painter.save();painter.setClipRect(artwork)
            painter.drawPixmap(artwork.x()+(artwork.width()-image.width())//2,artwork.y()+(artwork.height()-image.height())//2,image)
            painter.restore()
        shade=QLinearGradient(0,0,0,self.height()-70)
        shade.setColorAt(0,QColor(0,0,0,0))
        shade.setColorAt(1,QColor(0,0,0,35))
        painter.fillRect(self.rect(),shade)
        painter.setPen(QColor('white'))
        font=QFont('Segoe UI');font.setPixelSize(20);font.setWeight(QFont.Weight.DemiBold);painter.setFont(font)
        painter.drawText(self.rect().adjusted(12,0,-12,-32),Qt.AlignmentFlag.AlignBottom,self.title)
        painter.setFont(QFont('Segoe UI',10))
        painter.setPen(QColor('#cccccc'))
        painter.drawText(self.rect().adjusted(12,0,-12,-12),Qt.AlignmentFlag.AlignBottom,self.subtitle)
        if self.underMouse() or self.hasFocus():
            painter.setPen(QColor('#00a4dc'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1,1,-1,-1))


class MediaShortcuts(QScrollArea):
    """Large media cards wrap into rows instead of shrinking five into one strip."""
    def __init__(self,card_width=280):
        super().__init__();self.card_width=card_width;self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content=QWidget();self.row=QGridLayout(self.content)
        self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(12)
        self.tiles=[];self.setWidget(self.content);self.setFixedHeight(300)
    def add_tile(self,tile):
        self.tiles.append(tile);self.reflow()
    def reflow(self):
        available=max(1,self.viewport().width());count=len(self.tiles)
        width=min(available,max(160,int(self.card_width)));columns=max(1,min(max(1,count),(available+12)//(width+12)))
        height=round((width-16)*9/16)+90
        while self.row.count():self.row.takeAt(0)
        for index,tile in enumerate(self.tiles):
            tile.setFixedSize(width,height);self.row.addWidget(tile,index//columns,index%columns)
        rows=(count+columns-1)//columns
        total=rows*height+max(0,rows-1)*12+4
        self.content.setMinimumHeight(total-4)
        if self.height()!=total:self.setFixedHeight(total)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()


class HomePage(QScrollArea):
    def __init__(self,window):
        super().__init__()
        from .ui import label,button,PosterList,PosterDelegate
        self.window=window
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content=QWidget();self.layout=QVBoxLayout(self.content)
        self.layout.setContentsMargins(0,0,12,0);self.layout.setSpacing(12)
        self.setWidget(self.content);self.rows=[];self.tiles={};self.sections={}
        self.layout.addWidget(label('我的媒体','sectionTitle'))
        self.shortcuts=MediaShortcuts(window.library.setting("thumbnail_width",280));tiles=self.shortcuts.row
        for kind,title in [('movie','电影'),('series','电视剧'),('vr','VR电影'),('fans','Fans'),('other','其他视频')]:
            tile=MediaTile(title,'0 位作者' if kind=='fans' else '0 部作品',None,lambda checked=False,kind=kind:window.navigate(kind))
            self.tiles[kind]=tile;self.shortcuts.add_tile(tile)
        self.layout.addWidget(self.shortcuts)
        for title in ['继续观看','最新电影','最新电视剧','最新VR电影','最新Fans作者','为你推荐']:
            heading=label(title,'sectionTitle')
            if title=='为你推荐':
                heading_row=QWidget();row=QHBoxLayout(heading_row);row.setContentsMargins(0,0,0,0);row.addWidget(heading,1)
                row.addWidget(button('查看全部推荐',lambda:window.navigate('recommend')));heading=heading_row
            self.layout.addWidget(heading)
            cards=PosterList(window.play_work)
            cards.favoriteRequested.connect(window.toggle_favorite)
            cards.watchlistRequested.connect(lambda work_id:window.toggle_card_personal(work_id,'watchlist'))
            cards.setObjectName('posters');cards.setViewMode(QListWidget.ViewMode.IconMode);cards.setFlow(QListWidget.Flow.LeftToRight)
            cards.setWrapping(False);cards.setResizeMode(QListWidget.ResizeMode.Adjust);cards.setMovement(QListWidget.Movement.Static);cards.viewport().setAcceptDrops(True)
            cards.setMouseTracking(True);cards.setItemDelegate(PosterDelegate(cards));cards.setSpacing(2)
            cards.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            cards.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);cards.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);cards.customContextMenuRequested.connect(lambda point,cards=cards:window.card_menu(point,cards))
            cards.itemClicked.connect(window.open_item);self.layout.addWidget(cards);self.sections[title]=(heading,cards)
        self.empty=QWidget();empty_layout=QVBoxLayout(self.empty)
        message=label('开始建立你的媒体库\n添加电影、电视剧或视频文件夹，封面和观看记录将在这里显示。')
        message.setAlignment(Qt.AlignmentFlag.AlignCenter);message.setMinimumHeight(210);message.setStyleSheet('color: #aaaaaa; font-size: 16px;')
        empty_layout.addWidget(message);row=QHBoxLayout();row.addStretch();row.addWidget(button('添加媒体文件夹',window.import_dialog,True));row.addStretch();empty_layout.addLayout(row)
        self.layout.addWidget(self.empty);self.layout.addStretch()

    def refresh(self,works=None,recommendations=None):
        from .ui import update_poster_items
        if works is None:
            from .continuation import continue_works
            continuing={item['id']:item for item in continue_works(self.window.library)}
            works=[continuing.get(item['id'],item) for item in self.window.library.query()]
        self.shortcuts.card_width=self.window.library.setting("thumbnail_width",280);self.shortcuts.reflow()
        position=self.verticalScrollBar().value()
        for kind,tile in self.tiles.items():
            items=[work for work in works if work['kind']==kind];cover=None
            for work in items[:24]:
                record=self.window.card_data(work,True);cover=record.get('_cover') or record.get('thumbnail')
                if cover:break
            tile.subtitle=f'{len(items)} 位作者' if kind=='fans' else f'{len(items)} 部作品';tile.cover_path=cover;tile.update()
        continuing=sorted([work for work in works if work.get('_resume')],key=lambda work:(work.get('_last_played',''),work['id']),reverse=True)
        if recommendations is None:recommendations=self.window.library.recommendations()
        sections=[('继续观看',continuing,True),('最新电影',[work for work in works if work['kind']=='movie'],False),
                  ('最新电视剧',[work for work in works if work['kind']=='series'],False),('最新VR电影',[work for work in works if work['kind']=='vr'],False),('最新Fans作者',[work for work in works if work['kind']=='fans'],False),('为你推荐',recommendations,False)]
        self.rows=[]
        for title,items,landscape in sections:
            heading,cards=self.sections[title];landscape=landscape or self.window.view_mode.currentData()=='thumbnail'
            width=self.window.library.setting('thumbnail_width' if landscape else 'poster_width',280 if landscape else 190)
            cards.setFixedHeight(round((width-16)*(9/16 if landscape else 3/2))+114)
            records=[self.window.card_data(work,landscape) for work in items[:24]]
            update_poster_items(cards,records)
            if title=='继续观看':
                for index,work in enumerate(items[:24]):cards.item(index).setToolTip(work['_resume']['label'])
            heading.setVisible(bool(items));cards.setVisible(bool(items))
            if items:self.rows.append(cards)
        self.empty.setVisible(not works);self.layout.activate();self.verticalScrollBar().setValue(position)
