"""Split a verified Windows ZIP into GitHub-compatible, checksummed parts."""
import argparse
import hashlib
import json
from pathlib import Path


def package(source, destination, revision, chunk_size=48*1024*1024):
    source=Path(source);destination=Path(destination)
    if not source.is_file():raise FileNotFoundError(source)
    destination.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256();parts=[]
    with source.open('rb') as stream:
        while block:=stream.read(chunk_size):
            name=f'Lumen-windows-x64.zip.part{len(parts)+1:03}'
            (destination/name).write_bytes(block)
            digest.update(block)
            parts.append({'name':name,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()})
    if not parts:raise ValueError('Empty package')
    for old in destination.glob('Lumen-windows-x64.zip.part*'):
        if old.name not in {p['name'] for p in parts}:old.unlink()
    manifest={'file':'Lumen-windows-x64.zip','source_commit':revision,'bytes':source.stat().st_size,'sha256':digest.hexdigest(),'parts':parts}
    (destination/'windows-package.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination');parser.add_argument('--revision',required=True)
    args=parser.parse_args();package(args.source,args.destination,args.revision)
