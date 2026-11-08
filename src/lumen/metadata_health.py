"""Missing-only repair, explicit metadata replacement and retryable image caching."""
from __future__ import annotations
import copy
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from .core import check_cancelled, ImportCancelled, now, identity
from .plugins import Plugins, validate_metadata, external_ids_conflict

FIELDS = ('overview', 'tags', 'actors', 'poster')
LABELS = {'title':'标题', 'year':'年份', 'overview':'简介', 'tags':'标签', 'actors':'演员',
          'directors':'导演', 'aliases':'别名', 'poster':'海报', 'cover':'缩略图', 'stills':'剧照', 'images':'图片缓存'}


def _read(library, work_id):
    row = library.db.execute('SELECT id,kind,title,year,metadata,locked,thumbnail FROM works WHERE id=?', (work_id,)).fetchone()
    if row is None: raise ValueError('影片已不存在')
    item = dict(row); item['metadata'] = json.loads(item['metadata']); item['locked'] = json.loads(item['locked'])
    return item


def _cached(path):
    if not isinstance(path,(str,Path)):return False
    try: return bool(path and Path(path).is_file() and Path(path).stat().st_size)
    except OSError: return False


def _protected(library, work):
    fields = set(work['locked']) | set(work['metadata'].get('nfo_fields', []))
    if work['metadata'].get('nfo_poster') or library.setting(f"artwork_{work['id']}", {}).get('poster'):
        fields.add('poster')
    return fields


def _poster_present(library, work):
    custom = library.setting(f"artwork_{work['id']}", {}).get('poster')
    if _cached(custom):return True
    thumbnail=work['thumbnail'];metadata=work['metadata']
    if not _cached(thumbnail):return False
    if metadata.get('nfo_poster'):return True
    # FFmpeg frames are useful placeholders, but they are not scraped posters.
    generated={str(library.directory/'cache'/(row['digest']+'.jpg'))
               for row in library.db.execute('SELECT digest FROM files WHERE work_id=?',(work['id'],))}
    if str(thumbnail) in generated:return False
    if metadata.get('poster'):return True
    return any(entry.get('path')==thumbnail for entry in metadata.get('stills_cache',[]) if isinstance(entry,dict))


def image_requests(library, work):
    metadata = work['metadata']; requests = []
    if metadata.get('poster') and not _poster_present(library, work):
        requests.append({'field':'poster', 'url':metadata['poster']})
    from .artwork import scraped_image_path
    if metadata.get('cover') and not scraped_image_path(work,'cover'):
        requests.append({'field':'cover', 'url':metadata['cover']})
    for actor in metadata.get('actors', []):
        if actor.get('photo') and not _cached(actor.get('photo_cache')):
            requests.append({'field':'actors', 'url':actor['photo'], 'name':actor['name']})
    cached = {entry.get('url'):entry.get('path') for entry in metadata.get('stills_cache', []) if isinstance(entry,dict)}
    for url in dict.fromkeys(metadata.get('stills', [])):
        if not _cached(cached.get(url)): requests.append({'field':'stills', 'url':url})
    return requests


def scan_health(library, work_ids=None, progress=None, cancelled=None, *, include_complete=False):
    wanted = set(work_ids) if work_ids is not None else None
    rows = library.db.execute("SELECT id FROM works WHERE kind IN ('movie','series','vr') AND EXISTS (SELECT 1 FROM files WHERE work_id=works.id) ORDER BY title,id").fetchall()
    items=[]
    for index,row in enumerate(rows):
        check_cancelled(cancelled)
        if wanted is not None and row['id'] not in wanted: continue
        work = _read(library,row['id']); metadata=work['metadata']; protected=_protected(library,work)
        missing=[field for field in ('overview','tags','actors') if not metadata.get(field)]
        if not _poster_present(library,work): missing.append('poster')
        requests=image_requests(library,work)
        if include_complete or missing or requests:
            sources=[dict(row) for row in library.db.execute('SELECT plugin,site,url,source_id FROM sources WHERE work_id=?',(work['id'],))]
            items.append({'id':work['id'],'title':work['title'],'kind':work['kind'],'missing':missing,
                          'locked':[field for field in missing if field in protected],
                          'images':len(requests),'image_locked':sum(request['field'] in protected for request in requests),
                          'sources':list(dict.fromkeys(source['site'] for source in sources))})
        if progress: progress(index+1,len(rows),'检查资料 · '+work['title'])
    return {'checked':len(rows) if wanted is None else sum(row['id'] in wanted for row in rows),'items':items}


