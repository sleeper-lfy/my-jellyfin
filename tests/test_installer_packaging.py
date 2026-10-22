"""Validate delivery integrity; these checks do not run the Windows installer."""
import hashlib
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('installer_target',Path(__file__).parents[1]/'scripts/package-installer-target.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_direct_and_split_delivery_roundtrip(tmp_path):
    source=tmp_path/'fixture.exe';payload=b'MZ'+bytes(range(256))*15;source.write_bytes(payload)
    target=tmp_path/'target'
    direct=module.package(source,target,'a'*40,direct_limit=10000)
    assert (target/direct['file']).read_bytes()==payload
    assert direct['parts']==[]
    split=module.package(source,target,'b'*40,direct_limit=1000,chunk_size=512)
    assert not (target/direct['file']).exists()
    reconstructed=b''.join((target/p['name']).read_bytes() for p in split['parts'])
    assert reconstructed==payload
    assert hashlib.sha256(reconstructed).hexdigest()==split['sha256']
    for part in split['parts']:
        data=(target/part['name']).read_bytes()
        assert len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
    module.package(source,target,'c'*40,direct_limit=10000)
    assert not list(target.glob('*.part*'))
    assert (target/'Lumen-Setup-x64.exe.sha256').read_text(encoding='utf-8').split()[0]==hashlib.sha256(payload).hexdigest()


def test_refuses_non_windows_input(tmp_path):
    source=tmp_path/'linux';source.write_bytes(b'\x7fELF')
    with pytest.raises(ValueError,match='Windows EXE'):module.package(source,tmp_path/'target','d'*40)
    assert not (tmp_path/'target').exists()
