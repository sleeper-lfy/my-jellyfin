from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
import httpx
from .core import identity, now

CAPABILITIES = {'search', 'detail', 'discover', 'actors'}


def validate_actor(item):
    """Independent people records are not media records and never create works."""
    if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item['name'].strip() or len(item['name']) > 200 or not item.get('id'):
        raise ValueError('演员资料缺少 name / id')
    if item.get('gender', 'unknown') not in {'female', 'male', 'unknown'}:
        raise ValueError('无效演员性别')
    aliases = item.get('aliases', [])
    if not isinstance(aliases, list) or len(aliases) > 100 or any(not isinstance(name, str) or len(name) > 200 for name in aliases):
        raise ValueError('演员 aliases 须为至多 100 个姓名的数组')
    for field in ('url', 'photo', 'photo_page'):
        address = item.get(field)
        if field == 'url' or address:
            parsed = urlparse(address if isinstance(address, str) else '')
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('演员来源及头像须为完整 HTTP(S) URL')


def validate_metadata(item):
    if not isinstance(item, dict) or not isinstance(item.get('title'), str) or not item['title'].strip() or not item.get('id'):
        raise ValueError('元数据缺少 title / id')
    if item.get('kind', 'movie') not in {'movie', 'series', 'vr'} or urlparse(item.get('url','')).scheme not in {'http','https'}:
        raise ValueError('无效媒体类型或来源 URL')
    stills=item.get('stills',[])
    if not isinstance(stills,list) or len(stills)>40 or any(not isinstance(url,str) or urlparse(url).scheme not in {'http','https'} for url in stills):
        raise ValueError('stills 须为至多 40 个 HTTP/HTTPS 图片 URL')
    method=item.get('download_method')
    if method is not None and method not in {'magnet','direct'}:
        raise ValueError('download_method 须为 magnet 或 direct')
    downloads=item.get('download_url',[])
    if not isinstance(downloads,list) or len(downloads)>40:
        raise ValueError('download_url 须为至多 40 项的数组')
    for entry in downloads:
        if not isinstance(entry,dict) or not isinstance(entry.get('url'),str) or not isinstance(entry.get('description',''),str):
            raise ValueError('下载项须包含 url，description 须为字符串')
        selected=entry.get('method',method)
        scheme=urlparse(entry['url']).scheme
        if selected not in {'magnet','direct'} or (selected=='magnet' and scheme!='magnet') or (selected=='direct' and scheme not in {'http','https'}):
            raise ValueError('下载方式与 URL 协议不匹配')
    for field in ['tags','aliases','directors']:
        if not isinstance(item.get(field,[]),list) or any(not isinstance(v,str) for v in item.get(field,[])):
            raise ValueError(field + ' 须为字符串数组')
    if not isinstance(item.get('actors',[]),list) or any(not isinstance(a,dict) or not isinstance(a.get('name'),str) or a.get('gender','unknown') not in {'female','male','unknown'} or not isinstance(a.get('aliases',[]),list) or any(not isinstance(n,str) for n in a.get('aliases',[])) for a in item.get('actors',[])):
        raise ValueError('无效演员数据')
    if not isinstance(item.get('external_ids',{}),dict) or any(not isinstance(k,str) or v is not None and not isinstance(v,(str,int)) for k,v in item.get('external_ids',{}).items()):
        raise ValueError('external_ids 须为命名空间到字符串/数字的映射')
    if item.get('year') is not None and (type(item['year']) is not int or not 1800 <= item['year'] <= 2200):
        raise ValueError('年份须为 1800–2200 的整数或空')
    if item.get('rating') is not None and (type(item['rating']) not in {float,int} or not 0 <= item['rating'] <= 10):
        raise ValueError('来源评分须归一到 0–10 或空')



