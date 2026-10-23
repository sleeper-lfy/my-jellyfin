"""Bounded LAN commands; all player operations execute on the Qt GUI thread."""
import copy
import queue
import threading
import time
import uuid
from PySide6.QtCore import QObject,QTimer
from PySide6.QtMultimedia import QMediaPlayer,QMediaMetaData


def validate_command(body):
    if not isinstance(body,dict): raise ValueError('无效遥控命令')
    action=body.get('action')
    if action not in {'open','toggle','play','pause','seek','jump','volume','mute','audio','subtitle'}: raise ValueError('不支持的遥控命令')
    allowed={'action'}|{'open':{'work_id','file_id'},'seek':{'value'},'jump':{'value'},'volume':{'value'},'mute':{'value'},'audio':{'value'},'subtitle':{'value'}}.get(action,set())
    if not body.keys() <= allowed: raise ValueError('无效遥控参数')
    if action=='open':
        if type(body.get('work_id')) is not int or body['work_id']<=0 or type(body.get('file_id',0)) is not int or body.get('file_id',0)<0: raise ValueError('无效影片编号')
    elif action in {'seek','jump','volume','audio','subtitle'}:
        import math
        value=body.get('value');low,high={'seek':(0,864000),'jump':(-600,600),'volume':(0,100),'audio':(-1,1000),'subtitle':(-2,1000)}[action]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high: raise ValueError('遥控参数超出范围')
        if action in {'audio','subtitle'} and type(value) is not int: raise ValueError('轨道编号须为整数')
    elif action=='mute' and type(body.get('value')) is not bool: raise ValueError('无效静音参数')
    return dict(body)


class DesktopRemote(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.pending=queue.Queue(32);self.lock=threading.Lock();self.snapshot={'available':False};self.result={}
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.pump);self.timer.start()
    def submit(self,body):
        command=validate_command(body);identifier=uuid.uuid4().hex
        try: self.pending.put_nowait((identifier,time.monotonic(),command))
        except queue.Full: raise ValueError('遥控命令过多，请稍后重试')
        return identifier
    def state(self):
        with self.lock:return copy.deepcopy(self.snapshot)
    def clear(self):
        while True:
            try:self.pending.get_nowait()
            except queue.Empty:break
    def pump(self):
        enabled=not self.window._closing and self.window.library.setting('remote_enabled',False)
        player=self.window.player
        for _ in range(8):
            try:identifier,created,command=self.pending.get_nowait()
            except queue.Empty:break
            try:
                if not enabled or time.monotonic()-created>10:raise ValueError('遥控已关闭或命令已过期')
                action=command['action'];value=command.get('value')
                if action=='open':
                    work=self.window.library.work(command['work_id'])
                    file=next((f for f in work['files'] if f['id']==command.get('file_id')),None) if command.get('file_id') else self.window.library.resume_file(work['id'])
                    if file is None:raise ValueError('影片没有此视频')
                    self.window.play_file(file)
                    if not player.file or player.file['id']!=file['id']:raise ValueError('视频文件离线或已移动')
                elif not player.isVisible() or not player.file:raise ValueError('电脑当前没有播放视频')
                elif action=='toggle':player.toggle()
                elif action=='play':player.media.play()
                elif action=='pause':player.media.pause()
                elif action=='jump':player.jump(int(value*1000))
                elif action=='seek':player.timeline.setValue(min(player.media.duration(),int(value*1000)));player.seek()
                elif action=='volume':player.volume.setValue(int(value))
                elif action=='mute':player.audio.setMuted(value)
                elif action in {'audio','subtitle'}:
                    tracks=player.media.audioTracks() if action=='audio' else player.media.subtitleTracks()
                    if not (-1<=value<len(tracks) or action=='subtitle' and value==-2 and player.cues):raise ValueError('轨道不存在')
                    (player.media.setActiveAudioTrack if action=='audio' else player.select_subtitle)(value)
                self.result={'id':identifier,'ok':True}
            except Exception as exc:self.result={'id':identifier,'ok':False,'error':str(exc)}
        file=player.file if player.isVisible() else None
        def tracks(items):
            return [{'index':i,'name':track.stringValue(QMediaMetaData.Key.Title) or track.stringValue(QMediaMetaData.Key.Language) or str(i+1)} for i,track in enumerate(items)]
        value={'available':bool(enabled),'active':bool(file),'work_id':file['work_id'] if file else None,'file_id':file['id'] if file else None,
               'title':player.title.text() if file else '', 'position':player.media.position()/1000 if file else 0,
               'duration':player.media.duration()/1000 if file else 0,'playing':bool(file and player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState),
               'volume':player.volume.value(),'muted':player.audio.isMuted(),'audio':tracks(player.media.audioTracks()) if file else [],
               'subtitles':([{'index':-2,'name':'外挂字幕'}] if file and player.cues else [])+(tracks(player.media.subtitleTracks()) if file else []),'last_command':self.result}
        with self.lock:self.snapshot=value
