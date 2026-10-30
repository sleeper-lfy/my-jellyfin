import json
import os
from pathlib import Path
import time
import pytest
from lumen import release_acceptance as acceptance


def fixture_run(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance, 'source_state', lambda root: {'commit': 'abc', 'content_sha256': 'hash'})
    report = acceptance.begin(tmp_path)
    report['started_epoch'] -= 2
    installer = tmp_path / 'Lumen.exe'
    installer.write_bytes(b'new installer')
    junit = tmp_path / 'tests.xml'
    junit.write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>')
    installation = tmp_path / 'installation.json'
    installation.write_text(json.dumps({'sha256': acceptance.sha256(installer), 'started_epoch': time.time(),
        'installed_ui': True, 'mpv_runtime': True, 'plugin_worker': True, 'uninstall': True}))
    return report, installer, junit, installation


def test_automatic_acceptance_never_implies_manual_or_android(tmp_path, monkeypatch):
    report, installer, junit, proof = fixture_run(tmp_path, monkeypatch)
    acceptance.finish(report, tmp_path, installer, junit, proof)
    acceptance.validate(report, installer)
    assert report['android']['status'] == 'unverified'
    with pytest.raises(ValueError, match='人工验收'): acceptance.validate(report, installer, require_release=True)
    for item in report['manual'].values():
        item.update(status='passed', reviewer='tester', evidence='device and observed outcome', checked='2026-10-27')
    acceptance.validate(report, installer, require_release=True)
    installer.write_bytes(b'changed')
    with pytest.raises(ValueError, match='已改变'): acceptance.validate(report, installer, require_release=True)


@pytest.mark.parametrize('fault', ['old_tests', 'old_installer', 'old_proof', 'wrong_artifact', 'failed_tests', 'skipped_tests', 'source_changed', 'missing_check'])
def test_rejects_stale_incomplete_or_changed_evidence(tmp_path, monkeypatch, fault):
    report, installer, junit, proof_path = fixture_run(tmp_path, monkeypatch)
    proof = json.loads(proof_path.read_text())
    if fault == 'old_tests': os.utime(junit, (1, 1))
    if fault == 'old_installer': os.utime(installer, (1, 1))
    if fault == 'old_proof': proof['started_epoch'] = 1
    if fault == 'wrong_artifact': proof['sha256'] = 'wrong'
    if fault == 'failed_tests': junit.write_text('<testsuite tests="2" failures="1"/>')
    if fault == 'skipped_tests': junit.write_text('<testsuite tests="2" skipped="1"/>')
    if fault == 'missing_check': del proof['uninstall']
    if fault == 'source_changed': monkeypatch.setattr(acceptance, 'source_state', lambda root: {})
    proof_path.write_text(json.dumps(proof))
    with pytest.raises(ValueError): acceptance.finish(report, tmp_path, installer, junit, proof_path)


def test_record_requires_specific_human_evidence_and_hash_match(tmp_path, monkeypatch):
    report, installer, junit, proof = fixture_run(tmp_path, monkeypatch)
    acceptance.finish(report, tmp_path, installer, junit, proof)
    path = tmp_path / 'acceptance.json'
    path.write_text(json.dumps(report))
    args = ['record', '--report', str(path), '--installer', str(installer), '--item', 'audio', '--reviewer', 'tester']
    with pytest.raises(SystemExit): acceptance.main(args)
    assert acceptance.main(args + ['--evidence', 'Windows 11 speaker output normal']) == 0
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['manual']['audio']['status'] == 'passed'
    assert saved['manual']['fullscreen']['status'] == 'unverified'


def test_source_fingerprint_detects_uncommitted_source(tmp_path):
    import subprocess
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '--allow-empty', '-qm', 'init'], check=True)
    (tmp_path / 'src').mkdir()
    source = tmp_path / 'src/example.py'
    source.write_text('first')
    first = acceptance.source_state(tmp_path)
    source.write_text('second')
    assert acceptance.source_state(tmp_path) != first
    (tmp_path / 'scripts').mkdir()
    request = tmp_path / 'scripts/package-request.json'
    request.write_text('{"publish": false}')
    before = acceptance.source_state(tmp_path)
    request.write_text('{"publish": true}')
    assert acceptance.source_state(tmp_path) == before


def test_release_gate_requires_matching_source_and_complete_evidence(tmp_path, monkeypatch):
    report, installer, junit, proof = fixture_run(tmp_path, monkeypatch)
    acceptance.finish(report, tmp_path, installer, junit, proof)
    for item in report['manual'].values():
        item.update(status='passed', reviewer='tester', evidence='tested on device', checked='2026-10-27')
    path = tmp_path / 'acceptance.json'
    path.write_text(json.dumps(report))
    args = ['check', '--report', str(path), '--installer', str(installer), '--require-release']
    assert acceptance.main(args) == 0
    monkeypatch.setattr(acceptance, 'source_state', lambda root: {'content_sha256': 'different'})
    with pytest.raises(SystemExit): acceptance.main(args)
    report['automated']['installation']['uninstall'] = False
    with pytest.raises(ValueError, match='安装验收证据'): acceptance.validate(report, installer, require_release=True)
