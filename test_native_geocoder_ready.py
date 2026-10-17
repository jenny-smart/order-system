import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('setup,expected', [
    ('', False),
    ('global.google = {maps: {}};', False),
    ('global.google = {maps: {Geocoder: class Mr {constructor() {throw Error("must not instantiate");}}}};', True),
])
def test_geocoder_wait_returns_boolean_without_invoking_class(setup, expected):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required to evaluate JavaScript readiness predicate')
    source = Path(__file__).parent / 'backend_address_form.py'
    tree = ast.parse(source.read_text())
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == 'wait_for_function')
    expression = ast.literal_eval(call.args[0])
    script = setup + '\nconst expression = ' + json.dumps(expression) + ';\n'
    # Playwright calls the evaluated value if it is a function.
    script += 'const value = eval(expression); const ready = typeof value === "function" ? value() : value;\n'
    script += 'require("assert").strictEqual(ready, ' + json.dumps(expected) + ');'
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
