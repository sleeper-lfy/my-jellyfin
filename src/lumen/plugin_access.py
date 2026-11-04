"""Host-owned site sessions and actionable HTTP failures; never passed to JS."""
from urllib.parse import urlsplit


def origin(url):
    try:
        part=urlsplit(url)
        if part.scheme not in {'http','https'} or not part.hostname or part.username or part.password:return ''
        port=part.port or (443 if part.scheme=='https' else 80)
        return f'{part.scheme}://{part.hostname.lower()}:{port}'
    except (ValueError,TypeError):return ''


def session(library,plugin):
    if not plugin.get('id'):return {}
    value=library.setting('plugin-access:'+plugin.get('id',''),{})
    return value if isinstance(value,dict) else {}


def save_session(library,plugin,values):
    selected=values.get('transport','auto')
    if selected not in {'auto','browser','standard'}:raise ValueError('无效请求模式')
    cookie=values.get('cookie','').strip();agent=values.get('user_agent','').strip()
    for name,value,maximum in [('Cookie',cookie,16000),('User-Agent',agent,2000)]:
        if len(value)>maximum or any(ord(char)<32 or ord(char)>126 for char in value):
            raise ValueError(name+' 须为单行 ASCII 请求头内容，不含换行')
    site=plugin['config'].get('base_url','');scoped=origin(site)
    if not scoped or urlsplit(site).hostname not in plugin['domains']:raise ValueError('请先保存属于插件允许域名的站点地址')
    library.set_setting('plugin-access:'+plugin['id'],{'transport':selected,'origin':scoped,'cookie':cookie,'user_agent':agent})


def request_headers(library,plugin,url,defaults):
    headers=dict(defaults);settings=session(library,plugin)
    base=plugin['config'].get('base_url','')
    # Sessions belong to an exact scheme/host/port, never an entire plugin's
    # allowlist (which may also contain image CDNs or third-party services).
    if settings.get('origin')==origin(url)==origin(base):
        if settings.get('cookie'):headers['Cookie']=settings['cookie']
        if settings.get('user_agent'):headers['User-Agent']=settings['user_agent']
    if origin(base):
        part=urlsplit(base)
        # Keep Referer free of userinfo, query strings and fragments.
        headers['Referer']=f'{part.scheme}://{part.netloc}/'
    return headers


class PluginHttpError(ValueError):
    def __init__(self,status,reason,host,message,retryable=False):
        self.status=status;self.reason=reason;self.host=host;self.retryable=retryable
        super().__init__(f'{host}：HTTP {status}，'+message)


def check_response(status,headers,body,url):
    host=urlsplit(url).hostname or '来源'
    headers={str(key).lower():str(value) for key,value in headers.items()}
    snippet=body[:65536].decode('utf-8','replace').lower()
    challenge=(headers.get('cf-mitigated','').lower()=='challenge' or
               any(marker in snippet for marker in ('__cf_chl','challenge-platform','challenge-running','verifying you are human','<title>just a moment')))
    if challenge:
        raise PluginHttpError(status,'verification_required',host,'站点要求浏览器验证。可在“站点访问设置”配置浏览器兼容请求；仍失败时，在相同网络出口的浏览器完成验证，并按需填写该站点的 Cookie 与 User-Agent。')
    if status in {401,403}:
        login=status==401 or any(marker in snippet for marker in ('login required','please log in','需要登入','需要登录','請先登入','请先登录'))
        reason='login_required' if login else 'access_denied'
        message='站点要求登录，请在“站点访问设置”填写有效的站点会话。' if login else '站点拒绝访问；请检查插件代理与浏览器网络出口、站点地址及会话。更换解析器不能保证解决此错误。'
        raise PluginHttpError(status,reason,host,message)
    if status==429:
        raise PluginHttpError(status,'rate_limited',host,'站点请求过于频繁，请稍后重试或降低后台并发。',True)
    if status>=400 or status<100:
        raise PluginHttpError(status,'http_error',host,'来源请求失败，请检查站点状态。',status>=500 or status==0)
