"""User-started downloads: stream to a temporary file, then atomically publish."""
from pathlib import Path
from urllib.parse import urlparse
import os
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
import time
import httpx
from .core import ImportCancelled, check_cancelled


def download_direct(library, plugin_id, url, target, progress=None, cancelled=None, overwrite=False, *, resolve_target=None):
    from .plugins import Plugins
    plugin=next((item for item in Plugins(library).installed() if item['id']==plugin_id),None)
    parsed=urlparse(url)
    if plugin is None or parsed.scheme not in {'http','https'} or parsed.hostname not in plugin['domains'] or parsed.username or parsed.password:
        raise ValueError('下载地址不在插件声明的 HTTP/HTTPS 域名内')
    target=Path(target)
    if target.exists() and not overwrite and not resolve_target:raise ValueError('目标文件已存在')
    task_id=uuid.uuid4().hex
    temporary=target.with_name(target.name+'.'+task_id+'.part')
    payload={'url':url,'plugin':plugin_id,'target':str(target),'bytes':0,'total':0}
    library.task(task_id,'download','running',payload)
    proxy=plugin['config'].get('proxy','inherit')
    if proxy=='inherit':proxy=library.setting('proxy','')
    count=0
    digest=hashlib.sha256()
    last_saved=time.monotonic()
    try:
        check_cancelled(cancelled)
        with httpx.Client(proxy=proxy or None,trust_env=False,timeout=httpx.Timeout(30,connect=20),follow_redirects=False) as client:
            with client.stream('GET',url,headers={'User-Agent':'Lumen/0.4','Accept-Encoding':'identity'}) as response:
                response.raise_for_status()
                if response.is_redirect:raise ValueError('下载重定向被拒绝，请让插件返回最终下载地址')
                if resolve_target:
                    target=Path(resolve_target(response.headers))
                    if target.exists() and not overwrite:raise ValueError('目标文件已存在，未覆盖')
                    temporary=target.with_name(target.name+'.'+task_id+'.part')
                    payload['target']=str(target)
                target.parent.mkdir(parents=True,exist_ok=True)
                total=int(response.headers.get('content-length','0'))
                payload['total']=total
                with temporary.open('xb') as stream:
                    for block in response.iter_bytes(256*1024):
                        check_cancelled(cancelled)
                        stream.write(block);digest.update(block);count+=len(block);payload['bytes']=count
                        if time.monotonic()-last_saved>=1:
                            library.task(task_id,'download','running',payload)
                            last_saved=time.monotonic()
                        if progress:progress(count,total,f'下载 {count/1048576:.1f} MB'+(f' / {total/1048576:.1f} MB' if total else ''))
                if total and count!=total:raise ValueError('下载长度与服务器声明不符')
        check_cancelled(cancelled)
        if target.exists() and not overwrite:raise ValueError('目标文件已存在')
        if overwrite:
            os.replace(temporary,target)
        elif os.name == 'nt':
            os.rename(temporary,target)  # Windows rename fails atomically if the target exists.
        else:
            os.link(temporary,target)  # Atomic no-replace publication on the same filesystem.
            temporary.unlink()
        library.task(task_id,'download','done',payload,{'path':str(target),'bytes':count})
        return {'path':str(target),'bytes':count,'sha256':digest.hexdigest()}
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        library.task(task_id,'download','cancelled' if isinstance(exc,ImportCancelled) else 'failed',payload,error=str(exc))
        raise


FOLDERS = {'movie': 'Movies', 'series': 'TV Shows', 'vr': 'VR Movies'}


def default_download_root(library, kind):
    if kind not in FOLDERS: raise ValueError('此分类不支持下载')
    configured = library.setting('downloads', {}).get(kind)
    organized = library.setting('partition:' + kind, {}).get('destination')
    return Path(configured or organized or Path.home() / 'Videos' / 'Lumen' / FOLDERS[kind]).expanduser().absolute()


def download_folder(library, work_id):
    from .files import safe_name
    work = library.work(work_id)
    override = library.setting('download-folder:' + str(work_id))
    return Path(override).expanduser().absolute() if override else default_download_root(library, work['kind']) / (safe_name(work['title'])[:100] + (f" ({work['year']})" if work['year'] else ''))


def set_download_folder(library, work_id, directory):
    library.work(work_id)
    value = str(directory).strip()
    if value and not Path(value).expanduser().is_absolute(): raise ValueError('请输入服务端的绝对保存路径')
    library.set_setting('download-folder:' + str(work_id), str(Path(value).expanduser().absolute()) if value else None)
    return str(download_folder(library, work_id))