def _providers(library, work, manager, plugin_ids):
    enabled={p['id']:p for p in manager.installed() if p['config'].get('enabled')}
    associated=[dict(row) for row in library.db.execute('SELECT plugin,source_id,url FROM sources WHERE work_id=?',(work['id'],))]
    if plugin_ids is None:
        rule=library.setting('partition:'+work['kind'],{})
        ids=[source['plugin'] for source in associated]
        ids += [rule.get('plugin',''), *rule.get('fallback_plugins',[]), *library.setting('numbered_fallbacks:'+work['kind'],[])]
    else: ids=list(plugin_ids)
    return [(enabled[identifier],next((source for source in associated if source['plugin']==identifier),None))
            for identifier in dict.fromkeys(ids) if identifier in enabled]


def _detail(library, work, manager, plugin, source, *, refresh=False, cancelled=None):
    parameters={'cancelled':cancelled,**({'refresh':True} if refresh else {})}
    if source and 'detail' in plugin['capabilities']:
        records=manager.run(plugin['id'],'detail',url=source['url'],**parameters)
        records=[record for record in records if str(record['id'])==str(source['source_id'])]
        if len(records)!=1: raise ValueError('详情来源标识不一致')
        record=records[0]
    else:
        if 'search' not in plugin['capabilities']: raise ValueError('来源不支持影片搜索')
        from .ingestion import choose, work_codes
        complete=library.work(work['id']); identifiers=work_codes(complete)
        if len(identifiers)>1: raise ValueError('影片包含多个编号，请先确认归组')
        query=next(iter(identifiers)) if identifiers else work['title']
        record=choose(complete,manager.run(plugin['id'],'search',query=query,**parameters))
        if 'detail' in plugin['capabilities']:
            records=manager.run(plugin['id'],'detail',url=record['url'],**parameters)
            exact=[value for value in records if str(value['id'])==str(record['id'])]
            if len(exact)!=1: raise ValueError('详情来源标识不一致')
            record=exact[0]
    validate_metadata(record)
    from .ingestion import choose, work_codes
    current=library.work(work['id'])
    if work_codes(current):choose(current,[record])
    kind=record.get('kind','movie')
    if kind!=work['kind'] and not (kind=='movie' and work['kind']=='vr'): raise ValueError('候选类型不匹配')
    return record


def _fill(library, work_id, plugin, record):
    """Commit only still-empty fields under the write lock; never replace identity."""
    changed=[]
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        work=_read(library,work_id); metadata=work['metadata']; protected=_protected(library,work)
        linked=library.db.execute('SELECT work_id FROM sources WHERE plugin=? AND source_id=?',(plugin['id'],str(record['id']))).fetchone()
        if linked and linked['work_id']!=work_id: raise ValueError('此来源已关联其他作品，请先核对')
        known=dict(library.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(work_id,)).fetchall())
        if external_ids_conflict(known.items(),{key.lower():value for key,value in record.get('external_ids',{}).items() if value is not None}):
            raise ValueError('来源的外部编号与当前影片冲突')
        for field in ('overview','tags','actors','poster','cover','stills'):
            if field in protected or metadata.get(field) or not record.get(field): continue
            if field=='poster' and _poster_present(library,work): continue
            metadata[field]=copy.deepcopy(record[field]);changed.append(field)
        provenance=metadata.setdefault('health_image_sources',{})
        for field in changed:
            if field in {'poster','cover'}:provenance[metadata[field]]=plugin['id']
            if field=='actors':
                for actor in metadata['actors']:
                    if actor.get('photo'):provenance[actor['photo']]=plugin['id']
            if field=='stills':
                for url in metadata['stills']:provenance[url]=plugin['id']
        if changed:
            library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),work_id))
            library.db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?)',
                (work_id,plugin['id'],plugin['name'],str(record['id']),record['url'],now(),record.get('site_added'),record.get('rating')))
    return changed


