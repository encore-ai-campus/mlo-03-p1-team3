"""Run installer entry points with harmless stand-ins to prove reset stops early."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('script',['mariadb-master.sh','mongodb.sh'])
def test_unconfirmed_reset_never_reaches_package_or_database_commands(tmp_path,script):
    source=Path(__file__).parents[1]/'vm'/script
    shutil.copy(source,tmp_path/script)
    (tmp_path/'common.sh').write_text('''require_root() { :; }
check_ubuntu_2404() { :; }
load_env() { CONFIRM_DATABASE_RESET=""; }
check_password() { :; }
die() { echo "$*" >&2; exit 7; }
install_mariadb() { echo INSTALL_CALLED; exit 99; }
''')
    env=dict(os.environ,RESET_DATABASES='true')
    env.pop('CONFIRM_DATABASE_RESET',None)
    result=subprocess.run(['bash',str(tmp_path/script)],env=env,capture_output=True,text=True)
    assert result.returncode==7
    assert 'Explicit CONFIRM_DATABASE_RESET' in result.stderr
    assert 'INSTALL_CALLED' not in result.stdout


def test_explicit_confirmation_survives_empty_template_value(tmp_path):
    shutil.copy(Path(__file__).parents[1]/'vm/mariadb-master.sh',tmp_path/'mariadb-master.sh')
    (tmp_path/'common.sh').write_text('''require_root() { :; }
check_ubuntu_2404() { :; }
load_env() { CONFIRM_DATABASE_RESET=""; }
check_password() { :; }
die() { exit 7; }
install_mariadb() { exit 99; }
''')
    result=subprocess.run(['bash',str(tmp_path/'mariadb-master.sh')],env=dict(os.environ,RESET_DATABASES='true',CONFIRM_DATABASE_RESET='ERASE_PODOBANK_TEST_DATA'),capture_output=True,text=True)
    assert result.returncode==99