def resource(library, work_id, index):
    work = library.work(work_id)
    entries = work['metadata'].get('download_url', [])
    if type(index) is not int or not 0 <= index < len(entries): raise ValueError('下载资源不存在，请刷新详情')
    entry = entries[index]
    method = entry.get('method', work['metadata'].get('download_method'))
    if method not in {'magnet', 'direct'}: raise ValueError('无效下载方式')
    return work, entry, method


def video_filename(headers, url, title):
    from email.message import Message
    from urllib.parse import unquote
    from .files import safe_name
    from .core import VIDEO_EXTENSIONS
    message = Message(); message['Content-Disposition'] = headers.get('content-disposition', '')
    supplied = message.get_filename()
    filename = supplied or unquote(urlparse(url).path).replace('\\', '/').rsplit('/', 1)[-1]
    filename = str(filename).replace('\\', '/').rsplit('/', 1)[-1] or title
    mime = headers.get('content-type', '').split(';')[0].strip().lower()
    if mime.startswith('text/') or mime in {'application/json', 'application/zip', 'application/x-bittorrent'}:
        raise ValueError('直链没有返回视频文件，请使用最终视频下载链接')
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        if supplied and suffix or suffix and suffix not in {'.php','.asp','.aspx','.cgi','.action','.do'}:
            raise ValueError('直链文件不是支持的视频格式：' + suffix)
        suffix = {'video/x-matroska': '.mkv', 'video/webm': '.webm', 'video/x-msvideo': '.avi', 'video/mp2t': '.ts'}.get(mime, '.mp4')
        filename = (safe_name(filename)[:110] if supplied else safe_name(title)[:100] + '-' + hashlib.sha256(url.encode()).hexdigest()[:10]) + suffix
    return safe_name(Path(filename).stem)[:115] + Path(filename).suffix.lower()


def write_download_metadata(library, work_id, folder, video=None, season=None, episode=None):
    """Portable sidecars; never replace a user's existing NFO or artwork."""
    import xml.etree.ElementTree as ET
    from .artwork import still_paths
    work = library.work(work_id); metadata = work['metadata']; folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    series = work['kind'] == 'series'
    root = ET.Element('tvshow' if series else 'movie')
    for key,value in [('title',work['title']),('year',work['year']),('plot',metadata.get('overview'))]:
        if value is not None: ET.SubElement(root,key).text = str(value)
    for tag in metadata.get('tags', []): ET.SubElement(root,'tag').text = tag
    for person in metadata.get('actors', []):
        actor = ET.SubElement(root,'actor'); ET.SubElement(actor,'name').text = person['name']
        ET.SubElement(actor,'gender').text = person.get('gender','unknown')
    for name,value in metadata.get('external_ids', {}).items(): ET.SubElement(root,'uniqueid',{'type':name}).text = str(value)
    images = [('poster.jpg',work['thumbnail']), ('fanart.jpg', metadata.get('nfo_backdrop'))]
    images += [(f'extrafanart/extrafanart-{i+1}.jpg',path) for i,path in enumerate(still_paths(work))]
    warnings = []
    for name,path in images:
        if not path or not Path(path).is_file(): continue
        target = folder / name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with target.open('xb') as output, Path(path).open('rb') as source: shutil.copyfileobj(source,output)
            if name == 'poster.jpg': ET.SubElement(root,'poster').text = name
            elif name == 'fanart.jpg': ET.SubElement(root,'fanart').text = name
        except OSError as error: warnings.append(str(error))
    nfo = folder / ('tvshow.nfo' if series else 'movie.nfo')
    if not nfo.exists():
        with nfo.open('xb') as output: ET.ElementTree(root).write(output,encoding='utf-8',xml_declaration=True)
    if series and video and season is not None and episode is not None:
        episode_root=ET.Element('episodedetails')
        for key,value in [('title',Path(video).stem),('season',season),('episode',episode)]: ET.SubElement(episode_root,key).text=str(value)
        sidecar=Path(video).with_suffix('.nfo')
        if not sidecar.exists():
            with sidecar.open('xb') as output: ET.ElementTree(episode_root).write(output,encoding='utf-8',xml_declaration=True)
    return warnings


