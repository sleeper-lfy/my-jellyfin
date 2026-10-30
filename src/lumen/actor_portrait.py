"""User-selected local portrait replacement, independent of scraper permissions."""
import hashlib
import json
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QIODevice, QSaveFile
from PySide6.QtGui import QImageReader
from .core import check_cancelled

PHOTO_FIELDS=('photo','photo_source','photo_source_id','photo_source_url','photo_page','photo_license','photo_attribution')


def replace_local_portrait(library, actor, source, *, cancelled=None):
    path=Path(source)
    if not path.is_file() or path.stat().st_size>40*1024*1024:
        raise ValueError('请选择不超过 40 MB 的本地图片')
    check_cancelled(cancelled)
    reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
    if not size.isValid() or size.width()*size.height()>40_000_000:
        raise ValueError('图片无法读取，或超过 4000 万像素')
    if max(size.width(),size.height())>1200:
        reader.setScaledSize(size.scaled(QSize(1200,1200),Qt.AspectRatioMode.KeepAspectRatio))
    picture=reader.read()
    if picture.isNull():raise ValueError('图片无法解码，请更换图片')
    # Hash decoded pixels so provenance is independent of the source filename.
    revision=hashlib.sha256(f'{picture.width()}x{picture.height()}:{picture.format().value}:'.encode()+bytes(picture.constBits())).hexdigest()
    cached=library.directory/'cache'/('actor-local-'+revision+'.png')
    output=QSaveFile(str(cached))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly) or not picture.save(output,'PNG') or not output.commit():
        raise ValueError('头像保存失败，原头像已保留')
    names={str(name).strip().casefold() for name in actor.get('portrait_names',
        [actor['name'],*actor.get('aliases',[])]) if str(name).strip()}
    actor_id=actor.get('id');updated=0
    check_cancelled(cancelled)
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        for work_id in dict.fromkeys(actor.get('work_ids',[])):
            check_cancelled(cancelled)
            row=library.db.execute('SELECT metadata FROM works WHERE id=?',(work_id,)).fetchone()
            if row is None:continue
            details=json.loads(row['metadata']);changed=False
            for credit in details.get('actors',[]):
                credit_names={str(name).strip().casefold() for name in [credit.get('name',''),*credit.get('aliases',[])]}
                if not (names & credit_names or actor_id and credit.get('id')==actor_id):continue
                for field in PHOTO_FIELDS:credit.pop(field,None)
                credit.update(photo_cache=str(cached),photo_revision=revision,photo_source='local',photo_local=True)
                changed=True
            if changed:
                library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(details,ensure_ascii=False),work_id))
                updated+=1
    if not updated:raise ValueError('演员关联资料已改变，请刷新演员列表后重新拖入')
    return {'updated':updated,'name':actor['name'],'photo_cache':str(cached)}