def _download(library, manager, plugin, url, *, refresh=False):
    from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QSize,QSaveFile,Qt
    from PySide6.QtGui import QImageReader
    filename='health-'+hashlib.sha256((plugin['id']+'\n'+url).encode()).hexdigest()+'.jpg'
    target=library.directory/'cache'/filename
    if not refresh and _cached(target): return str(target)
    data,content_type=manager.fetch(plugin,url,image=True)
    if not content_type.startswith('image/'): raise ValueError('图片响应类型无效')
    if refresh:
        # A new response must never change a file still used by the old view.
        target=library.directory/'cache'/('health-refresh-'+hashlib.sha256(data).hexdigest()+'.jpg')
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);reader.setAutoTransform(True);size=reader.size()
    if size.width()<=0 or size.height()<=0 or size.width()*size.height()>40_000_000: raise ValueError('图片无效或像素过大')
    if max(size.width(),size.height())>1920:reader.setScaledSize(size.scaled(QSize(1920,1920),Qt.AspectRatioMode.KeepAspectRatio))
    picture=reader.read();output=QSaveFile(str(target))
    if picture.isNull() or not output.open(QIODevice.OpenModeFlag.WriteOnly) or not picture.save(output,'JPG') or not output.commit():
        raise ValueError('图片解码或保存失败')
    return str(target)


def _attach(library, work_id, request, path):
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        work=_read(library,work_id);metadata=work['metadata'];field=request['field'];url=request['url']
        if field in _protected(library,work): return False
        if field=='poster':
            if metadata.get('poster')!=url or _poster_present(library,work): return False
            library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(path,work_id))
            metadata['poster_cache']={'url':url,'path':path}
        elif field=='cover':
            if metadata.get('cover')!=url:return False
            metadata['cover_cache']={'url':url,'path':path}
        elif field=='actors':
            matches=[actor for actor in metadata.get('actors',[]) if actor.get('name')==request['name'] and actor.get('photo')==url]
            if len(matches)!=1 or _cached(matches[0].get('photo_cache')):return False
            matches[0]['photo_cache']=path
            matches[0]['photo_revision']=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        else:
            if url not in metadata.get('stills',[]):return False
            cache=metadata.setdefault('stills_cache',[])
            if any(entry.get('url')==url and _cached(entry.get('path')) for entry in cache):return False
            metadata['stills_cache']=[entry for entry in cache if entry.get('url')!=url]+[{'url':url,'path':path}]
        library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),work_id))
        return True


def retry_images(library, work_id, plugin_ids=None, cancelled=None):
    work=_read(library,work_id);manager=Plugins(library);providers=_providers(library,work,manager,plugin_ids)
    manager.cancelled=cancelled
    enabled={p['id']:p for p in manager.installed() if p['config'].get('enabled')}
    provenance=work['metadata'].get('health_image_sources',{})
    result={'updated':0,'skipped':0,'errors':[]}
    for request in image_requests(library,work):
        check_cancelled(cancelled)
        field=request['field'];url=request['url']
        if field in _protected(library,work):result['skipped']+=1;continue
        candidates=[p for p,_ in providers]
        if provenance.get(url) in enabled:candidates.insert(0,enabled[provenance[url]])
        plugin=next((p for p in candidates if urlparse(url).hostname in p['domains']),None)
        identifier='health-image-'+hashlib.sha256((str(work_id)+field+url+request.get('name','')).encode()).hexdigest()
        payload={'work_id':work_id,**request}
        try:
            if not plugin:raise ValueError('没有已启用且允许此图片域名的关联来源')
            payload['plugin']=plugin['id'];library.task(identifier,'health-image','running',payload)
            path=_download(library,manager,plugin,url);check_cancelled(cancelled)
            if _attach(library,work_id,request,path):result['updated']+=1
            else:result['skipped']+=1
            library.task(identifier,'health-image','done',payload)
        except ImportCancelled:
            library.task(identifier,'health-image','cancelled',payload);raise
        except Exception as error:
            result['errors'].append({'field':field,'url':url,'error':str(error)})
            library.task(identifier,'health-image','failed',payload,error=str(error))
    if any(plugin['id']=='javinizer-go' for plugin,_ in providers):
        from .javinizer import _select_poster
        _select_poster(library,work_id,False,cancelled)
    return result


