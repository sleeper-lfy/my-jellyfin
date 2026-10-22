import os,subprocess,sys
from pathlib import Path
from urllib.parse import urlsplit
repository=Path(__file__).resolve().parents[1]
root=repository/'.local/android-tools'
environment=dict(os.environ)
environment['JAVA_HOME']=str(next(root.glob('jdk-*')))
environment['ANDROID_USER_HOME']=str(root/'android-user')
(root/'android-user').mkdir(exist_ok=True)
environment['ANDROID_HOME']=str(root/'sdk')
environment['ANDROID_SDK_ROOT']=str(root/'sdk')
environment['GRADLE_USER_HOME']=str(root/'gradle-home')
environment['PATH']=environment['JAVA_HOME']+'/bin:'+environment['PATH']
options=[]
proxy=urlsplit(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
if proxy.hostname:
 for protocol in ['http','https']:
  options.extend([f'-D{protocol}.proxyHost={proxy.hostname}',f'-D{protocol}.proxyPort={proxy.port or 80}'])
 options.append('-Dhttp.nonProxyHosts=localhost|127.*')
if Path('/etc/ssl/certs/java/cacerts').exists():options.append('-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts')
environment['GRADLE_OPTS']=' '.join(options)
(repository/'android/local.properties').write_text('sdk.dir='+str(root/'sdk')+'\n')
command=[str(root/'gradle-8.11.1/bin/gradle'),*(sys.argv[1:] or [':app:assembleDebug']),'--no-daemon','--stacktrace']
raise SystemExit(subprocess.call(command,cwd=repository/'android',env=environment))
