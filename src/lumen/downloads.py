"""User-started downloads: stream to a temporary file, then atomically publish."""
from pathlib import Path
from urllib.parse import urlparse
import os
import uuid
import time
import httpx
from .core import ImportCancelled, check_cancelled


def download_direct(library, plugin_id, url, target, progress=None, cancelled=None, overwrite=False):
    from .plugins import Plugins
    plugin=next((item for item in Plugins(library).installed() if item['id']==plugin_id),None)
    parsed=urlparse(url)
    if plugin is None or parsed.scheme not in {'http','https'} or parsed.hostname not in plugin['domains'] or parsed.username or parsed.password:
        raise ValueError('下载地址不在插件声明的 HTTP/HTTPS 域名内')
    target=Path(target)
    if target.exists() and not overwrite:raise ValueError('目标文件已存在')
    task_id=uuid.uuid4().hex
    temporary=target.with_name(target.name+'.'+task_id+'.part')
    payload={'url':url,'plugin':plugin_id,'target':str(target),'bytes':0,'total':0}
    library.task(task_id,'download','running',payload)
    proxy=plugin['config'].get('proxy','inherit')
    if proxy=='inherit':proxy=library.setting('proxy','')
    count=0
    last_saved=time.monotonic()
    try:
        check_cancelled(cancelled)
        with httpx.Client(proxy=proxy or None,trust_env=False,timeout=httpx.Timeout(30,connect=20),follow_redirects=False) as client:
            with client.stream('GET',url,headers={'User-Agent':'Lumen/0.4','Accept-Encoding':'identity'}) as response:
                response.raise_for_status()
                if response.is_redirect:raise ValueError('下载重定向被拒绝，请让插件返回最终下载地址')
                total=int(response.headers.get('content-length','0'))
                payload['total']=total
                with temporary.open('xb') as stream:
                    for block in response.iter_bytes(256*1024):
                        check_cancelled(cancelled)
                        stream.write(block);count+=len(block);payload['bytes']=count
                        if time.monotonic()-last_saved>=1:
                            library.task(task_id,'download','running',payload)
                            last_saved=time.monotonic()
                        if progress:progress(count,total,f'下载 {count/1048576:.1f} MB'+(f' / {total/1048576:.1f} MB' if total else ''))
                if total and count!=total:raise ValueError('下载长度与服务器声明不符')
        check_cancelled(cancelled)
        if target.exists() and not overwrite:raise ValueError('目标文件已存在')
        os.replace(temporary,target)
        library.task(task_id,'download','done',payload,{'path':str(target),'bytes':count})
        return {'path':str(target),'bytes':count}
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        library.task(task_id,'download','cancelled' if isinstance(exc,ImportCancelled) else 'failed',payload,error=str(exc))
        raise
