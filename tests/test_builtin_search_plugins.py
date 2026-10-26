"""Explicit upgrades keep user settings and cannot overwrite arbitrary providers."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from lumen.discovery_search import search_providers
from lumen.plugins import Plugins


@pytest.mark.parametrize('plugin_id,domains', [
    ('tvmaze', ['api.tvmaze.com', 'static.tvmaze.com']),
    ('internet-archive', ['archive.org']),
])
def test_shipped_search_source_install_stays_disabled_and_has_exact_permissions(library, plugin_id, domains):
    manager = Plugins(library)
    source = manager.builtin_search_plugin(plugin_id)
    assert source == (Path(__file__).parents[1] / 'plugins' / plugin_id).resolve()
    manifest = manager.update_builtin_search_plugin(plugin_id)
    assert manifest['id'] == plugin_id and manifest['domains'] == domains
    installed = manager.installed()[0]
    assert not installed['config']['enabled'] and search_providers(library) == []
    assert installed['search_filters'] == (['name', 'tag'] if plugin_id == 'internet-archive' else ['name'])
    with pytest.raises(ValueError, match='权限'):
        manager.fetch(installed, 'https://unlisted.example.org/private')
    with pytest.raises(ValueError, match='权限'):
        manager.fetch(installed, 'https://archive.org@unlisted.example.org/private')


@pytest.mark.parametrize('plugin_id', ['tvmaze', 'internet-archive'])
@pytest.mark.parametrize('enabled', [False, True])
def test_old_search_code_and_manifest_are_upgraded_without_resetting_any_configuration(library, plugin_id, enabled):
    manager = Plugins(library); manager.update_builtin_search_plugin(plugin_id)
    manager.configure(plugin_id, {'enabled': enabled, 'proxy': 'http://127.0.0.1:8899', 'priority': 17,
                                  'category': 'my_collection', 'interval_hours': 13, 'auto_refresh': True,
                                  'base_url': 'https://archive.org/custom' if plugin_id == 'internet-archive' else 'https://api.tvmaze.com/custom',
                                  'last_refresh': 1234, 'user_extra': {'keep': 'all settings'}})
    previous = library.setting('plugin:'+plugin_id)
    target = manager.root / plugin_id
    old = json.loads((target/'manifest.json').read_text(encoding='utf-8'))
    old['version'] = '0.0.1'; old.pop('search_filters', None)
    (target/'manifest.json').write_text(json.dumps(old), encoding='utf-8')
    (target/'plugin.js').write_text('function oldPlugin(){return "old code";}', encoding='utf-8')
    manifest = manager.update_builtin_search_plugin(plugin_id)
    official = json.loads((manager.builtin_search_plugin(plugin_id)/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['version'] == official['version'] != '0.0.1'
    assert (target/'plugin.js').read_bytes() == (manager.builtin_search_plugin(plugin_id)/'plugin.js').read_bytes()
    assert library.setting('plugin:'+plugin_id) == previous
    if enabled:
        assert search_providers(library)[0]['supports_tags'] == (plugin_id == 'internet-archive')
    else: assert search_providers(library) == []
    assert not list(target.glob('*.updating'))


@pytest.mark.parametrize('plugin_id', ['catalog-json', 'wikimedia-actors', '../tvmaze', '/tmp/tvmaze', 'tvmaze/../internet-archive'])
def test_search_updater_rejects_third_party_actor_only_and_path_traversal_ids(library, plugin_id):
    manager = Plugins(library); manager.install(Path('plugins/example'))
    manager.configure('catalog-json', {'enabled': True, 'priority': 9})
    before = {path.name:path.read_bytes() for path in (manager.root/'catalog-json').iterdir()}
    config = library.setting('plugin:catalog-json')
    with pytest.raises(ValueError): manager.builtin_search_plugin(plugin_id)
    with pytest.raises(ValueError): manager.update_builtin_search_plugin(plugin_id)
    assert {path.name:path.read_bytes() for path in (manager.root/'catalog-json').iterdir()} == before
    assert library.setting('plugin:catalog-json') == config
    assert len(manager.installed()) == 1


def test_packaged_search_update_uses_only_runtime_bundled_source_and_rejects_wrong_manifest(library, tmp_path, monkeypatch):
    runtime = tmp_path/'packaged-app'
    runtime_plugins = runtime/'plugins'; runtime_plugins.mkdir(parents=True)
    source = runtime_plugins/'internet-archive'
    shutil.copytree(Path('plugins/internet-archive'), source)
    monkeypatch.setattr(sys, '_MEIPASS', str(runtime), raising=False)
    manager = Plugins(library)
    assert manager.builtin_search_plugin('internet-archive') == source.resolve()
    manager.update_builtin_search_plugin('internet-archive')
    target = manager.root/'internet-archive'
    before = {path.name:path.read_bytes() for path in target.iterdir()}
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    manifest['id'] = 'third-party'
    (source/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='清单'):
        manager.update_builtin_search_plugin('internet-archive')
    assert {path.name:path.read_bytes() for path in target.iterdir()} == before
    assert not library.setting('plugin:internet-archive')['enabled']