def register_download(library, work_id, path, root, digest=None, progress=None, cancelled=None):
    from .core import fingerprint, probe, parse_name, quick_fingerprint
    work = library.work(work_id); path=Path(path).resolve(strict=True); root=Path(root).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError('视频不在当前下载目录内')
    before = path.stat()
    existing = library.db.execute('SELECT id,work_id FROM files WHERE path=?',(str(path),)).fetchone()
    if existing:
        if existing['work_id'] != work_id: raise ValueError('此文件已关联其他作品，未重新关联')
        return {'file_id':existing['id'],'work_id':work_id,'path':str(path),'duplicate':True}
    if progress: progress(0,0,'检查下载视频并关联影视资料')
    # No network protocols are needed when probing a completed local download.
    duration = probe(path,cancelled=cancelled,local_only=True)
    warnings=[]
    from . import nfo
    local=nfo.load(path,root,work['kind'],warnings)
    local['work']=None  # A downloaded folder must not rename the explicitly selected work.
    if work['thumbnail']: local['poster']=None
    if work['metadata'].get('nfo_backdrop'): local['backdrop']=None
    season=episode=None
    if work['kind']=='series':
        try:
            parsed=parse_name(path,'series');season,episode=parsed['season'],parsed['episode']
        except ValueError:
            # Preserve an opaque single episode; never invent an episode number.
            pass
        if local['entry']:
            season=local['entry']['season'] if local['entry']['season'] is not None else season
            episode=local['entry']['episode'] if local['entry']['episode'] is not None else episode
    digest = digest or fingerprint(path,cancelled=cancelled)
    check_cancelled(cancelled)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('文件仍在变化，请下载完成后再入库')
    duplicate=library.db.execute('SELECT id,work_id FROM files WHERE digest=?',(digest,)).fetchone()
    if duplicate:
        if duplicate['work_id']!=work_id: raise ValueError('相同视频已属于另一部作品，请核对后合并')
        return {'file_id':duplicate['id'],'work_id':work_id,'path':str(path),'duplicate':True}
    quick=quick_fingerprint(path)
    with library.db:
        file_id=library.db.execute('INSERT INTO files(work_id,path,digest,root,season,episode,duration) VALUES (?,?,?,?,?,?,?)',
            (work_id,str(path),digest,str(root),season,episode,duration)).lastrowid
        library.db.execute('INSERT INTO import_cache VALUES (?,?,?,?,?,?,?)',(file_id,after.st_size,after.st_mtime_ns,quick,digest,'',1 if not work['thumbnail'] else 0))
        nfo.apply(library,work_id,file_id,local,False,True,root,warnings)
    try: warnings.extend(write_download_metadata(library,work_id,root,path,season,episode))
    except OSError as error: warnings.append(str(error))
    return {'file_id':file_id,'work_id':work_id,'path':str(path),'duplicate':False,'warnings':warnings}


def download_to_library(library, work_id, index, progress=None, cancelled=None, task_id=None, *, directory=None, expected_url=None):
    work, entry, method = resource(library,work_id,index)
    if method != 'direct': raise ValueError('此资源须使用外部磁力下载器')
    if expected_url is not None and entry['url'] != expected_url: raise ValueError('下载资源已变化，请刷新详情后重试')
    folder=Path(directory) if directory else download_folder(library,work_id); folder.mkdir(parents=True,exist_ok=True)
    task_id=task_id or uuid.uuid4().hex
    payload={'work_id':work_id,'index':index,'directory':str(folder),'bytes':0,'total':0}
    def report(done,total,message):
        elapsed=max(.001,time.monotonic()-report.previous[0]);speed=max(0,done-report.previous[1])/elapsed;report.previous=(time.monotonic(),done)
        payload.update(bytes=done,total=total,message=message,bytes_per_second=round(speed,2))
        if time.monotonic()-report.saved>=.5:
            library.task(task_id,'download-library','running',payload); report.saved=time.monotonic()
        if progress: progress(done,total,message)
    report.saved=0
    report.previous=(time.monotonic(),0)
    library.task(task_id,'download-library','running',payload)
    saved=None
    try:
        saved=download_direct(library,work['metadata'].get('download_plugin'),entry['url'],folder/'video.mp4',report,cancelled,
            resolve_target=lambda headers:folder/video_filename(headers,entry['url'],work['title']))
        payload['path']=saved['path']
        library.task(task_id,'download-library','importing',payload)
        def import_progress(done,total,message):
            payload['message']=message;library.task(task_id,'download-library','importing',payload)
            if progress:progress(done,total,message)
        result=register_download(library,work_id,saved['path'],folder,saved['sha256'],import_progress,cancelled)
        result.update(bytes=saved['bytes'],task_id=task_id)
        library.task(task_id,'download-library','done',payload,result)
        return result
    except Exception as error:
        library.task(task_id,'download-library','cancelled' if isinstance(error,ImportCancelled) else 'partial' if saved else 'failed',payload,error=str(error))
        if saved and not isinstance(error,ImportCancelled): raise ValueError(f"视频已保存到 {saved['path']}，入库未完成：{error}。可在详情页点击“检查下载文件并入库”重试。") from error
        raise