def _overwrite(library, work, plugin, record, manager, cancelled, selected):
    """Stage replacement artwork, then replace presentation in one short transaction."""
    work_id=work['id']
    fields=('title','year','overview','tags','actors','directors','aliases','released','poster','cover','stills',
            'runtime','studio','label','maker','series','javinizer_source','download_method','download_url')
    metadata={field:copy.deepcopy(record[field]) for field in fields if field in record}
    # Actor cache paths and prior local/NFO artwork are owned by the host.
    for actor in metadata.get('actors',[]):
        for field in ('photo_cache','photo_revision','photo_local'):
            actor.pop(field,None)
    external={str(key).lower():str(value) for key,value in record.get('external_ids',{}).items() if value is not None and str(value)}
    metadata['external_ids']={**work['metadata'].get('external_ids',{}),**external}
    if metadata.get('download_url'):metadata['download_plugin']=plugin['id']
    key=identity(record['title'],record.get('year'),work['kind'])

    def validate_target():
        current=_read(library,work_id)
        if current!=work or library.setting(f'artwork_{work_id}',{})!=selected:
            raise ValueError('修复期间影片资料已修改，请重新检查后再覆盖')
        linked=library.db.execute('SELECT work_id FROM sources WHERE plugin=? AND source_id=?',(plugin['id'],str(record['id']))).fetchone()
        if linked and linked['work_id']!=work_id:raise ValueError('此来源已关联其他作品，请先核对')
        for namespace,value in external.items():
            linked=library.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',
                                      (work['kind'],namespace,value)).fetchone()
            if linked and linked[0]!=work_id:raise ValueError('外部编号已关联其他作品，请先核对')
        linked=library.db.execute('SELECT id FROM works WHERE identity=? AND id!=?',(key,work_id)).fetchone()
        if linked:raise ValueError('同标题与年份已关联其他作品，请先核对')
        linked=library.db.execute('SELECT work_id FROM name_keys WHERE key=?',(key,)).fetchone()
        if linked and linked[0]!=work_id:raise ValueError('标题索引已关联其他作品，请先核对')

    validate_target()
    requests=[('poster',metadata.get('poster')),('cover',metadata.get('cover'))]
    requests += [('actors',actor.get('photo')) for actor in metadata.get('actors',[])]
    requests += [('stills',url) for url in metadata.get('stills',[])]
    downloaded={};errors=[];attempted=set();deadline=time.monotonic()+180
    for field,url in requests:
        check_cancelled(cancelled)
        if not url or url in attempted:continue
        if time.monotonic()>deadline:
            errors.append('图片下载超过 180 秒，已保存资料；可重试缺失图片')
            break
        attempted.add(url)
        try:
            downloaded[url]=_download(library,manager,plugin,url,refresh=True)
        except ImportCancelled:raise
        except Exception as error:errors.append(LABELS[field]+'：'+str(error))
    for field in ('poster','cover'):
        url=metadata.get(field)
        if url in downloaded:metadata[field+'_cache']={'url':url,'path':downloaded[url]}
    for actor in metadata.get('actors',[]):
        if actor.get('photo') in downloaded:
            actor['photo_cache']=downloaded[actor['photo']]
            actor['photo_revision']=hashlib.sha256(Path(actor['photo_cache']).read_bytes()).hexdigest()
    metadata['stills_cache']=[{'url':url,'path':downloaded[url]} for url in dict.fromkeys(metadata.get('stills',[])) if url in downloaded]
    metadata['health_image_sources']={url:plugin['id'] for _,url in requests if url}
    from .artwork import scraped_poster_path
    cover=downloaded.get(metadata.get('cover'))
    original=downloaded.get(metadata.get('poster'))
    poster=scraped_poster_path(library,{'metadata':metadata},original,
                               fallback_paths=[path for path in (cover,original) if path])
    check_cancelled(cancelled)
    with library.db:
        library.db.execute('BEGIN IMMEDIATE');validate_target()
        library.db.execute('UPDATE works SET identity=?,title=?,year=?,metadata=?,locked=?,thumbnail=? WHERE id=?',
                           (key,record['title'],record.get('year'),json.dumps(metadata,ensure_ascii=False),'[]',poster,work_id))
        library.db.execute('DELETE FROM settings WHERE key=?',(f'artwork_{work_id}',))
        library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(key,work_id))
        for alias in metadata.get('aliases',[]):
            library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(identity(alias,record.get('year'),work['kind']),work_id))
        for namespace,value in external.items():
            # A deliberate replacement may correct this work's old identifiers.
            # Ownership of every incoming ID was checked again under the write lock.
            library.db.execute('DELETE FROM external_ids WHERE work_id=? AND namespace=?',(work_id,namespace))
            library.db.execute('INSERT OR IGNORE INTO external_ids VALUES (?,?,?,?)',(work['kind'],namespace,value,work_id))
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plugin,source_id) DO UPDATE SET url=excluded.url,updated=excluded.updated,site_added=excluded.site_added,rating=excluded.rating',
                           (work_id,plugin['id'],plugin['name'],str(record['id']),record['url'],now(),record.get('site_added'),record.get('rating')))
    return {'fields':[field for field in LABELS if field not in {'images'}], 'images':len(downloaded),'errors':errors}


