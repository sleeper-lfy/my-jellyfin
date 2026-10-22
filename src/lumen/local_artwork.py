"""Explicit NFO artwork refresh. Changes cached image associations, never originals."""
from pathlib import Path
import json
from . import nfo
from .core import check_cancelled


def _valid(path):
    if not path or not Path(path).is_file():return False
    from PySide6.QtGui import QImageReader
    return QImageReader(str(path)).canRead()


def refresh_local_artwork(library,folder,mode='missing',work_id=None,progress=None,cancelled=None):
    if mode not in {'missing','overwrite'}:raise ValueError('未知图片更新方式')
    root=Path(folder).resolve()
    if not root.is_dir():raise ValueError('请选择有效的资源目录')
    works=[library.work(work_id)] if work_id else library.query()
    tasks=[]
    warnings=[]
    for work in works:
        files=work['files']
        if not files and work_id:
            sidecars=[path for path in root.iterdir() if path.suffix.lower()=='.nfo' and not path.is_symlink()]
            if len(sidecars)!=1:raise ValueError('未入库影片请选择只包含该影片 NFO 的资源目录')
            files=[{'id':None,'path':str(sidecars[0].with_suffix('.mp4')),'digest':None}]
        for file in files:
            video=Path(file['path']).resolve()
            if video.is_relative_to(root):tasks.append((work['id'],file,video))
            elif work_id and (root/(video.stem+'.nfo')).is_file():tasks.append((work['id'],file,root/video.name))
    if not tasks:raise ValueError('所选目录没有匹配的已入库视频 / 同名 NFO')
    result={'works':0,'poster':0,'thumbnail':0,'stills':0,'backdrop':0,'skipped':0,'warnings':warnings}
    touched=set();reset_galleries=set();cache={}
    for index,(identifier,file,video) in enumerate(tasks):
        check_cancelled(cancelled)
        data=nfo.load(video,root,library.work(identifier)['kind'],warnings,cache)
        work=library.work(identifier);metadata=work['metadata'];locked=set(work['locked'])
        changed=False
        def image(path,role):
            check_cancelled(cancelled)
            try:return nfo.cache_poster(path,library.directory)
            except (ValueError,OSError) as error:
                warnings.append({'path':str(path),'reason':role+': '+str(error)})
                return None
        cover=work['thumbnail']
        if data['poster']:
            if mode=='overwrite' or ('poster' not in locked and not _valid(cover)):
                cached=image(data['poster'],'海报')
                if cached:
                    cover=cached;metadata['nfo_poster']=True;result['poster']+=1;changed=True
            else:result['skipped']+=1
        if data.get('backdrop') and (mode=='overwrite' or not _valid(metadata.get('nfo_backdrop'))):
            cached=image(data['backdrop'],'背景图')
            if cached:metadata['nfo_backdrop']=cached;result['backdrop']+=1;changed=True
        if data.get('thumbnail') and file['id'] is not None:
            previous=metadata.get('nfo_thumbnails',{}).get(str(file['id']))
            generated=library.directory/'cache'/(file['digest']+'.jpg')
            if mode=='overwrite' or ('thumbnail' not in locked and not _valid(previous) and not _valid(generated)):
                cached=image(data['thumbnail'],'缩略图')
                if cached:
                    metadata.setdefault('nfo_thumbnails',{})[str(file['id'])]=cached;result['thumbnail']+=1;changed=True
            else:result['skipped']+=1
        if mode=='overwrite' or 'stills' not in locked:
            groups=[('nfo_stills',data.get('stills',[]))]
            if file['id'] is not None:groups.append((str(file['id']),data.get('episode_stills',[])))
            for key,paths in groups:
                if not paths:continue
                saved=[value for path in paths if (value:=image(path,'剧照'))]
                if not saved:continue
                if mode=='overwrite' and identifier not in reset_galleries:
                    metadata['nfo_stills']=[];metadata['episode_stills']={};metadata['stills']=[];metadata['stills_cache']=[]
                    reset_galleries.add(identifier)
                container=metadata if key=='nfo_stills' else metadata.setdefault('episode_stills',{})
                before=container.get(key,[])
                # Add missing images without removing existing artwork, or replace only supplied groups.
                after=list(dict.fromkeys(([] if mode=='overwrite' else before)+saved))[:40]
                container[key]=after;result['stills']+=len(set(after)-set(before));changed=True
        if changed:
            with library.db:
                library.db.execute('UPDATE works SET thumbnail=?,metadata=? WHERE id=?',(cover,json.dumps(metadata,ensure_ascii=False),identifier))
            touched.add(identifier)
        if progress:progress(index+1,len(tasks),work['title'])
    result['works']=len(touched)
    return result
