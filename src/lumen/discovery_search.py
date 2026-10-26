"""Explicit online discovery search; no local metadata is changed without matching."""
from __future__ import annotations

from .core import check_cancelled, identity
from .plugins import Plugins, validate_metadata


class DiscoverySearchError(ValueError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def search_parameters(query='', tag='', plugin_id=''):
    for value, name, maximum in ((query, '名称', 200), (tag, '标签', 200), (plugin_id, '来源', 51)):
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(f'{name}须为至多 {maximum} 个字符的字符串')
    query, tag, plugin_id = query.strip(), tag.strip(), plugin_id.strip()
    if not query and not tag:
        raise ValueError('请输入影片名称或站点标签')
    return query, tag, plugin_id


def search_providers(library):
    result = []
    for plugin in Plugins(library).installed():
        if not plugin['config'].get('enabled') or 'search' not in plugin['capabilities']:
            continue
        filters = plugin.get('search_filters', ['name'])
        result.append({'id': plugin['id'], 'name': plugin['name'],
                       'search_filters': [field for field in ('name', 'tag') if field in filters],
                       'supports_tags': 'tag' in filters})
    return result


def _merge_discovered(manager, plugin_id, record):
    """Resolve again under a short writer lock, closing the import/search race.

    The plugin parser and any network/image request run outside this transaction.
    Even identical source IDs or title/year matches never refresh a local work.
    """
    validate_metadata(record)
    library = manager.library
    kind = record.get('kind', 'movie')
    key = identity(record['title'], record.get('year'), kind)
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        associated = {row[0] for row in library.db.execute('SELECT work_id FROM sources WHERE plugin=? AND source_id=?',
                                                         (plugin_id, str(record['id'])))}
        associated.update(row[0] for row in library.db.execute('SELECT work_id FROM name_keys WHERE key=? UNION SELECT id FROM works WHERE identity=?', (key, key)))
        for namespace, value in record.get('external_ids', {}).items():
            if value is None or not str(value):
                continue
            associated.update(row[0] for row in library.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',
                                                                  (kind, namespace.lower(), str(value))))
        local = [work_id for work_id in sorted(associated) if library.db.execute('SELECT 1 FROM works w JOIN files f ON f.work_id=w.id WHERE w.id=? AND w.kind IN (?,?,?) LIMIT 1',
                                                                              (work_id, 'movie', 'series', 'vr')).fetchone()]
        if local:
            return local, False, True
        # _merge's metadata transaction commits before returning. Image work is
        # deliberately deferred: a search must not fetch every cast/still image.
        work_id = manager._merge(plugin_id, record, cache_images=False)
        return [work_id], work_id not in associated, False


def search_sites(library, query, tag='', plugin_id='', progress=None):
    query, tag, plugin_id = search_parameters(query, tag, plugin_id)
    providers = search_providers(library)
    providers = [provider for provider in providers if not plugin_id or provider['id'] == plugin_id]
    result = {'ids': [], 'count': 0, 'added': 0, 'matched': 0, 'local_matches': 0, 'searched': [], 'errors': []}
    if not providers:
        message = '所选站点未启用或不支持搜索' if plugin_id else '请先安装并启用支持 search 的站点插件'
        result['errors'].append({'plugin': plugin_id, 'name': plugin_id or '站点来源', 'message': message})
        raise DiscoverySearchError(message, result)
    manager = Plugins(library)
    cancelled = getattr(progress, 'cancelled', None)
    added, local_ids, found = set(), set(), set()
    for index, provider in enumerate(providers):
        check_cancelled(cancelled)
        source_id, source_name = provider['id'], provider['name']
        if progress: progress(index, len(providers), '正在搜索：' + source_name)
        if tag and not provider['supports_tags']:
            result['errors'].append({'plugin': source_id, 'name': source_name, 'message': '此来源不支持站点标签搜索；可清空标签后按名称搜索'})
            continue
        if query and 'name' not in provider['search_filters']:
            result['errors'].append({'plugin': source_id, 'name': source_name, 'message': '此来源不支持站点名称搜索'})
            continue
        try:
            records = manager.run(source_id, 'search', query=query,
                                  **({'tag': tag} if tag else {}), **({'cancelled': cancelled} if cancelled else {}))
            usable = 0
            result['matched'] += len(records)
            for record in records:
                check_cancelled(cancelled)
                try:
                    ids, created, local = _merge_discovered(manager, source_id, record)
                    found.update(ids); usable += 1
                    if created: added.update(ids)
                    if local: local_ids.update(ids)
                except Exception as error:
                    result['errors'].append({'plugin': source_id, 'name': source_name, 'message': record.get('title', '') + '：' + str(error)})
            if not records or usable:
                result['searched'].append(source_id)
        except Exception as error:
            from .core import ImportCancelled
            if isinstance(error, ImportCancelled): raise
            result['errors'].append({'plugin': source_id, 'name': source_name, 'message': str(error)})
        if progress: progress(index + 1, len(providers), source_name + '搜索完成')
    result.update(ids=sorted(found), count=len(found), added=len(added), local_matches=len(local_ids))
    if not result['searched']:
        raise DiscoverySearchError('站点搜索未完成：' + '；'.join(error['name'] + '：' + error['message'] for error in result['errors'])[:1600], result)
    # Poster URLs stay in metadata; desktop/LAN clients load only visible covers.
    # Search completion never waits for all poster, cast or still downloads.
    if progress: progress(len(providers), len(providers), f"搜索完成：{result['count']} 条")
    return result


