"""Shared validation for GUI and Qt-free desktop remote routing."""

def validate_command(body):
    if not isinstance(body,dict): raise ValueError('无效遥控命令')
    action=body.get('action')
    if action not in {'open','toggle','play','pause','seek','jump','volume','mute','audio','subtitle','shutdown','shutdown_cancel'}: raise ValueError('不支持的遥控命令')
    allowed={'action'}|{'open':{'work_id','file_id'},'seek':{'value'},'jump':{'value'},'volume':{'value'},'mute':{'value'},'audio':{'value'},'subtitle':{'value'},'shutdown':{'confirm'}}.get(action,set())
    if not body.keys() <= allowed: raise ValueError('无效遥控参数')
    if action=='shutdown' and body.get('confirm') is not True:raise ValueError('请在手机上确认关机')
    if action=='open':
        if type(body.get('work_id')) is not int or body['work_id']<=0 or type(body.get('file_id',0)) is not int or body.get('file_id',0)<0: raise ValueError('无效影片编号')
    elif action in {'seek','jump','volume','audio','subtitle'}:
        import math
        value=body.get('value');low,high={'seek':(0,864000),'jump':(-600,600),'volume':(0,100),'audio':(-1,1000),'subtitle':(-2,1000)}[action]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high: raise ValueError('遥控参数超出范围')
        if action in {'audio','subtitle'} and type(value) is not int: raise ValueError('轨道编号须为整数')
    elif action=='mute' and type(body.get('value')) is not bool: raise ValueError('无效静音参数')
    return dict(body)
