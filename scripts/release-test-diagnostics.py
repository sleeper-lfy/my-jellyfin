"""Read CI logs in memory; publish only repository test IDs and fixed categories."""
import ast
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TYPES = ('AssertionError','TypeError','ValueError','RuntimeError','FileNotFoundError',
         'PermissionError','HTTPStatusError','CalledProcessError','TimeoutError')


def summarize(logs, root=ROOT):
    allowed = set()
    for path in (root/'tests').rglob('test_*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                allowed.add(path.relative_to(root).as_posix()+'::'+node.name)
    failed = set()
    types = set()
    for value in logs:
        for match in re.finditer(r'FAILED (tests/[A-Za-z0-9_/]+\.py)::(?:[A-Za-z0-9_]+::)*([A-Za-z0-9_]+)',value):
            identifier = match[1]+'::'+match[2]
            if identifier in allowed:failed.add(identifier)
        for category in TYPES:
            if re.search(r'\b'+category+r'\b',value):types.add(category)
    return {'failed_tests':sorted(failed),'exception_types':sorted(types)}


def main():
    config=json.loads((ROOT/'scripts/release-diagnostics-request.json').read_text())
    runs=config['runs']
    if not isinstance(runs,list) or len(runs)>3 or any(type(run) is not int or run<=0 for run in runs):
        raise SystemExit('Invalid diagnostic request')
    output=[]
    for run in runs:
        # Never forward subprocess stderr or arbitrary GitHub/log fields.
        result=subprocess.run(['gh','api',f'repos/sleeper-lfy/my-jellyfin/actions/runs/{run}/logs'],capture_output=True)
        if result.returncode:
            output.append({'run':run,'status':'logs_unavailable'});continue
        try:
            with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
                logs=[archive.read(item).decode(errors='replace') for item in archive.infolist()
                      if not item.is_dir() and item.file_size<=20*1024*1024]
            output.append({'run':run,'status':'read',**summarize(logs)})
        except Exception:
            output.append({'run':run,'status':'invalid_log_archive'})
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
