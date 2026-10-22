"""Read-only browser snapshots; large catalog calculations run outside the GUI thread."""
from datetime import datetime
from PySide6.QtCore import QThread,Signal
from .core import Library


def load_view(library,request):
    section,tab=request['section'],request['tab']
    if section=='home' and tab==0:
        all_items=library.query({'local':False})
        return {'home':[item for item in all_items if item['files']],
                'recommendations':library.recommendations(items=all_items)}
    if section=='stats':
        return {'stats':library.stats(),'report':library.annual_report(request.get('year',datetime.now().year)) if tab==4 else None,
                'history':[dict(row) for row in library.db.execute('SELECT s.started,s.watched,w.title FROM sessions s JOIN files f ON s.file_id=f.id JOIN works w ON w.id=f.work_id ORDER BY s.started DESC LIMIT 200')] if tab==7 else []}
    if section=='movie' and tab==1:
        return {'items':library.actresses(request['actor_min'],request['actor_sort'])}
    if section=='discover':
        return {'items':library.recommendations(True) if tab==0 else library.query({'local':False})}
    result={'items':library.query(request['filters'])}
    if section=='other':result['tree']=library.query({'kinds':['other']})
    return result


class BrowseRead(QThread):
    done=Signal(object)
    failed=Signal(str)
    def __init__(self,directory,request,parent=None):
        super().__init__(parent);self.directory=directory;self.request=request
    def run(self):
        library=None
        try:
            library=Library(self.directory,initialize=False)
            self.done.emit(load_view(library,self.request))
        except Exception as error:self.failed.emit(str(error))
        finally:
            if library:library.close()
