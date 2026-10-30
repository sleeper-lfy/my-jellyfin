"""Executable acceptance record bound to source content and installer bytes.

Build verification and human acceptance are separate states. This records
evidence; it never publishes a release or infers manual checks from unit tests.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

MANUAL_CHECKS = {
    'audio': 'Windows 实际扬声器/耳机输出、音量与音画同步',
    'fullscreen': '窗口/全屏切换、任务栏、恢复播放',
    'dpi_keyboard': '100%/150% 缩放、关键页面、键盘操作',
    'upgrade_restore': '已有安装升级、资料保留、旧备份恢复',
    'plugin_live': '实际站点搜索、详情和错误提示（使用非私人测试数据）',
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_state(root):
    paths = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--',
         'src', 'tests', 'scripts', 'installer', 'assets', 'plugins', '.github',
         'pyproject.toml', 'requirements.lock'], cwd=root).decode('utf-8').split('\0')
    # Release requests are delivery metadata, not build inputs. They change when
    # publishing an already accepted artifact without rebuilding it.
    files = {name: sha256(root / name) if (root / name).is_file() else 'deleted'
             for name in sorted(set(paths)) if name and
             (not name.startswith('scripts/') or Path(name).suffix in {'.py', '.ps1', '.sh', '.cmd'})}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    return {'commit': commit, 'content_sha256': digest}


def begin(root):
    from . import __version__
    return {'format_version': 1, 'scope': 'Windows PC', 'version': __version__,
            'started_epoch': time.time(), 'source': source_state(Path(root)),
            'automated': {'status': 'pending'},
            'manual': {key: {'description': text, 'status': 'unverified'} for key, text in MANUAL_CHECKS.items()},
            'android': {'status': 'unverified', 'note': '此报告只验收 Windows；Android 真机验收单独进行'}}


def verify_junit(path, started):
    path = Path(path)
    if path.stat().st_mtime < started:
        raise ValueError('测试报告早于本次构建，不能复用旧结果')
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else root.findall('testsuite')
    totals = {key: sum(int(suite.get(key, 0)) for suite in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if not totals['tests'] or any(totals[key] for key in ('failures', 'errors', 'skipped')):
        raise ValueError('测试报告未全部通过或含跳过项')
    return {**totals, 'sha256': sha256(path)}


def finish(report, root, installer, junit, installation):
    if source_state(Path(root)) != report['source']:
        raise ValueError('构建期间源码发生变化，请重新构建验收')
    installer = Path(installer)
    if installer.stat().st_mtime < report['started_epoch']:
        raise ValueError('安装包早于本次构建，不能使用旧安装包')
    tests = verify_junit(junit, report['started_epoch'])
    proof = json.loads(Path(installation).read_text(encoding='utf-8-sig'))
    artifact_hash = sha256(installer)
    if proof.get('sha256') != artifact_hash or proof.get('started_epoch', 0) < report['started_epoch']:
        raise ValueError('安装验收记录与当前构建不匹配')
    for key in ('installed_ui', 'mpv_runtime', 'plugin_worker', 'uninstall'):
        if proof.get(key) is not True:
            raise ValueError('安装验收缺少通过项：' + key)
    report['artifact'] = {'filename': installer.name, 'sha256': artifact_hash, 'bytes': installer.stat().st_size}
    report['automated'] = {'status': 'passed', 'tests': tests, 'installation': proof}
    report['completed'] = datetime.now(timezone.utc).isoformat()
    # Rebuilding always invalidates previous human acceptance.
    for item in report['manual'].values():
        item.clear()
    report['manual'] = {key: {'description': text, 'status': 'unverified'} for key, text in MANUAL_CHECKS.items()}
    return report


def validate(report, installer, *, require_release=False):
    if report.get('format_version') != 1 or report.get('automated', {}).get('status') != 'passed':
        raise ValueError('自动验收尚未通过')
    artifact = report.get('artifact', {})
    if artifact.get('sha256') != sha256(installer) or artifact.get('bytes') != Path(installer).stat().st_size:
        raise ValueError('安装包已改变，验收记录失效')
    automated = report['automated']
    tests = automated.get('tests', {})
    proof = automated.get('installation', {})
    if not tests.get('tests') or any(tests.get(key, -1) != 0 for key in ('failures', 'errors', 'skipped')):
        raise ValueError('自动测试证据不完整')
    if proof.get('sha256') != artifact['sha256'] or not all(proof.get(key) is True for key in
            ('installed_ui', 'mpv_runtime', 'plugin_worker', 'uninstall')):
        raise ValueError('安装验收证据不完整')
    if require_release:
        pending = [key for key in MANUAL_CHECKS if
                   report.get('manual', {}).get(key, {}).get('status') != 'passed' or
                   not all(report['manual'][key].get(field) for field in ('reviewer', 'evidence', 'checked'))]
        if pending:
            raise ValueError('人工验收尚未完成：' + ', '.join(pending))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['begin', 'finish', 'check', 'record'])
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--installer', type=Path)
    parser.add_argument('--junit', type=Path, default=Path('.local/test-results.xml'))
    parser.add_argument('--installation', type=Path, default=Path('.local/installer-verification.json'))
    parser.add_argument('--require-release', action='store_true')
    parser.add_argument('--item', choices=list(MANUAL_CHECKS))
    parser.add_argument('--reviewer')
    parser.add_argument('--evidence')
    args = parser.parse_args(argv)
    try:
        if args.action == 'begin':
            report = begin(args.root)
        else:
            report = json.loads(args.report.read_text(encoding='utf-8-sig'))
            if not args.installer:
                raise ValueError('必须指定本次安装包 --installer')
            if args.action == 'finish':
                finish(report, args.root, args.installer, args.junit, args.installation)
            else:
                validate(report, args.installer, require_release=args.require_release)
                if args.require_release and source_state(args.root)['content_sha256'] != report['source']['content_sha256']:
                    raise ValueError('当前源码与验收时不同，请使用对应源码或重新验收')
                if args.action == 'check':
                    print('Acceptance passed.' if args.require_release else 'Automated checks passed; human checks are tracked separately.')
                    return 0
                if not args.item or not args.reviewer or not args.reviewer.strip() or not args.evidence or not args.evidence.strip():
                    raise ValueError('记录人工验收必须提供项目、验收人和具体证据')
                report['manual'][args.item].update(status='passed', reviewer=args.reviewer.strip(),
                    evidence=args.evidence.strip(), checked=datetime.now(timezone.utc).isoformat())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(args.report)
        print('Acceptance record saved: ' + str(args.report))
        return 0
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
