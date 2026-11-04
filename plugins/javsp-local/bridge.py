"""Standalone stdlib bridge, executed by the user's JavSP Python installation.

No JavSP implementation is vendored. Import only its config, data type and
configured crawlers; never import __main__ or pass media paths to the engine.
"""
import contextlib
import importlib
import json
import os
from pathlib import Path
import re
import sys


def code(value):
    value=str(value or '').strip().upper()
    fc2=re.fullmatch(r'FC2[-_ ]*(?:PPV[-_ ]*)?(\d{5,9})',value)
    if fc2:return 'FC2-PPV-'+fc2[1]
    match=re.fullmatch(r'([A-Z]{2,10})[-_ ]*(\d{2,7})',value)
    if not match:raise ValueError('仅支持明确的影片编号，例如 ABC-123 / FC2-PPV-123456')
    return match[1]+'-'+match[2]


def collect(request):
    root=Path(request['root']).resolve();config=Path(request['config']).resolve()
    sys.path.insert(0,str(root))
    sys.argv=['javsp','-c',str(config)]
    from javsp.config import Cfg
    from javsp.datatype import MovieInfo
    cfg=Cfg()
    if request.get('probe'):
        return {'ready':True,'sources':{key:[getattr(item,'value',str(item)) for item in cfg.crawler.selection[key]][:8] for key in ('normal','fc2')}}
    identifier=code(request['code'])
    names=cfg.crawler.selection['fc2' if identifier.startswith('FC2-PPV-') else 'normal']
    records=[];errors=[]
    for entry in names[:8]:
        name=getattr(entry,'value',entry)
        if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_]{2,30}',name):continue
        try:
            parser=importlib.import_module('javsp.web.'+name).parse_data
            info=MovieInfo(identifier.replace('FC2-PPV-','FC2-'))
            parser(info)
            raw=vars(info)
            if code(raw.get('dvdid'))!=identifier:raise ValueError('编号不一致')
            if not raw.get('title') or not raw.get('url'):raise ValueError('资料不完整')
            records.append({'source':name,'info':{key:raw.get(key) for key in (
                'dvdid','url','title','ori_title','plot','cover','big_cover','genre','genre_norm','score',
                'actress','actress_pics','director','producer','publisher','publish_date','preview_pics')}})
        except Exception as error:
            # Upstream errors may contain configured credentials; export only type.
            errors.append({'source':name,'error':type(error).__name__})
    return {'records':records,'errors':errors}


def main():
    request_path,response_path=map(Path,sys.argv[1:])
    try:
        if request_path.stat().st_size>16000:raise ValueError('输入过大')
        request=json.loads(request_path.read_text(encoding='utf-8'))
        with open(os.devnull,'w') as quiet,contextlib.redirect_stdout(quiet),contextlib.redirect_stderr(quiet):
            result=collect(request)
        text=json.dumps(result,ensure_ascii=False)
        if len(text.encode('utf-8'))>4_000_000:raise ValueError('输出过大')
    except Exception as error:
        text=json.dumps({'error':'JavSP 启动或配置失败（'+type(error).__name__+'），请检查独立 Python 环境及 config.yml'},ensure_ascii=False)
    response_path.write_text(text,encoding='utf-8')


if __name__=='__main__':main()
