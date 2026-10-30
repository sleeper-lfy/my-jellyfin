import json
import zipfile
import pytest
from lumen.support_bundle import collect_report, export_report


def test_bundle_allowlist_does_not_leak_secrets_titles_or_paths(library, tmp_path):
    secret = 'PRIVATE-SECRET-123'
    library.set_setting('proxy', 'https://user:' + secret + '@host.test')
    library.set_setting('plugin:private', {'cookie': secret})
    library.set_setting('poster_width', 220)
    library.set_setting('thumbnail_width', secret)
    library.set_setting('schema_migration_completed', secret)
    (library.directory / 'diagnostics.log').write_text(
        '2026-10-27 12:00:00,000 ERROR token=' + secret + ' title=PRIVATE-TITLE /private/movie.mp4\n'
        '  File "E:/workspaces/my-jellyfin/src/lumen/player.py", line 100, in open_file\n'
        'ValueError: ' + secret, encoding='utf-8')
    report = collect_report(library.directory, 'libmpv')
    text = json.dumps(report)
    for value in (secret, 'PRIVATE-TITLE', '/private', 'my-jellyfin', str(library.directory)):
        assert value not in text
    assert report['settings'] == {'poster_width': 220}
    assert report['logs']['diagnostics.log']['levels'] == {'ERROR': 1}
    assert report['logs']['diagnostics.log']['frames'] == [{'module': 'player.py', 'line': 100}]
    destination = tmp_path / 'report.zip'
    export_report(report, destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.namelist() == ['report.json']
        assert json.loads(archive.read('report.json')) == report
    assert not list(tmp_path.glob('*.tmp'))


def test_export_preserves_existing_file_on_failure(library, tmp_path, monkeypatch):
    destination = tmp_path / 'existing.zip'
    destination.write_bytes(b'keep')
    def fail(*args, **kwargs): raise OSError('disk full')
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', fail)
    with pytest.raises(OSError): export_report(collect_report(library.directory), destination)
    assert destination.read_bytes() == b'keep'
    with pytest.raises(ValueError): export_report({}, tmp_path / 'library.sqlite')
