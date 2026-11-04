"""Read-only version inspection and explicit preferred playback selection."""
import json
from pathlib import Path
from .core import check_cancelled, media_process, tool, ImportCancelled


def set_preferred(library,work_id,file_id):
    work=library.work(work_id)
    if work['kind'] not in {'movie','vr'}:raise ValueError('电视剧按季集续播，不设置整部默认版本')
    if file_id is not None:
        if type(file_id) is not int or not any(file['id']==file_id for file in work['files']):raise ValueError('视频不属于此影片')
        path=Path(next(file['path'] for file in work['files'] if file['id']==file_id))
        if not path.is_file():raise ValueError('此版本当前离线，不能设为默认')
    library.set_setting('preferred-file:'+str(work_id),file_id)


def inspect_versions(library,work_ids,progress=None,cancelled=None):
    records=[]
    works=[library.work(identifier) for identifier in dict.fromkeys(work_ids)]
    total=sum(len(work['files']) for work in works)
    for work in works:
        work_id=work['id']
        check_cancelled(cancelled)
        for file in work['files']:
            check_cancelled(cancelled)
            row={**file,'title':work['title'],'kind':work['kind'],'default':library.setting('preferred-file:'+str(work_id))==file['id'],
                 'resolution':'','codec':'','audio':'','subtitles':'','size':None,'error':''}
            path=Path(file['path'])
            try:
                before=path.stat();row['size']=before.st_size
                signature=[str(path),before.st_size,before.st_mtime_ns]
                key='stream-profile:'+str(file['id']);cache=library.setting(key,{})
                if cache.get('signature')!=signature:
                    executable=tool('ffprobe')
                    if not executable:raise ValueError('未配置 FFprobe，可在设置中安装媒体工具后重试')
                    if progress:progress(len(records),total,'读取版本信息 · '+path.name)
                    output=media_process([executable,'-v','error','-protocol_whitelist','file,pipe,crypto,data','-show_format','-show_streams','-of','json',str(path)],45,cancelled)
                    data=json.loads(output.stdout)
                    after=path.stat()
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('读取期间文件已变化，请重试')
                    streams=data.get('streams',[]);video=next((stream for stream in streams if stream.get('codec_type')=='video' and not stream.get('disposition',{}).get('attached_pic')), {})
                    cache={'signature':signature,'resolution':f"{video.get('width','?')}×{video.get('height','?')}",
                           'codec':video.get('codec_name','未知'),'duration':float(data.get('format',{}).get('duration') or file['duration']),
                           'audio':' / '.join(str(stream.get('codec_name','?'))+' '+str(stream.get('tags',{}).get('language','')) for stream in streams if stream.get('codec_type')=='audio'),
                           'subtitles':' / '.join(str(stream.get('tags',{}).get('language') or stream.get('codec_name','未知')) for stream in streams if stream.get('codec_type')=='subtitle')}
                    library.set_setting(key,cache)
                row.update({k:v for k,v in cache.items() if k!='signature'})
                external=[p.name for p in path.parent.iterdir() if p.is_file() and p.suffix.lower() in {'.srt','.ass','.ssa','.vtt','.sub'} and (p.stem==path.stem or p.name.startswith(path.stem+'.'))]
                if external:row['subtitles']+=' · 外挂：'+'、'.join(external)
            except ImportCancelled:raise
            except Exception as error:row['error']=str(error)
            records.append(row)
    return records


def duplicate_candidates(library):
    """Group evidence; equal codes are possible versions, never proof of equal content."""
    from .ingestion import work_codes
    codes={};digests={};groups=[]
    for work in library.query({'kinds':['movie','vr']}):
        identifiers=work_codes(work)
        if len(identifiers)==1:codes.setdefault(next(iter(identifiers)),set()).add(work['id'])
        for file in work['files']:
            cache=library.db.execute('SELECT full FROM import_cache WHERE file_id=?',(file['id'],)).fetchone()
            digest=(cache['full'] if cache else None) or file['digest']
            if digest and not digest.startswith('fast-'):digests.setdefault(digest,[]).append((work['id'],file['id']))
    for code,ids in codes.items():
        if len(ids)>1:groups.append({'label':'相同编号 '+code+'（请核对版本）','work_ids':sorted(ids),'basis':'code'})
    for digest,files in digests.items():
        if len(files)>1:groups.append({'label':f'已记录相同完整指纹 · {len(files)} 个文件（删除前需重新核对）','work_ids':list(dict.fromkeys(work for work,file in files)),'basis':'digest'})
    return groups
