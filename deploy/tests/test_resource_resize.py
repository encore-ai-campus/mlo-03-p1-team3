import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'lab'))
spec=importlib.util.spec_from_file_location('resize_resources',Path(__file__).parents[1]/'lab/resize-resources.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def change(**overrides):
    before={'processors':2,'memory':2048,'state':'on','path':'unchanged.vmx'}
    after={**before,'processors':4,'memory':4096,**overrides}
    return {'mode':'managed','type':'vmworkstation_virtual_machine','name':'server','change':{'actions':['update'],'before':before,'after':after}}


def test_only_cpu_memory_update_is_accepted():
    assert len(module.validate_changes({'resource_changes':[change()]}))==1


@pytest.mark.parametrize('override',[{'path':'other.vmx'},{'state':'off'},{'id':'new-id'}])
def test_path_identity_and_poweroff_are_refused(override):
    with pytest.raises(ValueError):module.validate_changes({'resource_changes':[change(**override)]})


def test_destroy_is_refused_before_stopping_any_vm():
    item=change();item['change']['actions']=['delete','create']
    with pytest.raises(ValueError):module.validate_changes({'resource_changes':[item]})
