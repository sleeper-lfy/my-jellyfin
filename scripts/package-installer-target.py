"""Publish an EXE directly when it fits Git, otherwise preserve it as checked parts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def package(source, destination, revision, direct_limit=99*1024*1024, chunk_size=48*1024*1024):
    source=Path(source);destination=Path(destination)
    with source.open('rb') as stream:
        if stream.read(2)!=b'MZ':raise ValueError('Expected a Windows EXE')
    if not source.stat().st_size:raise ValueError('Empty installer')
    destination.mkdir(parents=True,exist_ok=True)
    name='Lumen-Setup-x64.exe';parts=[];digest=hashlib.sha256()
    if source.stat().st_size<=direct_limit:
        shutil.copyfile(source,destination/name)
        with source.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    else:
        with source.open('rb') as stream:
            while block:=stream.read(chunk_size):
                part=f'{name}.part{len(parts)+1:03}';(destination/part).write_bytes(block);digest.update(block)
                parts.append({'name':part,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()})
    keep={p['name'] for p in parts} if parts else {name}
    for old in destination.glob(name+'*'):
        if old.name not in keep and old.name!=name+'.sha256':old.unlink()
    manifest={'file':name,'source_commit':revision,'bytes':source.stat().st_size,'sha256':digest.hexdigest(),'parts':parts}
    (destination/'windows-installer.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (destination/(name+'.sha256')).write_text(digest.hexdigest()+'  '+name+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination');parser.add_argument('--revision',required=True)
    args=parser.parse_args();package(args.source,args.destination,args.revision)
