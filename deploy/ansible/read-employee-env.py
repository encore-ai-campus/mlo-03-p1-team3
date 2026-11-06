"""Read only employee keys from a private .env; invoke with Ansible no_log."""
import json
import re
from pathlib import Path
import shlex
import sys

keys = ('EMPLOYEE_PHONE_NUMBER', 'EMPLOYEE_PASSWORD', 'EMPLOYEE_NAME')
try:
    values = {}
    for line in Path(sys.argv[1]).read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:]
        key, separator, value = line.partition('=')
        if separator and key.strip() in keys:
            parts = shlex.split(value, comments=True)
            if len(parts) != 1:
                raise ValueError()
            values[key.strip()] = parts[0]
    if any(not values.get(key) for key in keys):
        raise ValueError()
    if (not re.fullmatch(r'01[0-9]{8,9}', values['EMPLOYEE_PHONE_NUMBER'])
            or not 8 <= len(values['EMPLOYEE_PASSWORD']) <= 128
            or not values['EMPLOYEE_NAME'].strip() or len(values['EMPLOYEE_NAME']) > 50):
        raise ValueError()
except Exception:
    raise SystemExit('Configure EMPLOYEE_PHONE_NUMBER, EMPLOYEE_PASSWORD and EMPLOYEE_NAME in the private backend/.env') from None
print('Employee configuration valid.' if '--check' in sys.argv[2:] else json.dumps(values))
