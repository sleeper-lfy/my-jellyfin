"""Stable VR movie groups: only videos with the exact same parent folder."""
import hashlib
import os
from pathlib import Path


class VRFolderPlan:
    def __init__(self, library, paths, cancelled=None):
        from .core import check_cancelled
        self.groups = {}
        for path in paths:
            check_cancelled(cancelled)
            folder = path.parent
            if folder not in self.groups:
                key = 'vr-folder:' + hashlib.sha256(os.path.normcase(str(folder.resolve())).encode()).hexdigest()
                bound = library.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
                self.groups[folder] = {'folder': folder, 'key': key, 'known': bound[0] if bound else None}
        for row in library.db.execute("SELECT f.path,f.work_id FROM files f JOIN works w ON w.id=f.work_id WHERE w.kind='vr' ORDER BY f.id"):
            check_cancelled(cancelled)
            group = self.groups.get(Path(row['path']).parent)
            if group and group['known'] is None:
                group['known'] = row['work_id']

    def group(self, path):
        return self.groups[path.parent]

    def reconcile(self, library, path, existing, warnings):
        group = self.group(path)
        if not existing:
            return existing
        if existing['work_id'] == group['known']:
            # Do not load every file in the work again for each unchanged part.
            with library.db:
                library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (group['key'], existing['work_id']))
            return existing
        source = library.work(existing['work_id'])
        if source['kind'] != 'vr':
            return existing
        with library.db:
            if group['known'] != source['id']:
                if not all(Path(file['path']).parent == group['folder'] for file in source['files']):
                    warnings.append({'path': str(path), 'reason': 'VR 条目关联多个目录，请手动核对合并'})
                    return existing
                library.merge_works(source['id'], group['known'], commit=False)
                existing = {'id': existing['id'], 'work_id': group['known']}
            library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (group['key'], existing['work_id']))
        return existing
