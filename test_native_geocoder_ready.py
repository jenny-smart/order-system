import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('values,expected', [
    ({}, False),
    ({'#area_id': '25'}, False),
    ({'#area_id': '25', '#company_id': '1'}, True),
])
def test_backend_form_waits_for_service_area_fields(values, expected):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required to evaluate JavaScript readiness predicate')
    source = Path(__file__).parent / 'backend_address_form.py'
    tree = ast.parse(source.read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == 'wait_for_function']
    call = next(n for n in calls if '#area_id' in ast.literal_eval(n.args[0]))
    expression = ast.literal_eval(call.args[0])
    script = 'const values = ' + json.dumps(values) + ';\n'
    script += 'global.document = {querySelector: selector => selector in values ? {value: values[selector]} : null};\n'
    script += 'global.google = {maps: {Geocoder: class Mr {constructor() {throw Error("must not instantiate");}}}};\n'
    script += 'const expression = ' + json.dumps(expression) + ';\n'
    # Playwright calls the evaluated value if it is a function.
    script += 'const value = eval(expression); const ready = typeof value === "function" ? value() : value;\n'
    script += 'require("assert").strictEqual(ready, ' + json.dumps(expected) + ');'
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
