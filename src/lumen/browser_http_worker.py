"""Short-lived TLS-compatible GET worker. No browser, model or persistent daemon."""
import json
from pathlib import Path
import sys
import time


def perform(request,target):
    from curl_cffi import requests
    # Parent enforces the plugin's host allowlist on every redirect. The worker
    # performs a single GET and never forwards credentials through redirects.
    with requests.Session(impersonate='chrome',trust_env=False) as client:
        response=client.get(request['url'],headers=request['headers'],proxy=request.get('proxy') or None,
                            timeout=20,allow_redirects=False,stream=True)
        try:
            size=0;deadline=time.monotonic()+20
            with target.open('wb') as output:
                for block in response.iter_content(chunk_size=65536):
                    size+=len(block)
                    if size>request['maximum'] or time.monotonic()>deadline:raise ValueError('响应大小或时间超限')
                    output.write(block)
            names={'content-type','location','cf-mitigated','server','retry-after','www-authenticate'}
            return {'status':response.status_code,'headers':{key.lower():value for key,value in response.headers.items() if key.lower() in names}}
        finally:response.close()


def main():
    source,result,body=map(Path,sys.argv[-3:])
    try:
        if source.stat().st_size>32000:raise ValueError('请求过大')
        request=json.loads(source.read_text(encoding='utf-8'))
        value=perform(request,body)
    except ImportError:value={'error':'当前安装缺少浏览器兼容请求组件，请更新完整安装包或选择标准请求模式'}
    except ValueError:value={'error':'兼容请求的响应大小或时间超限'}
    except Exception as error:
        # Upstream exception strings may expose URLs, proxy passwords or Cookie.
        value={'error':'浏览器兼容请求失败（'+type(error).__name__+'），请检查代理和网络后重试'}
    result.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':main()
