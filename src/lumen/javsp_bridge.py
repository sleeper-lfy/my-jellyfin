"""Trusted, explicitly configured local JavSP metadata provider."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
from urllib.parse import urlsplit
from .core import check_cancelled,media_process,ImportCancelled

ID='javsp-local'


def code(value):
    value=str(value or '').strip().upper()
    fc2=re.fullmatch(r'FC2[-_ ]*(?:PPV[-_ ]*)?(\d{5,9})',value)
    if fc2:return 'FC2-PPV-'+fc2[1]
    match=re.fullmatch(r'([A-Z]{2,10})[-_ ]*(\d{2,7})',value)
    if not match:raise ValueError('仅支持明确的影片编号，例如 ABC-123 / FC2-PPV-123456')
    return match[1]+'-'+match[2]


def settings(library):
    value=library.setting('javsp',{})
    return value if isinstance(value,dict) else {}


def validate_settings(value):
    python=Path(value.get('python','')).expanduser()
    root=Path(value.get('root','')).expanduser()
    config=Path(value.get('config','') or root/'config.yml').expanduser()
    if not python.is_absolute() or not python.is_file() or not python.name.lower().startswith('python'):
        raise ValueError('请选择 JavSP 独立环境的 Python 可执行文件，不是 JavSP.exe 或 Lumen.exe')
    if not root.is_absolute() or not (root/'javsp/config.py').is_file() or not (root/'javsp/datatype.py').is_file():
        raise ValueError('请选择包含 javsp/config.py 和 javsp/datatype.py 的 JavSP 项目目录')
    if not config.is_absolute() or not config.is_file():raise ValueError('JavSP config.yml 不存在')
    domains=value.get('image_domains',[])
    if not isinstance(domains,list) or len(domains)>100 or any(not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',host) for host in domains):
        raise ValueError('图片域名须为精确主机名列表，不含协议、端口、通配符或路径')
    # Resolving a venv's python symlink would select the base interpreter and
    # silently discard the environment containing JavSP's dependencies.
    return {'python':str(python.absolute()),'root':str(root.resolve()),'config':str(config.resolve()),'image_domains':list(dict.fromkeys(host.lower() for host in domains))}


def address(value):
    if not isinstance(value,str) or len(value)>4096:return ''
    try:parsed=urlsplit(value)
    except ValueError:return ''
    return value if parsed.scheme in {'http','https'} and parsed.hostname and not parsed.username and not parsed.password else ''


def strings(value,limit=100):
    if isinstance(value,str):value=[value]
    return list(dict.fromkeys(item.strip()[:500] for item in (value or []) if isinstance(item,str) and item.strip()))[:limit] if isinstance(value,(list,tuple)) else []


def normalize(payload,requested):
    identifier=code(requested);valid=[]
    for entry in payload.get('records',[])[:8]:
        if not isinstance(entry,dict):continue
        raw=entry.get('info',{})
        if not isinstance(raw,dict):continue
        try:matched=code(raw.get('dvdid'))==identifier
        except ValueError:matched=False
        if matched and isinstance(raw.get('title'),str) and raw['title'].strip() and address(raw.get('url')):
            valid.append(raw)
    if not valid:
        reasons=', '.join(str(e.get('source',''))+':'+str(e.get('error','failed')) for e in payload.get('errors',[])[:8])
        raise ValueError('JavSP 未返回编号一致的完整资料'+('（'+reasons+'）' if reasons else ''))
    def first(field):return next((item[field] for item in valid if item.get(field)),None)
    released=first('publish_date');released=released[:10] if isinstance(released,str) else ''
    year=int(released[:4]) if re.match(r'^\d{4}-\d{2}-\d{2}$',released) and 1800<=int(released[:4])<=2200 else None
    pictures=next((item.get('actress_pics') for item in valid if isinstance(item.get('actress_pics'),dict)),{})
    actors=[{'name':name,'gender':'female',**({'photo':address(pictures.get(name))} if address(pictures.get(name)) else {})} for name in strings(first('actress'))]
    result={'id':identifier,'title':first('title').strip()[:2000],'kind':'movie','url':address(first('url')),
            'external_ids':{'product_code':identifier},'year':year,'overview':str(first('plot') or '')[:50000],
            'tags':strings(first('genre_norm') or first('genre')),'actors':actors,'directors':strings(first('director')),
            'stills':[url for url in (address(item) for item in (first('preview_pics') or [])[:40]) if url],
            'aliases':strings(first('ori_title'))}
    poster=address(first('big_cover')) or address(first('cover'))
    if poster:result['poster']=poster
    if year:result['released']=released
    if first('producer'):result['studio']=str(first('producer'))[:500]
    try:
        rating=float(first('score'))
        if 0<=rating<=10:result['rating']=rating
    except (TypeError,ValueError):pass
    from .plugins import validate_metadata
    validate_metadata(result)
    return result


def invoke(library,config,request,cancelled=None):
    from .plugins import Plugins
    check_cancelled(cancelled)
    with tempfile.TemporaryDirectory(prefix='javsp-',dir=library.directory) as temporary:
        source,target=Path(temporary)/'request.json',Path(temporary)/'response.json'
        source.write_text(json.dumps({**config,**request}),encoding='utf-8')
        worker=Plugins.builtin_numbered_plugin(ID)/'bridge.py'
        try:media_process([config['python'],'-I',str(worker),str(source),str(target)],180,cancelled)
        except subprocess.TimeoutExpired as error:
            raise ValueError('JavSP 抓取超过 180 秒，请减少配置来源或检查网络后重试') from error
        except (subprocess.CalledProcessError,OSError) as error:
            raise ValueError('JavSP Python 进程启动失败或异常退出，请检查独立环境') from error
        if not target.is_file() or target.stat().st_size>4_000_000:raise ValueError('JavSP 未返回有效响应')
        data=json.loads(target.read_text(encoding='utf-8'))
        if data.get('error'):raise ValueError(str(data['error'])[:1000])
        check_cancelled(cancelled)
        return data


def probe(library,value,cancelled=None):
    return invoke(library,validate_settings(value),{'probe':True},cancelled)


def run(library,operation,parameters,cancelled=None):
    check_cancelled(cancelled)
    config=validate_settings(settings(library));folder=library.directory/'cache/javsp';folder.mkdir(exist_ok=True,parents=True)
    stat=Path(config['config']).stat()
    fingerprint=hashlib.sha256(json.dumps([config,stat.st_size,stat.st_mtime_ns],sort_keys=True).encode()).hexdigest()
    def cache_path(value):return folder/(hashlib.sha256(value.encode()).hexdigest()+'.json')
    def read(value):
        path=cache_path(value)
        if not path.is_file() or path.stat().st_size>4_000_000:return None
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            if item['config']==fingerprint and 0<=time.time()-item['created']<600:
                from .plugins import validate_metadata
                validate_metadata(item['record'])
                return item['record']
        except (ValueError,KeyError,TypeError):pass
        return None
    if operation=='detail':
        item=read('url:'+parameters.get('url',''))
        if item is None:raise ValueError('JavSP 候选已过期，请重新按编号搜索')
        from .plugins import validate_metadata
        validate_metadata(item)
        if parameters.get('refresh'):
            return run(library,'search',{'query':item['id'],'refresh':True},cancelled)
        return [item]
    if operation!='search':raise ValueError('JavSP 辅助引擎仅支持编号搜索与详情')
    identifier=code(parameters.get('query',''));cached=None if parameters.get('refresh') else read('code:'+identifier)
    if cached:return [cached]
    task_id=uuid.uuid4().hex;payload={'plugin':ID,'operation':operation,'parameters':{'query':identifier}}
    library.task(task_id,'scrape','running',payload)
    try:
        check_cancelled(cancelled)
        record=normalize(invoke(library,config,{'code':identifier},cancelled),identifier)
        check_cancelled(cancelled)
        encoded=json.dumps({'config':fingerprint,'created':time.time(),'record':record},ensure_ascii=False)
        for key in ('code:'+identifier,'url:'+record['url']):
            path=cache_path(key);temp=path.with_suffix('.'+uuid.uuid4().hex+'.partial');temp.write_text(encoded,encoding='utf-8');temp.replace(path)
        library.task(task_id,'scrape','done',payload,{'count':1});return [record]
    except Exception as error:
        library.task(task_id,'scrape','cancelled' if isinstance(error,ImportCancelled) else 'failed',payload,error=str(error));raise