def qbittorrent_executable(library):
    settings=library.setting('downloads',{})
    configured=settings.get('magnet_executable','')
    if configured:
        if not Path(configured).is_file(): raise ValueError('磁力下载器程序不存在，请在下载设置中重新选择')
        return str(configured)
    found=shutil.which('qbittorrent')
    if found: return found
    for variable in ['ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA']:
        base=os.environ.get(variable)
        if base:
            target=Path(base)/'qBittorrent'/'qbittorrent.exe'
            if target.is_file(): return str(target)
    return None


def launch_magnet(library, work_id, index, *, directory=None, expected_url=None):
    work,entry,method=resource(library,work_id,index)
    if method!='magnet' or urlparse(entry['url']).scheme!='magnet': raise ValueError('无效磁力资源')
    if expected_url is not None and entry['url'] != expected_url: raise ValueError('下载资源已变化，请刷新详情后重试')
    folder=Path(directory) if directory else download_folder(library,work_id);folder.mkdir(parents=True,exist_ok=True)
    warnings=write_download_metadata(library,work_id,folder)
    config=library.setting('downloads',{})
    if config.get('magnet_client')=='custom' and not config.get('magnet_executable'): raise ValueError('自定义下载器须指定程序路径')
    executable=qbittorrent_executable(library) if config.get('magnet_client','auto')!='system' else None
    if executable:
        arguments=config.get('magnet_arguments') if config.get('magnet_client')=='custom' else ['--save-path={directory}','--skip-dialog=true','{url}']
        if not isinstance(arguments,list) or not arguments or any(not isinstance(arg,str) for arg in arguments): raise ValueError('下载器参数须为 JSON 字符串数组')
        if not any('{url}' in arg for arg in arguments) or not any('{directory}' in arg for arg in arguments): raise ValueError('自定义下载器参数必须同时包含 {url} 和 {directory}')
        command=[executable,*[arg.replace('{url}',entry['url']).replace('{directory}',str(folder)) for arg in arguments]]
        subprocess.Popen(command,shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        result={'directory':str(folder),'directory_sent':True,'client':Path(executable).name,'warnings':warnings}
    else:
        if config.get('magnet_client') in {'qbittorrent','custom'}: raise ValueError('未找到下载器，请在设置 → 下载中指定程序路径')
        if sys.platform=='win32': os.startfile(entry['url'])
        else: subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',entry['url']],shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        result={'directory':str(folder),'directory_sent':False,'client':'系统默认下载器','warnings':warnings,
                'message':'系统 magnet 协议无法指定目录；请在下载器中选择此目录，或在设置中使用 qBittorrent。'}
    library.task(uuid.uuid4().hex,'magnet','external',{'work_id':work_id,'index':index},result)
    return result


def import_download_folder(library, work_id, progress=None, cancelled=None, *, directory=None):
    from .core import VIDEO_EXTENSIONS
    folder=Path(directory) if directory else download_folder(library,work_id)
    if not folder.is_dir(): raise ValueError('当前下载目录尚不存在')
    files=sorted(path for path in folder.rglob('*') if path.is_file() and not path.is_symlink() and path.suffix.lower() in VIDEO_EXTENSIONS)
    result={'imported':0,'duplicates':0,'errors':[],'work_id':work_id}
    for index,path in enumerate(files):
        check_cancelled(cancelled)
        try:
            attached=register_download(library,work_id,path,folder,cancelled=cancelled)
            result['duplicates' if attached['duplicate'] else 'imported']+=1
        except ImportCancelled: raise
        except Exception as error: result['errors'].append({'path':str(path),'reason':str(error)})
        if progress: progress(index+1,len(files),'检查已完成的下载文件')
    return result


