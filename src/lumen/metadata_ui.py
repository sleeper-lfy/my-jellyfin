"""List-based tag and actor editing; no structured-data input required."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,
    QPushButton,QLineEdit,QComboBox,QLabel,QDialogButtonBox,QInputDialog,QMessageBox,QTabWidget)
from .metadata_edit import normalize, snapshot, save_lists


class MetadataList(QWidget):
    def __init__(self, field, values, parent=None):
        super().__init__(parent);self.field=field;self.values=copy.deepcopy(values)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.items=QListWidget();self.items.setObjectName(field+'List');layout.addWidget(self.items)
        row=QHBoxLayout();layout.addLayout(row);self.selection_controls=[]
        for name,callback in [('新增',self.add),('编辑',self.edit),('删除',self.remove)]:
            control=QPushButton(name);control.setObjectName(field+{'新增':'Add','编辑':'Edit','删除':'Remove'}[name]);control.clicked.connect(callback);row.addWidget(control)
            if name!='新增':self.selection_controls.append(control)
        self.items.currentRowChanged.connect(lambda index:[control.setEnabled(index>=0) for control in self.selection_controls])
        for control in self.selection_controls:control.setEnabled(False)
        self.items.itemDoubleClicked.connect(lambda _:self.edit());self.render()
    def render(self, selected=-1):
        self.items.clear()
        for value in self.values:
            if self.field=='tags':text=value
            else:
                text=value['name']
                if value.get('role'):text+=' · '+value['role']
                if value.get('aliases'):text+='（'+ '、'.join(value['aliases'])+'）'
            self.items.addItem(text)
        if selected>=0:self.items.setCurrentRow(selected)
    def replace(self,index,value):
        values=copy.deepcopy(self.values)
        if index<0:values.append(value);index=len(values)-1
        else:values[index]=value
        self.values=normalize(self.field,values);self.render(index)
    def add(self):self.change(-1)
    def edit(self):
        index=self.items.currentRow()
        if index>=0:self.change(index)
    def change(self,index):
        old=self.values[index] if index>=0 else None
        if self.field=='tags':
            value,ok=QInputDialog.getText(self,'编辑标签' if old else '新增标签','标签名称',text=old or '')
            if not ok:return
        else:
            dialog=QDialog(self);dialog.setWindowTitle('编辑演员' if old else '新增演员')
            form=QFormLayout(dialog);value=copy.deepcopy(old or {})
            name=QLineEdit(value.get('name',''));name.setObjectName('actorName')
            gender=QComboBox()
            for title,key in [('未知','unknown'),('女','female'),('男','male')]:gender.addItem(title,key)
            gender.setCurrentIndex(max(0,gender.findData(value.get('gender','unknown'))))
            aliases=QLineEdit('、'.join(value.get('aliases',[])));role=QLineEdit(value.get('role',''))
            form.addRow('姓名',name);form.addRow('性别',gender);form.addRow('别名（逗号或顿号分隔）',aliases);form.addRow('角色',role)
            status=QLabel();status.setWordWrap(True);form.addRow(status)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons)
            buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
            def accept():
                value.update(name=name.text().strip(),gender=gender.currentData(),aliases=[v.strip() for v in aliases.text().replace('，',',').replace('、',',').split(',') if v.strip()],role=role.text().strip())
                try:
                    test=copy.deepcopy(self.values)
                    if index<0:test.append(value)
                    else:test[index]=value
                    normalize('actors',test);dialog.accept()
                except ValueError as error:status.setText(str(error))
            buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:self.replace(index,value)
        except ValueError as error:QMessageBox.warning(self,'未修改',str(error))
    def remove(self):
        index=self.items.currentRow()
        if index<0:return
        del self.values[index];self.render(min(index,len(self.values)-1))


class MetadataEditor(QDialog):
    def __init__(self, window, work_id, selected='tags'):
        super().__init__(window);self.window=window;self.work_id=work_id
        self.setWindowTitle('编辑标签与演员 · 当前影片');self.resize(650,530)
        self.original=snapshot(window.library,work_id)
        layout=QVBoxLayout(self)
        note=QLabel('修改仅应用于当前影片。保存后锁定修改过的字段，刮削不会覆盖；取消则放弃本次修改。');note.setWordWrap(True);layout.addWidget(note)
        tabs=QTabWidget();layout.addWidget(tabs);self.editors={}
        for field,title in [('tags','标签'),('actors','演员')]:
            editor=MetadataList(field,self.original.get(field,[]));self.editors[field]=editor;tabs.addTab(editor,title)
        tabs.setCurrentIndex(1 if selected=='actors' else 0)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def save(self):
        changes={field:editor.values for field,editor in self.editors.items() if editor.values!=self.original.get(field,[])}
        try:
            if changes:save_lists(self.window.library,self.work_id,changes,self.original)
        except Exception as error:self.status.setText(str(error));return
        self.accept()
        if changes:
            self.window.reload_details(self.work_id)
            self.window.status.setText('标签与演员已保存，修改字段已锁定')


def edit_metadata_lists(window,work_id,selected='tags'):
    dialog=MetadataEditor(window,work_id,selected);result=dialog.exec();dialog.deleteLater();return result
