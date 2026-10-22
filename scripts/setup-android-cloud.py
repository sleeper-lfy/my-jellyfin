from pathlib import Path
import httpx,hashlib,zipfile,tarfile,xml.etree.ElementTree as ET,os
repository=Path(__file__).resolve().parents[1]
root=repository/'.local/android-tools';root.mkdir(exist_ok=True,parents=True)
client=httpx.Client(follow_redirects=True,timeout=120)
def download(url,target,algorithm,expected):
 if target.exists() and hashlib.new(algorithm,target.read_bytes()).hexdigest()==expected:return
 with client.stream('GET',url) as response:
  response.raise_for_status()
  with target.open('wb') as out:
   for chunk in response.iter_bytes():out.write(chunk)
 assert hashlib.new(algorithm,target.read_bytes()).hexdigest()==expected, 'Checksum mismatch: '+target.name
 print('Verified',target.name,flush=True)
jdkurl='https://download.oracle.com/java/21/archive/jdk-21.0.8_linux-x64_bin.tar.gz'
checksum=client.get(jdkurl+'.sha256');checksum.raise_for_status()
archive=root/'jdk.tar.gz';download(jdkurl,archive,'sha256',checksum.text.strip().split()[0])
if not list(root.glob('jdk-*/bin/javac')):
 with tarfile.open(archive) as f:f.extractall(root,filter='data')
gradleurl='https://services.gradle.org/distributions/gradle-8.11.1-bin.zip'
checksum=client.get(gradleurl+'.sha256');checksum.raise_for_status()
archive=root/'gradle.zip';download(gradleurl,archive,'sha256',checksum.text.strip())
if not (root/'gradle-8.11.1').exists():
 with zipfile.ZipFile(archive) as f:f.extractall(root)
(root/'gradle-8.11.1/bin/gradle').chmod(0o755)
response=client.get('https://dl.google.com/android/repository/repository2-1.xml');response.raise_for_status()
xml=ET.fromstring(response.content)
for element in xml.iter():element.tag=element.tag.split('}')[-1]
sdk=root/'sdk';sdk.mkdir(exist_ok=True)
for packageid,folder in [('platforms;android-36','platforms/android-36'),('build-tools;35.0.0','build-tools/35.0.0'),('platform-tools','platform-tools')]:
 package=next(p for p in xml.findall('remotePackage') if p.get('path')==packageid and '-ext' not in p.findtext('display-name',''))
 chosen=next(a for a in package.findall('./archives/archive') if a.findtext('host-os') in (None,'linux'))
 complete=chosen.find('complete');checksum=complete.find('checksum')
 url='https://dl.google.com/android/repository/'+complete.findtext('url')
 archive=root/(packageid.replace(';','-')+'.zip')
 download(url,archive,checksum.get('type','sha1'),checksum.text.strip())
 target=sdk/folder
 if not target.exists():
  staging=root/('unpack-'+packageid.replace(';','-'));staging.mkdir(exist_ok=True)
  with zipfile.ZipFile(archive) as f:
   f.extractall(staging)
   for item in f.infolist():
    mode=item.external_attr>>16
    if mode and not item.is_dir(): (staging/item.filename).chmod(mode & 0o777)
  children=list(staging.iterdir());assert len(children)==1
  target.parent.mkdir(exist_ok=True,parents=True);children[0].rename(target)
 license_node=package.find('uses-license')
 if license_node is not None:
  license=next(x for x in xml.findall('license') if x.get('id')==license_node.get('ref'))
  text=''.join(license.itertext()).strip()
  (sdk/'licenses').mkdir(exist_ok=True)
  path=sdk/'licenses'/license.get('id')
  existing=path.read_text() if path.exists() else ''
  digest=hashlib.sha1(text.encode()).hexdigest()
  if digest not in existing:path.write_text(existing+'\n'+digest+'\n')
print('Android build tools ready',flush=True)
