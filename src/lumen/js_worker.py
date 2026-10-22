"""No Python callbacks, filesystem or networking exposed to JavaScript."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    from .sandbox import limit_worker
    limit_worker()
    args = [arg for arg in sys.argv[1:] if arg != '--plugin-worker']
    input_path, output_path = map(Path, args)
    if input_path.stat().st_size > 6_000_000:
        raise ValueError('插件输入超限')
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    engine = QJSEngine()
    result = engine.evaluate(payload['script'], 'plugin.js')
    if result.isError():
        raise RuntimeError(result.toString())
    function = engine.globalObject().property(payload['function'])
    if not function.isCallable():
        raise ValueError('插件未实现函数：' + payload['function'])
    argument = engine.evaluate('(' + json.dumps(payload['argument'], ensure_ascii=True) + ')')
    result = function.call([argument])
    if result.isError():
        raise RuntimeError(result.toString())
    output = engine.globalObject().property('JSON').property('stringify').call([result]).toString()
    if len(output) > 4_000_000:
        raise ValueError('插件输出超限')
    output_path.write_text(json.dumps({'result': json.loads(output)}), encoding='utf-8')


def run():
    try:
        main()
    except Exception as exc:
        args = [arg for arg in sys.argv[1:] if arg != '--plugin-worker']
        if len(args) == 2:
            Path(args[1]).write_text(json.dumps({'error': str(exc)}), encoding='utf-8')
        else:
            raise


if __name__ == '__main__':
    run()