class Plugins:
    def __init__(self, library):
        self.library = library
        self.root = library.directory / 'plugins'
        self.root.mkdir(exist_ok=True)

    def install(self, folder):
        folder = Path(folder)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        import re
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,50}', manifest['id']):
            raise ValueError('无效插件 ID')
        if not set(manifest['capabilities']) <= CAPABILITIES or manifest.get('api_version') != 1:
            raise ValueError('不支持的插件接口')
        if not manifest.get('domains') or any('/' in d or '*' in d or ':' in d for d in manifest['domains']):
            raise ValueError('须声明精确网络主机名')
        script = (folder / 'plugin.js').read_text(encoding='utf-8')
        if len(script) > 1_000_000:
            raise ValueError('脚本过大')
        target = self.root / manifest['id']
        target.mkdir()  # Never overwrite an existing installation.
        (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        (target / 'plugin.js').write_text(script, encoding='utf-8')
        self.configure(manifest['id'], {'enabled': False, 'base_url': manifest.get('base_url', ''), 'category': '', 'priority': 100, 'proxy': 'inherit', 'interval_hours': 24})
        return manifest

    def installed(self):
        result = []
        for path in sorted(self.root.glob('*/manifest.json')):
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['config'] = self.library.setting('plugin:' + manifest['id'], {})
            result.append(manifest)
        return sorted(result, key=lambda p: p['config'].get('priority', 100))

    def configure(self, plugin_id, config):
        previous = self.library.setting('plugin:' + plugin_id, {})
        previous.update(config)
        self.library.set_setting('plugin:' + plugin_id, previous)

    @staticmethod
    def builtin_actor_plugin(plugin_id):
        """Locate a shipped provider; callers must show its permissions first."""
        if plugin_id not in {'tvmaze', 'wikimedia-actors'}:
            raise ValueError('不是随应用提供的演员插件')
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        folder = root / 'plugins' / plugin_id
        if not (folder / 'manifest.json').is_file() or not (folder / 'plugin.js').is_file():
            raise ValueError('当前安装包缺少内置演员插件文件')
        return folder

    def update_builtin_actor_plugin(self, plugin_id):
        """Explicitly install/update shipped code, preserving enabled/proxy config.

        This never runs automatically and never enables a newly installed plugin.
        The UI must display the shipped manifest's domains before invoking it.
        """
        folder = self.builtin_actor_plugin(plugin_id)
        target = self.root / plugin_id
        if not target.exists():
            return self.install(folder)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['id'] != plugin_id or 'actors' not in manifest['capabilities']:
            raise ValueError('内置演员插件清单不匹配')
        # Two atomically replaced files, no deletion of user plugin configuration.
        for name in ('plugin.js', 'manifest.json'):
            temporary = target / (name + '.updating')
            temporary.write_bytes((folder / name).read_bytes())
            temporary.replace(target / name)
        return manifest

    def uninstall(self, plugin_id):
        found = next(p for p in self.installed() if p['id'] == plugin_id)
        shutil.rmtree(self.root / found['id'])
        self.library.set_setting('plugin:' + plugin_id, {})

    def javascript(self, plugin_id, function, argument):
        script = (self.root / plugin_id / 'plugin.js').read_text(encoding='utf-8')
        command = [sys.executable, '--plugin-worker'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'lumen.js_worker']
        # File IPC also works in PyInstaller's Windows windowed mode, where stdio is absent.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='plugin-', dir=self.library.directory) as directory:
            input_path, output_path = Path(directory) / 'input.json', Path(directory) / 'output.json'
            input_path.write_text(json.dumps({'script': script, 'function': function, 'argument': argument}), encoding='utf-8')
            result = subprocess.run([*command, str(input_path), str(output_path)], text=True, capture_output=True, timeout=8,
                                    creationflags=0x08000000 if sys.platform == 'win32' else 0)
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:] or f'插件进程被终止（资源限制 / exit={result.returncode}）')
            if not output_path.is_file() or output_path.stat().st_size > 4_000_000:
                raise ValueError('插件未返回有效大小的响应')
            output = json.loads(output_path.read_text(encoding='utf-8'))
            if 'error' in output:
                raise RuntimeError(output['error'])
            return output['result']

    def fetch(self, plugin, url, image=False):
        parsed = urlparse(url)
        if parsed.scheme not in {'https', 'http'} or parsed.hostname not in plugin['domains'] or parsed.username or parsed.password:
            raise ValueError('插件请求不在声明的网络权限内')
        proxy = plugin['config'].get('proxy', 'inherit')
        if proxy == 'inherit':
            proxy = self.library.setting('proxy', '')
        if proxy and urlparse(proxy).scheme not in {'http', 'https', 'socks5', 'socks5h'}:
            raise ValueError('代理协议须为 HTTP、HTTPS 或 SOCKS5')
        maximum = 10_000_000 if image else 4_000_000
        with httpx.Client(proxy=proxy or None, trust_env=False, timeout=20, follow_redirects=False) as client:
            with client.stream('GET', url, headers={'User-Agent': 'Lumen/0.1 (personal media library)'}) as response:
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError('重定向被拒绝，请配置最终站点地址')
                data = bytearray()
                deadline = time.monotonic() + 30
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > maximum or time.monotonic() > deadline:
                        raise ValueError('响应大小或时间超限')
                return bytes(data), response.headers.get('content-type', '')

    def run(self, plugin_id, operation, **parameters):
        plugin = next(p for p in self.installed() if p['id'] == plugin_id)
        if not plugin['config'].get('enabled'):
            raise ValueError('插件未启用')
        if operation not in plugin['capabilities']:
            raise ValueError('插件不支持该功能')
        import uuid
        task_id = uuid.uuid4().hex
        payload = {'plugin': plugin_id, 'operation': operation, 'parameters': parameters}
        self.library.task(task_id, 'scrape', 'running', payload)
        try:
            request = self.javascript(plugin_id, 'buildRequest', {'operation': operation, 'config': plugin['config'], **parameters})
            pending = [request]
            visited = set()
            result = []
            deadline = time.monotonic() + 180
            while pending:
                request = pending.pop(0)
                url = request['url']
                if url in visited:
                    continue
                if len(visited) >= 20 or time.monotonic() > deadline:
                    raise ValueError('插件请求预算超限（20 次 / 180 秒）')
                visited.add(url)
                data, content_type = self.fetch(plugin, url)
                parsed = self.javascript(plugin_id, 'parseResponse', {'operation': operation, 'url': url, 'body': data.decode('utf-8-sig'), 'content_type': content_type,
                                                                     'config': plugin['config'], 'context': request.get('context')})
                if isinstance(parsed, dict):
                    followups = parsed.get('followups', [])
                    if not isinstance(followups, list) or len(followups) > 19 or any(not isinstance(r,dict) or not isinstance(r.get('url'),str) for r in followups):
                        raise ValueError('无效后续请求')
                    pending.extend(followups)
                    parsed = parsed.get('records', [])
                if not isinstance(parsed, list) or len(parsed) + len(result) > 1000:
                    raise ValueError('插件必须返回至多 1000 条元数据记录')
                result.extend(parsed)
            for item in result:
                if operation == 'actors':
                    validate_actor(item)
                    continue
                if not isinstance(item, dict) or not isinstance(item.get('title'), str) or not item['title'].strip() or not item.get('id'):
                    raise ValueError('元数据缺少 title / id')
                if item.get('kind', 'movie') not in {'movie', 'series', 'vr'}:
                    raise ValueError('刮削只用于电影和电视剧')
                if urlparse(item.get('url', '')).scheme not in {'http', 'https'}:
                    raise ValueError('来源必须包含完整 HTTP(S) URL')
                validate_metadata(item)
            self.library.task(task_id, 'scrape', 'done', payload, {'count': len(result)})
            return result
        except Exception as exc:
            self.library.task(task_id, 'scrape', 'failed', payload, error=str(exc))
            raise

    def merge_actor(self, plugin_id, metadata, actor_name, *, replace=False):
        """Cache a confirmed portrait once, then update matching local cast entries.

        Run this on a worker: downloading/decoding happens before any write
        transaction so a slow provider cannot hold SQLite's writer lock.
        """
        validate_actor(metadata)
        if not isinstance(actor_name, str) or not actor_name.strip() or type(replace) is not bool:
            raise ValueError('须指定本地演员姓名及是否覆盖')
        plugin = next(p for p in self.installed() if p['id'] == plugin_id)
        if not plugin['config'].get('enabled') or 'actors' not in plugin['capabilities']:
            raise ValueError('演员资料插件未启用或不支持此功能')
        if not metadata.get('photo'):
            raise ValueError('所选演员没有头像')
        wanted = actor_name.strip().casefold()
        def matches(actor):
            return wanted in {str(name).strip().casefold() for name in [actor.get('name', ''), *actor.get('aliases', [])]}
        eligible = []
        skipped = 0
        # Stream cast metadata: a large library need not hold every NFO in RAM.
        for row in self.library.db.execute('SELECT id,metadata,locked FROM works'):
            details = json.loads(row['metadata'])
            if not any(matches(actor) for actor in details.get('actors', [])):
                continue
            if 'actors' in json.loads(row['locked']):
                skipped += 1
                continue
            targets = [actor for actor in details.get('actors', []) if matches(actor)]
            if not replace and all(actor.get('photo_cache') and Path(actor['photo_cache']).is_file() for actor in targets):
                skipped += 1
                continue
            eligible.append(row['id'])
        if not eligible:
            return {'updated': 0, 'skipped': skipped, 'name': actor_name}
        data, content_type = self.fetch(plugin, metadata['photo'], image=True)
        if not content_type.lower().startswith('image/'):
            raise ValueError('演员头像响应类型错误')
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSaveFile
        from PySide6.QtGui import QImageReader
        buffer = QBuffer(); buffer.setData(QByteArray(data)); buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer); reader.setAutoTransform(True); size = reader.size()
        if not size.isValid() or size.width() * size.height() > 40_000_000:
            raise ValueError('演员头像尺寸无效或过大')
        # Portrait tiles never need an original 40 MP image in memory/cache.
        if max(size.width(), size.height()) > 1200:
            from PySide6.QtCore import QSize, Qt
            reader.setScaledSize(size.scaled(QSize(1200, 1200), Qt.AspectRatioMode.KeepAspectRatio))
        picture = reader.read()
        if picture.isNull():
            raise ValueError('演员头像无法解码')
        revision = hashlib.sha256(data).hexdigest()
        path = self.library.directory / 'cache' / ('actor-' + revision + '.jpg')
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly) or not picture.save(output, 'JPG') or not output.commit():
            raise ValueError('演员头像缓存未能保存')
        updated = 0
        with self.library.db:
            for work_id in eligible:
                # Read again after the network request, preserving concurrent edits.
                row = self.library.db.execute('SELECT metadata,locked FROM works WHERE id=?', (work_id,)).fetchone()
                if not row or 'actors' in json.loads(row['locked']):
                    skipped += 1
                    continue
                details = json.loads(row['metadata']); changed = False
                for actor in details.get('actors', []):
                    if not matches(actor) or not replace and actor.get('photo_cache') and Path(actor['photo_cache']).is_file():
                        continue
                    actor.update(photo=metadata['photo'], photo_cache=str(path), photo_revision=revision, photo_source=plugin_id,
                                 photo_source_id=str(metadata['id']), photo_source_url=metadata['url'])
                    import html
                    import re
                    for field in ('photo_page', 'photo_license', 'photo_attribution'):
                        actor.pop(field, None)
                        value = metadata.get(field)
                        if isinstance(value, str):
                            actor[field] = html.unescape(re.sub(r'<[^>]*>', '', value))[:4000]
                    changed = True
                if changed:
                    self.library.db.execute('UPDATE works SET metadata=? WHERE id=?', (json.dumps(details, ensure_ascii=False), work_id))
                    updated += 1
        return {'updated': updated, 'skipped': skipped, 'name': actor_name}

    def merge(self, plugin_id, metadata, work_id=None, *, replace_nfo=False):
        with self.library.db:
            return self._merge(plugin_id,metadata,work_id,replace_nfo=replace_nfo)

    def _merge(self, plugin_id, metadata, work_id=None, *, replace_nfo=False):
        metadata = {key:value for key,value in metadata.items() if key not in {'stills_cache','nfo_stills','episode_stills','episode_details','nfo_fields','nfo_poster','nfo_backdrop','nfo_thumbnails','download_plugin'}}
        validate_metadata(metadata)
        plugin = next(p for p in self.installed() if p['id'] == plugin_id)
        existing = self.library.db.execute('SELECT work_id FROM sources WHERE plugin=? AND source_id=?', (plugin_id, str(metadata['id']))).fetchone()
        if existing and work_id and existing[0] != work_id:
            source = self.library.work(existing[0])
            if source['files']:
                raise ValueError('该来源已经关联另一部本地媒体，请人工核对，未自动合并')
            self.library.merge_works(existing[0], work_id, commit=False)
        kind = metadata.get('kind', 'movie')
        if work_id and self.library.work(work_id)['kind']=='vr' and kind=='movie':
            kind='vr';metadata={**metadata,'kind':'vr'}
        key = identity(metadata['title'], metadata.get('year'), kind)
        matching = self.library.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
        if not matching:
            matching = self.library.db.execute('SELECT id FROM works WHERE identity=?', (key,)).fetchone()
        external = {str(k).lower():str(v) for k,v in metadata.get('external_ids',{}).items() if v is not None and str(v)}
        linked = set()
        for namespace,value in external.items():
            row = self.library.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',(kind,namespace,value)).fetchone()
            if row:
                linked.add(row[0])
        if len(linked)>1:
            raise ValueError('外部标识指向多个实体，请人工核对')
        linked_id = next(iter(linked),None)
        work_id = work_id or (existing[0] if existing else linked_id or (matching[0] if matching else None))
        if linked_id and linked_id != work_id:
            if self.library.work(linked_id)['files']:
                raise ValueError('外部标识已关联另一部本地媒体，请人工核对')
            self.library.merge_works(linked_id,work_id,commit=False)
        if work_id:
            stored_external = list(self.library.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(work_id,)))
            if any(namespace in external and external[namespace] != value for namespace,value in stored_external):
                raise ValueError('同名影片的外部标识冲突，未自动合并')
        if matching and work_id and matching[0] != work_id:
            other = self.library.work(matching[0])
            if not other['files']:
                self.library.merge_works(matching[0], work_id, commit=False)
            else:
                raise ValueError('同标题与年份已存在另一部本地作品，请先人工合并核对')
        if work_id and self.library.work(work_id)['kind'] == 'other':
            raise ValueError('其他分区不执行联网刮削')
        with self.library.db:
            if not work_id:
                cursor = self.library.db.execute('INSERT INTO works(identity,kind,title,year,added,discovered) VALUES (?,?,?,?,?,?)',
                                                (key, kind, metadata['title'], metadata.get('year'), now(), now()))
                work_id = cursor.lastrowid
            item = self.library.work(work_id)
            if item['kind'] != kind:
                raise ValueError('候选媒体类型不匹配')
            protected = set(item['locked']) | (set() if replace_nfo else set(item['metadata'].get('nfo_fields', [])))
            merged = {**item['metadata'], **{k: v for k, v in metadata.items() if k not in protected and v not in (None, [], '')}}
            merged['external_ids'] = {**item['metadata'].get('external_ids',{}), **metadata.get('external_ids',{})}
            if 'aliases' not in protected:
                merged['aliases'] = list(dict.fromkeys(item['metadata'].get('aliases',[]) + metadata.get('aliases',[]) + ([item['title']] if item['title'] != metadata['title'] else [])))
            else:
                merged.setdefault('aliases', [])
            if metadata.get('download_url'):
                merged['download_plugin'] = plugin_id
            merged['discovery_categories'] = list(dict.fromkeys(item['metadata'].get('discovery_categories', []) + metadata.get('discovery_categories', [])))
            self.library.db.execute('UPDATE works SET identity=?,metadata=?,title=?,year=? WHERE id=?',
                                    (key, json.dumps(merged, ensure_ascii=False), item['title'] if 'title' in protected else metadata['title'],
                                     item['year'] if 'year' in protected else metadata.get('year', item['year']), work_id))
            self.library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(key,work_id))
            for alias in merged['aliases']:
                self.library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(identity(alias,metadata.get('year'),kind),work_id))
            for namespace,value in external.items():
                self.library.db.execute('INSERT OR IGNORE INTO external_ids VALUES (?,?,?,?)',(kind,namespace,value,work_id))
            self.library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plugin,source_id) DO UPDATE SET url=excluded.url,updated=excluded.updated,site_added=excluded.site_added,rating=excluded.rating',
                                    (work_id, plugin_id, plugin['name'], str(metadata['id']), metadata['url'], now(), metadata.get('site_added'), metadata.get('rating')))
        # Images use exactly the same network policy and proxy as metadata.
        for image_url, actor in [(metadata.get('poster'), None), *[(a.get('photo'), a) for a in merged.get('actors', [])]]:
            if not image_url or actor is None and item['metadata'].get('nfo_poster') and not replace_nfo:
                continue
            try:
                data, content_type = self.fetch(plugin, image_url, image=True)
                if not content_type.startswith('image/'):
                    raise ValueError('图片响应类型错误')
                from PySide6.QtGui import QImage
                picture = QImage.fromData(data)
                if picture.isNull() or picture.width() * picture.height() > 40_000_000:
                    raise ValueError('图片无效或过大')
                filename = 'actor-' + hashlib.sha256(data).hexdigest() if actor is not None else hashlib.sha256(image_url.encode()).hexdigest()
                path = self.library.directory / 'cache' / (filename + '.jpg')
                picture.save(str(path), 'JPG')
                with self.library.db:
                    if actor is None and 'poster' not in item['locked']:
                        if replace_nfo: merged.pop('nfo_poster', None)
                        self.library.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(path), work_id))
                    elif actor is not None:
                        actor['photo_cache'] = str(path)
                        actor['photo_revision'] = hashlib.sha256(data).hexdigest()
                        self.library.db.execute('UPDATE works SET metadata=? WHERE id=?', (json.dumps(merged, ensure_ascii=False), work_id))
            except Exception as exc:
                import uuid
                self.library.task(uuid.uuid4().hex, 'image', 'failed', {'url': image_url, 'plugin': plugin_id}, error=str(exc))
        if 'stills' not in item['locked']:
            cached={entry['url']:entry for entry in item['metadata'].get('stills_cache',[]) if isinstance(entry,dict) and entry.get('url') and entry.get('path')}
            for image_url in dict.fromkeys(metadata.get('stills',[])):
                if image_url in cached and Path(cached[image_url]['path']).is_file():
                    continue
                try:
                    data, content_type = self.fetch(plugin,image_url,image=True)
                    if not content_type.startswith('image/'):
                        raise ValueError('剧照响应类型错误')
                    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
                    from PySide6.QtGui import QImageReader
                    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                    reader=QImageReader(buffer);size=reader.size()
                    if size.width()<=0 or size.height()<=0 or size.width()*size.height()>40_000_000:
                        raise ValueError('剧照无效或像素过大')
                    if size.width()>1920:
                        from PySide6.QtCore import QSize
                        reader.setScaledSize(QSize(1920,max(1,size.height()*1920//size.width())))
                    picture=reader.read()
                    path=self.library.directory/'cache'/('still-'+hashlib.sha256(image_url.encode()).hexdigest()+'.jpg')
                    if picture.isNull() or not picture.save(str(path),'JPG'):
                        raise ValueError('剧照解码或保存失败')
                    cached[image_url]={'url':image_url,'path':str(path)}
                except Exception as exc:
                    import uuid
                    self.library.task(uuid.uuid4().hex,'image','failed',{'url':image_url,'plugin':plugin_id,'role':'still'},error=str(exc))
            merged['stills_cache']=[cached[url] for url in dict.fromkeys(merged.get('stills',[])) if url in cached]
        with self.library.db:
            self.library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(merged,ensure_ascii=False),work_id))
        return work_id

    def refresh(self, plugin_id, category=None):
        parameters = {'category': category} if category is not None else {}
        self.configure(plugin_id, {'last_attempt': time.time()})
        configuration = self.library.setting('plugin:' + plugin_id, {})
        categories = [category] if category is not None else [c.strip() for c in configuration.get('category', '').split(',') if c.strip()] or [None]
        result = []
        for category in categories:
            records = self.run(plugin_id, 'discover', **({'category': category} if category is not None else {}))
            for record in records:
                record['discovery_categories'] = [plugin_id + ':' + (category or 'default')]
            result.extend(records)
        ids = list(dict.fromkeys(self.merge(plugin_id, item) for item in result))
        self.configure(plugin_id, {'last_refresh': time.time()})
        return ids
