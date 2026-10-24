"""Download both published installers and verify against the committed manifests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import httpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);args=parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+',args.tag):raise ValueError('Invalid release tag')
    windows=json.loads(Path('target/windows-installer.json').read_text());android=json.loads(Path('target/android-build.json').read_text())
    assert android['version']==args.tag[1:] and windows['source_commit']==android['source_commit']
    directory=Path('.local/packages')/args.tag[1:];directory.mkdir(parents=True,exist_ok=True)
    base='https://github.com/sleeper-lfy/my-jellyfin/releases/download/'+args.tag+'/'
    def download(pair):
        name,manifest=pair;path=directory/name;sha=hashlib.sha256();count=0
        with httpx.Client(follow_redirects=True,timeout=120) as client:
            checksum=client.get(base+name+'.sha256');checksum.raise_for_status()
            assert checksum.text.lstrip('\ufeff').split()[0].lower()==manifest['sha256']
            with client.stream('GET',base+name) as response:
                response.raise_for_status()
                with path.open('wb') as output:
                    for block in response.iter_bytes(1024*1024):
                        count+=len(block)
                        if count>manifest['bytes']:raise ValueError('Oversized asset '+name)
                        sha.update(block);output.write(block)
        assert count==manifest['bytes'] and sha.hexdigest()==manifest['sha256'], name
        (directory/(name+'.sha256')).write_bytes(checksum.content)
        print('Verified public download:',name,count,sha.hexdigest(),flush=True)
        return {'file':name,'url':base+name,'bytes':count,'sha256':sha.hexdigest(),'public_download_verified':True}
    with ThreadPoolExecutor(max_workers=2) as executor:
        assets=list(executor.map(download,[('Lumen-Setup-x64.exe',windows),('Lumen-android-debug.apk',android)]))
    result={'tag':args.tag,'source_commit':windows['source_commit'],'verified_at':datetime.now(timezone.utc).isoformat(),'release_url':'https://github.com/sleeper-lfy/my-jellyfin/releases/tag/'+args.tag,'assets':assets}
    Path('target/release-download-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