def overwrite_snapshot(library, work_id):
    """Capture presentation before fetching; personal state is deliberately excluded."""
    return _read(library,work_id),copy.deepcopy(library.setting(f'artwork_{work_id}',{}))


def overwrite_metadata(library, plugin, record, work_id, *, cancelled=None, snapshot=None):
    """Shared forced replacement for manual matching and the batch repair panel."""
    check_cancelled(cancelled)
    validate_metadata(record)
    work,selected=snapshot if snapshot is not None else overwrite_snapshot(library,work_id)
    if work['kind'] not in {'movie','series','vr'}:
        raise ValueError('该分类不使用影视资料修复')
    kind=record.get('kind','movie')
    if kind!=work['kind'] and not (kind=='movie' and work['kind']=='vr'):
        raise ValueError('候选媒体类型不匹配')
    manager=Plugins(library);manager.cancelled=cancelled
    return _overwrite(library,work,plugin,record,manager,cancelled,selected)


def repair_many(library, work_ids, *, images_only=False, force=False, plugin_ids=None, progress=None, cancelled=None):
    if images_only and force:raise ValueError('强制覆盖需要重新获取影片资料，不能同时仅重试图片')
    result={'updated':0,'images':0,'failed':0,'skipped':0,'items':[]}
    identifiers=list(dict.fromkeys(work_ids))
    for index,work_id in enumerate(identifiers):
        try:check_cancelled(cancelled)
        except ImportCancelled:result['stopped']=True;break
        item={'id':work_id,'title':str(work_id),'fields':[],'images':0,'errors':[]}
        try:
            work=_read(library,work_id);item['title']=work['title']
            if work['kind'] not in {'movie','series','vr'}:raise ValueError('该分类不使用影视资料修复')
            if force:
                manager=Plugins(library);manager.cancelled=cancelled
                selected=copy.deepcopy(library.setting(f'artwork_{work_id}',{}))
                providers=_providers(library,work,manager,plugin_ids)
                if not providers:item['errors'].append('没有可用影片来源；请配置或启用搜索 / 详情插件')
                for plugin,source in providers:
                    check_cancelled(cancelled)
                    try:
                        record=_detail(library,work,manager,plugin,source,refresh=True,cancelled=cancelled)
                        replaced=overwrite_metadata(library,plugin,record,work_id,cancelled=cancelled,snapshot=(work,selected))
                        item.update(replaced)
                        item['id']=work_id;item['title']=record['title']
                        break
                    except ImportCancelled:raise
                    except Exception as error:item['errors'].append(plugin['name']+'：'+str(error))
            elif not images_only:
                manager=Plugins(library);providers=_providers(library,work,manager,plugin_ids)
                wanted=[field for field in FIELDS if field not in _protected(library,work) and not work['metadata'].get(field) and not(field=='poster' and _poster_present(library,work))]
                if wanted and not providers:item['errors'].append('没有可用影片来源；请配置或启用搜索 / 详情插件')
                for plugin,source in providers:
                    if not wanted:break
                    check_cancelled(cancelled)
                    try:
                        record=_detail(library,work,manager,plugin,source,cancelled=cancelled)
                        item['fields']+=_fill(library,work_id,plugin,record)
                        work=_read(library,work_id)
                        wanted=[field for field in wanted if not work['metadata'].get(field)]
                    except ImportCancelled:raise
                    except Exception as error:item['errors'].append(plugin['name']+'：'+str(error))
                if wanted and providers:item['errors'].append('来源未补齐：'+'、'.join(LABELS[field] for field in wanted))
            if not force:
                images=retry_images(library,work_id,plugin_ids,cancelled)
                item['images']=images['updated'];item['errors'] += [LABELS.get(error['field'],error['field'])+'：'+error['error'] for error in images['errors']]
            if item['fields'] or item['images']:result['updated']+=1
            else:result['skipped']+=1
        except ImportCancelled:result['stopped']=True;break
        except Exception as error:item['errors'].append(str(error))
        if item['errors']:result['failed']+=1
        result['images']+=item['images'];result['items'].append(item)
        if progress:progress(index+1,len(identifiers),'修复资料 · '+item['title'])
    return result
