"""Explicit source fallback and diagnostic checks without silently accepting a guess."""
import time
from .core import check_cancelled, ImportCancelled
from .plugins import Plugins


class SourceLookupError(Exception):
    def __init__(self, message, attempts, candidates=None, plugin='', retryable=False):
        super().__init__(message)
        self.attempts=attempts;self.candidates=candidates or [];self.plugin=plugin;self.retryable=retryable


def source_order(primary, fallbacks):
    if not isinstance(fallbacks,list):fallbacks=[]
    return list(dict.fromkeys(value for value in [primary,*fallbacks] if isinstance(value,str) and value))[:8]


def resolve(library, work, primary, fallbacks=None, cancelled=None):
    from .ingestion import choose, work_codes, NeedsConfirmation
    identifiers=work_codes(work)
    if len(identifiers)>1:raise NeedsConfirmation('文件含多个编号，请确认作品归组')
    query=next(iter(identifiers)) if identifiers else work['title']
    manager=Plugins(library);installed={p['id']:p for p in manager.installed()}
    attempts=[];pending=[];pending_plugin='';transient=False
    for identifier in source_order(primary,fallbacks or []):
        check_cancelled(cancelled)
        plugin=installed.get(identifier)
        if not plugin or not plugin['config'].get('enabled') or 'search' not in plugin['capabilities']:
            attempts.append({'plugin':identifier,'state':'unavailable','message':'来源未启用或不支持影片搜索'});continue
        candidates=[]
        try:
            candidates=manager.run(identifier,'search',query=query,**({'cancelled':cancelled} if cancelled else {}))
            candidate=choose(work,candidates)
            if 'detail' in plugin['capabilities']:
                details=manager.run(identifier,'detail',url=candidate['url'],**({'cancelled':cancelled} if cancelled else {}))
                exact=[item for item in details if str(item['id'])==str(candidate['id'])]
                if len(exact)!=1:raise NeedsConfirmation('详情来源标识不一致')
                candidate=exact[0]
                # The detailed document cannot change a numbered candidate's identity.
                if identifiers:choose(work,[candidate])
            attempts.append({'plugin':identifier,'state':'matched','message':'唯一匹配并读取资料'})
            return {'plugin':identifier,'candidate':candidate,'attempts':attempts}
        except ImportCancelled:raise
        except NeedsConfirmation as error:
            attempts.append({'plugin':identifier,'state':'confirmation','message':str(error)})
            if candidates and not pending:pending=candidates[:40];pending_plugin=identifier
        except Exception as error:
            transient=transient or getattr(error,'retryable',True)
            attempt={'plugin':identifier,'state':'failed','message':str(error)[:1000]}
            if hasattr(error,'reason'):attempt.update(reason=error.reason,http_status=error.status)
            attempts.append(attempt)
    message='；'.join(row['plugin']+'：'+row['message'] for row in attempts) or '未配置可用影片来源'
    raise SourceLookupError(message,attempts,pending,pending_plugin,transient and not pending)


def check_source(library, plugin_id, query, cancelled=None):
    """A search/detail probe, not a mere HTTP 200 check; does not merge results."""
    from .ingestion import codes
    identifiers=codes(query)
    if len(identifiers)!=1:raise ValueError('请输入一个用于检测的影片编号')
    code=next(iter(identifiers));started=time.monotonic()
    work={'title':code,'kind':'movie','year':None,'files':[]}
    try:
        result=resolve(library,work,plugin_id,[],cancelled)
        value={'state':'available','message':'搜索与详情解析通过','title':result['candidate']['title'],'matched':True}
    except SourceLookupError as error:
        state='failed' if error.retryable or not error.attempts or any(row['state'] in {'failed','unavailable'} for row in error.attempts) else 'no_unique_match'
        value={'state':state,'message':str(error),'matched':False}
        value['attempts']=error.attempts
    value.update(plugin=plugin_id,query=code,checked_at=time.time(),seconds=round(time.monotonic()-started,2))
    library.set_setting('source-health:'+plugin_id,value)
    return value