class DownloadQueue:
    """A bounded background queue for authenticated client requests."""
    def __init__(self, directory,budget=None):
        import queue,threading
        self.directory=Path(directory); self.pending=queue.Queue(maxsize=16)
        self.closed=threading.Event();self.lock=threading.Lock();self.active={};self.thread=None
        from .task_journal import TaskBudget
        self.budget=budget or TaskBudget(1);self.threads=[];self.cancelled_ids=set();self.paused=threading.Event()

    def pause(self,paused):
        self.paused.set() if paused else self.paused.clear()

    def cancel(self,identifier):
        with self.lock:
            if identifier not in self.active.values():return False
            self.cancelled_ids.add(identifier);return True

    def cancel_all(self):
        with self.lock:self.cancelled_ids.update(self.active.values())

    def cancelled(self,identifier):
        while self.paused.is_set() and not self.closed.is_set() and identifier not in self.cancelled_ids:self.closed.wait(.1)
        return self.closed.is_set() or identifier in self.cancelled_ids

    def submit(self, work_id, index=None, action='download'):
        import threading
        from .core import Library
        library=Library(self.directory,initialize=False)
        try:
            url=None
            if action=='download':url=resource(library,work_id,index)[1]['url']
            elif action=='import':library.work(work_id)
            else:raise ValueError('无效下载操作')
            key=(work_id,url,action)
            with self.lock:
                if self.closed.is_set():raise ValueError('下载服务正在停止')
                if key in self.active:return self.active[key]
                if self.pending.full():raise ValueError('下载队列已满，请稍后重试')
            task_id=uuid.uuid4().hex;directory=str(download_folder(library,work_id))
            payload={'work_id':work_id,'index':index,'action':action,'directory':directory}
            # SQLite can be busy during import. Never hold the control lock
            # while writing: PC pause/cancel must remain immediate.
            library.task(task_id,'download-library','queued',payload)
            error=None;duplicate=None
            with self.lock:
                if self.closed.is_set():error='下载服务正在停止'
                elif key in self.active:duplicate=self.active[key]
                elif self.pending.full():error='下载队列已满，请稍后重试'
                else:
                    self.active[key]=task_id
                    self.pending.put_nowait((task_id,work_id,index,action,url,directory))
                    if self.thread is None:
                        for index in range(3):
                            worker=threading.Thread(target=self.run,name=f'LumenDownloads-{index}',daemon=True);self.threads.append(worker);worker.start()
                        self.thread=self.threads[0]
            if error:
                library.task(task_id,'download-library','cancelled',payload,error=error);raise ValueError(error)
            if duplicate:
                library.task(task_id,'download-library','cancelled',payload,error='重复请求已合并');return duplicate
            return task_id
        finally:library.close()

    def run(self):
        import queue
        from .core import Library
        while not self.closed.is_set():
            try: task_id,work_id,index,action,url,directory=self.pending.get(timeout=.2)
            except queue.Empty: continue
            library=Library(self.directory,initialize=False)
            library.parent_task_id=task_id
            payload={'work_id':work_id,'index':index,'action':action,'directory':directory}
            acquired=False
            try:
                self.budget.acquire(lambda:self.cancelled(task_id));acquired=True
                check_cancelled(lambda:self.cancelled(task_id))
                if action=='import':
                    result=import_download_folder(library,work_id,cancelled=lambda:self.cancelled(task_id),directory=directory)
                    library.task(task_id,'download-library','done',payload,result)
                elif resource(library,work_id,index)[2]=='magnet':
                    result=launch_magnet(library,work_id,index,directory=directory,expected_url=url)
                    library.task(task_id,'download-library','external',payload,result)
                else: download_to_library(library,work_id,index,cancelled=lambda:self.cancelled(task_id),task_id=task_id,directory=directory,expected_url=url)
            except Exception as error:
                row=library.db.execute('SELECT status,payload FROM tasks WHERE id=?',(task_id,)).fetchone()
                if not row or row['status'] not in {'failed','partial','cancelled'}:
                    library.task(task_id,'download-library','cancelled' if isinstance(error,ImportCancelled) else 'failed',payload,error=str(error))
            finally:
                library.close()
                if acquired:self.budget.release()
                with self.lock:self.active.pop((work_id,url,action),None);self.cancelled_ids.discard(task_id)
                self.pending.task_done()

    def stop(self):
        from .core import Library
        import queue
        self.closed.set()
        while True:
            try: task_id,work_id,index,action,url,directory=self.pending.get_nowait()
            except queue.Empty: break
            library=Library(self.directory,initialize=False)
            try: library.task(task_id,'download-library','cancelled',{'work_id':work_id},error='服务已停止，尚未开始下载')
            finally: library.close()
            self.pending.task_done()
        for thread in self.threads:thread.join(timeout=1)