def cache_discovery_cover(library, work_id):
    """Fetch one small visible poster without holding a database write lock."""
    import json
    from urllib.parse import urlparse
    from .matching import preview_cover
    work = library.work(work_id)
    if work['thumbnail']: return work['thumbnail']
    poster = work['metadata'].get('poster')
    if not isinstance(poster, str) or not poster or 'poster' in work['locked']:
        return None
    hostname = urlparse(poster).hostname
    associated = {source['plugin'] for source in work['sources']}
    provider = next((plugin for plugin in Plugins(library).installed()
                     if plugin['id'] in associated and plugin['config'].get('enabled') and hostname in plugin['domains']), None)
    if not provider: return None
    path = preview_cover(library, provider['id'], {'poster': poster})
    if not path: return None
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        row = library.db.execute('SELECT thumbnail,metadata,locked FROM works WHERE id=?', (work_id,)).fetchone()
        if not row: return None
        if row['thumbnail']: return row['thumbnail']
        if json.loads(row['metadata']).get('poster') != poster or 'poster' in json.loads(row['locked']): return None
        if not library.db.execute('SELECT 1 FROM files WHERE work_id=? LIMIT 1', (work_id,)).fetchone():
            library.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (path, work_id))
    return path


class DiscoverySearchJobs:
    """One bounded worker shares the desktop/server background concurrency budget."""
    def __init__(self, directory, budget):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from .task_journal import TaskJournal
        self.directory, self.budget = directory, budget
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='DiscoverySearch')
        self.slots = threading.BoundedSemaphore(4)
        self.closing = threading.Event()
        self.lock = threading.RLock()
        self.states = {}
        self.journal = TaskJournal(directory)

    def _record(self, identifier, status, payload, result=None, error=None):
        from .core import now
        value = {'id': identifier, 'kind': 'discovery-search', 'status': status,
                 'payload': payload, 'result': result or {}, 'error': error, 'updated': now()}
        with self.lock:
            self.states[identifier] = value
            while len(self.states) > 128:
                old = next((key for key, state in self.states.items() if state['status'] not in {'queued', 'running'}), None)
                if old is None: break
                del self.states[old]
        self.journal.record(identifier, 'discovery-search', status, payload, result, error)

    def submit(self, query='', tag='', plugin_id=''):
        import uuid
        query, tag, plugin_id = search_parameters(query, tag, plugin_id)
        if self.closing.is_set(): raise RuntimeError('服务端正在关闭，请稍后重新搜索')
        if not self.slots.acquire(blocking=False): raise OverflowError('站点搜索队列已满，请等待当前搜索完成')
        identifier = uuid.uuid4().hex
        payload = {'query': query, 'tag': tag, 'plugin': plugin_id}
        self._record(identifier, 'queued', payload)
        def run():
            from .core import Library, ImportCancelled
            library = None; acquired = False
            try:
                self.budget.acquire(self.closing.is_set); acquired = True
                library = Library(self.directory, initialize=False)
                library.parent_task_id = identifier
                self._record(identifier, 'running', payload)
                owner = self
                class Progress:
                    cancelled = staticmethod(owner.closing.is_set)
                    def __call__(self, done, total, stage):
                        owner._record(identifier, 'running', {**payload, 'progress': {'completed': done, 'total': total, 'stage': stage}})
                result = search_sites(library, query, tag, plugin_id, Progress())
                check_cancelled(self.closing.is_set)
                self._record(identifier, 'done', payload, result)
            except ImportCancelled:
                self._record(identifier, 'cancelled', payload, error='搜索已停止，请重新发起搜索')
            except Exception as error:
                self._record(identifier, 'cancelled' if self.closing.is_set() else 'failed', payload,
                             getattr(error, 'result', {}), str(error))
            finally:
                if library: library.close()
                if acquired: self.budget.release()
        try:
            future = self.pool.submit(run)
            def finished(value):
                if value.cancelled(): self._record(identifier, 'cancelled', payload, error='搜索已停止，请重新发起搜索')
                self.slots.release()
            future.add_done_callback(finished)
        except RuntimeError:
            self.slots.release(); self._record(identifier, 'cancelled', payload, error='服务端正在关闭')
            raise
        return identifier

    def status(self, library, identifier):
        import json
        with self.lock:
            if identifier in self.states: return dict(self.states[identifier])
        row = library.db.execute('SELECT * FROM tasks WHERE id=? AND kind=?', (identifier, 'discovery-search')).fetchone()
        if not row: return None
        state = {key: json.loads(row[key]) if key in {'payload', 'result'} else row[key] for key in row.keys()}
        if state['status'] in {'queued', 'running'}:
            state.update(status='cancelled', error='上次搜索已中断，请重新发起搜索')
            self._record(identifier, state['status'], state['payload'], state['result'], state['error'])
        return state

    def stop(self):
        self.closing.set()
        with self.lock:
            pending = [(key, value) for key, value in self.states.items() if value['status'] in {'queued', 'running'}]
        for key, value in pending:
            self._record(key, 'cancelled', value['payload'], value['result'], '搜索已停止，请重新发起搜索')
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.journal.stop()
