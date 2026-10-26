"""Visible discovery controls, with separate local and provider searches."""
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QPushButton,QInputDialog
from .plugins import Plugins


class DiscoveryPanel(QWidget):
    siteFinished=Signal(int)
    siteFailed=Signal(int,str)

    def __init__(self,window):
        super().__init__(window);self._window=window;self.mode='local';self.applied_tag='';self.token=0
        from .ui import FilterCombo
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        fields=QHBoxLayout();fields.setSpacing(10);layout.addLayout(fields)
        self.name=QLineEdit();self.name.setObjectName('discoveryName');self.name.setPlaceholderText('按影片名称搜索');self.name.setClearButtonEnabled(True)
        self.tag=FilterCombo([]);self.tag.setObjectName('discoveryTag');self.tag.setMinimumWidth(160);self.tag.lineEdit().setPlaceholderText('标签，可输入关键词')
        for caption,control,stretch in [('名称',self.name,2),('标签',self.tag,1),('来源',window.source_filter,1)]:
            fields.addWidget(QLabel(caption));fields.addWidget(control,stretch)
        actions=QHBoxLayout();actions.setSpacing(10);layout.addLayout(actions)
        self.local=QPushButton('筛选已发现');self.local.setObjectName('discoveryLocalSearch');self.local.clicked.connect(self.apply_local)
        self.site=QPushButton('搜索站点');self.site.setObjectName('discoverySiteSearch');self.site.clicked.connect(self.search_sites)
        self.reset=QPushButton('清空');self.reset.clicked.connect(self.clear)
        for control in (self.local,self.site,self.reset):actions.addWidget(control)
        self.mode_label=QLabel('当前：已发现资料');self.mode_label.setObjectName('subtitle');actions.addWidget(self.mode_label)
        actions.addStretch();actions.addWidget(QLabel('排序'))
        self.sort=QComboBox();self.sort.setObjectName('discoverySort')
        for caption,key in [('首次发现时间','discovered'),('网站收录时间','site_added'),('名称','title'),('年份','year'),('来源评分','community_rating')]:self.sort.addItem(caption,key)
        self.sort.setCurrentIndex(max(0,self.sort.findData(window.library.setting('discovery_sort','discovered'))))
        self.descending=bool(window.library.setting('discovery_descending',True))
        self.direction=QPushButton();self.direction.setObjectName('discoveryDirection');self.update_direction()
        actions.addWidget(self.sort);actions.addWidget(self.direction);actions.addWidget(window.category_filter)
        capability_row=QHBoxLayout();layout.addLayout(capability_row)
        self.capability=QLabel();self.capability.setObjectName('subtitle');self.capability.setWordWrap(True);capability_row.addWidget(self.capability,1)
        self.install=QPushButton('安装 / 更新站点来源…');self.install.setObjectName('discoveryInstallSource');self.install.clicked.connect(self.setup_source);capability_row.addWidget(self.install)
        self.notice=QLabel();self.notice.setObjectName('discoveryStatus');self.notice.setWordWrap(True);self.notice.hide();layout.addWidget(self.notice)
        self.name.returnPressed.connect(self.repeat_action);self.tag.lineEdit().returnPressed.connect(self.repeat_action)
        self.sort.currentIndexChanged.connect(self.change_sort);self.direction.clicked.connect(self.flip_direction)
        window.source_filter.currentIndexChanged.connect(self.source_changed)
        window.category_filter.currentIndexChanged.connect(self.category_changed)
        self.siteFinished.connect(self.site_finished)
        self.siteFailed.connect(lambda token,error:self.show_notice('本次搜索失败，保留上次结果：'+error) if token==self.token else None)
        self.hide()

    def online_results(self):
        return self.mode=='online' and 'ids' in self._window.filters

    def request_fields(self):
        if self.online_results():return {'source':'','category':'','tag_query':''}
        return {'source':self._window.source_filter.currentData() or '',
                'category':self._window.category_filter.currentData() or '', 'tag_query':self.applied_tag}

    def snapshot(self):
        return {'name':self.name.text(),'tag':self.tag.text(),'applied_tag':self.applied_tag,'mode':self.mode,
                'sort':self.sort.currentData(),'descending':self.descending,'notice':self.settled_notice(self.notice.text())}

    @staticmethod
    def settled_notice(text):
        if text.startswith('正在后台搜索站点'):
            return '已离开原搜索页面；完成的资料会保存在已发现列表，可重新筛选或搜索。'
        return text

    def restore(self,state):
        self.token+=1;self.mode=state.get('mode','local');self.applied_tag=state.get('applied_tag','')
        self.name.setText(state.get('name',''));self.tag.setEditText(state.get('tag',''))
        self.sort.blockSignals(True);self.sort.setCurrentIndex(max(0,self.sort.findData(state.get('sort','discovered'))));self.sort.blockSignals(False)
        self.descending=bool(state.get('descending',True));self.update_direction();self.show_notice(self.settled_notice(state.get('notice','')))
        self.update_mode();self.update_capabilities()

    def reset_view(self):
        self.token+=1;self.mode='local';self.applied_tag='';self.name.clear();self.tag.setEditText('');self.show_notice('')
        self.update_mode();self.update_capabilities()

    def show_notice(self,text):
        self.notice.setText(text);self.notice.setVisible(bool(text))

    def update_mode(self):self.mode_label.setText('当前：站点搜索结果' if self.mode=='online' else '当前：已发现资料')
    def update_direction(self):self.direction.setText('降序 ↓' if self.descending else '升序 ↑')

    def set_facets(self,facets):
        text=self.tag.text();self.tag.blockSignals(True);self.tag.clear();self.tag.addItem('');self.tag.addItems([str(tag) for tag in facets.get('tags',[])]);self.tag.setEditText(text);self.tag.blockSignals(False)
        category=self._window.category_filter;selected=category.currentData()
        category.blockSignals(True);category.clear();category.addItem('全部分类','')
        for value in facets.get('categories',[]):category.addItem(str(value),value)
        # Retain an explicit category even when its current result set is empty.
        if selected and category.findData(selected)<0:category.addItem(str(selected),selected)
        category.setCurrentIndex(max(0,category.findData(selected)));category.blockSignals(False)

    def update_capabilities(self):
        selected=self._window.source_filter.currentData() or ''
        plugins=[plugin for plugin in Plugins(self._window.library).installed() if plugin['config'].get('enabled') and 'search' in plugin['capabilities'] and (not selected or plugin['id']==selected)]
        descriptions=[]
        for plugin in plugins:
            fields=plugin.get('search_filters',['name'])
            descriptions.append(plugin['name']+'：'+('名称、标签' if 'tag' in fields else '仅名称'))
        self.capability.setText('站点搜索能力 · '+'；'.join(descriptions) if descriptions else '所选来源没有启用的站点搜索插件。请在设置中安装并启用支持 search 的插件。')
        if not self.site.property('pending'):self.site.setEnabled(bool(plugins))

    def reload_sources(self):
        source=self._window.source_filter;selected=source.currentData()
        source.blockSignals(True);source.clear();source.addItem('全部来源','')
        for plugin in Plugins(self._window.library).installed():source.addItem(plugin['name'],plugin['id'])
        source.setCurrentIndex(max(0,source.findData(selected)));source.blockSignals(False)
        self.update_capabilities()

    def setup_source(self):
        choices=['TVmaze · 名称搜索（api.tvmaze.com / static.tvmaze.com）','Internet Archive · 名称与标签搜索（archive.org）']
        selected,ok=QInputDialog.getItem(self,'安装 / 更新并启用站点来源','选择来源及允许访问的网络主机；保留原代理配置',choices,0,False)
        if not ok:return
        plugin_id='tvmaze' if selected==choices[0] else 'internet-archive'
        def update(library,progress):
            manager=Plugins(library);manager.update_builtin_search_plugin(plugin_id);manager.configure(plugin_id,{'enabled':True})
            return {'updated':1,'plugin':plugin_id}
        def complete(result):
            self.reload_sources()
            index=self._window.source_filter.findData(plugin_id)
            if index>=0:self._window.source_filter.setCurrentIndex(index)
            self.show_notice('已更新并启用站点来源，可按上方名称或标签搜索。')
        self._window.run_job('安装或更新站点来源',update,complete)

    def source_changed(self):
        self.update_capabilities()
        if self._window.section=='discover' and not self.online_results():self._window.refresh()

    def category_changed(self):
        if self._window.section=='discover' and not self.online_results():self._window.refresh()

    def repeat_action(self):
        if self.mode=='online':self.search_sites()
        else:self.apply_local()

    def apply_local(self):
        window=self._window;self.token+=1;self.mode='local';self.applied_tag=self.tag.text().strip()
        window.filters.pop('ids',None);window.filters.pop('query',None)
        name=self.name.text().strip()
        if name:window.filters['query']=name
        window.search.setText(name);self.show_notice('');self.update_mode();window.refresh()

    def clear(self):
        window=self._window;self.reset_view();window.filters={};window.search.clear()
        for control in (window.source_filter,window.category_filter):control.blockSignals(True);control.setCurrentIndex(0);control.blockSignals(False)
        window.refresh()

    def change_sort(self,*_,refresh=True):
        window=self._window
        window.filters['sort']=self.sort.currentData();window.filters['descending']=self.descending
        try:
            window.library.set_setting('discovery_sort',self.sort.currentData());window.library.set_setting('discovery_descending',self.descending)
        except Exception as error:self.show_notice('排序已生效，但未保存默认设置：'+str(error))
        if refresh and window.section=='discover':window.refresh()

    def flip_direction(self):self.descending=not self.descending;self.update_direction();self.change_sort()

    def sync_advanced_filters(self):
        self.token+=1;self.mode='local';self.applied_tag='';self.name.setText(self._window.search.text());self.tag.setEditText('');self.update_mode();self.show_notice('')

    def site_finished(self,token):
        if token==self.site.property('pending'):
            self.site.setProperty('pending',None);self.site.setText('搜索站点');self.update_capabilities()

    def search_sites(self):
        window=self._window;name=self.name.text().strip();tag=self.tag.text().strip();source=window.source_filter.currentData() or ''
        if not name and not tag:self.show_notice('请输入影片名称或标签，再搜索站点。');return
        self.token+=1;token=self.token;self.show_notice('正在后台搜索站点，可以继续使用界面…')
        self.site.setProperty('pending',token);self.site.setEnabled(False);self.site.setText('正在搜索…')
        def search(library,progress):
            from .discovery_search import search_sites
            try:return search_sites(library,name,tag=tag,plugin_id=source,progress=progress)
            except Exception as error:
                self.siteFailed.emit(token,str(error));raise
            finally:self.siteFinished.emit(token)
        def complete(result):
            if token!=self.token:return
            if window.section!='discover' or window.detail_page is not None:
                self.show_notice(f"站点搜索已完成：{len(result.get('ids',[]))} 部作品；结果已保存，可返回筛选已发现资料。")
                return
            ids=[int(value) for value in result.get('ids',[])];self.mode='online';self.applied_tag=''
            # Provider matching may be fuzzy; only the confirmed result IDs
            # select this result set, including the legitimate empty set.
            window.filters={'ids':ids,'sort':self.sort.currentData(),'descending':self.descending}
            window.tabs.blockSignals(True);window.tabs.setCurrentIndex(0);window.tabs.blockSignals(False);window.subtab=0
            window.search.setText(name);self.update_mode()
            errors=result.get('errors',[])
            message=f'站点搜索：{len(ids)} 部作品'
            if errors:
                details=[]
                for error in errors:
                    if isinstance(error,dict):details.append(str(error.get('name') or error.get('plugin') or '来源')+'：'+str(error.get('error') or error.get('message') or '请求失败'))
                    else:details.append(str(error))
                message+=' · 部分来源失败：'+'；'.join(details)
            self.show_notice(message);window.refresh();window.status.setText(message)
        window.run_job('搜索影片站点',search,complete)
