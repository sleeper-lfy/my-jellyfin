from pathlib import Path
import pytest
from lumen.versions import inspect_versions,set_preferred,duplicate_candidates


def test_inspection_reads_actual_streams_and_reuses_unchanged_cache(library,video_factory,monkeypatch):
    path=video_factory('Version.2024.mp4')
    library.import_folder(path.parent,'movie',fast=True);work=library.query()[0]
    first=inspect_versions(library,[work['id']])[0]
    assert first['resolution']=='320×180' and first['codec']=='mpeg4' and 'aac' in first['audio']
    assert first['size']==path.stat().st_size and first['duration']>0 and not first['error']
    def no_probe(*args,**kwargs):raise AssertionError('unchanged file should use cached stream data')
    monkeypatch.setattr('lumen.versions.media_process',no_probe)
    assert inspect_versions(library,[work['id']])[0]['resolution']=='320×180'


def test_corrupt_file_reports_error_without_hiding_other_versions(library,tmp_path,video_factory):
    good=video_factory('Good.2024.mp4');library.import_folder(good.parent,'movie',fast=True)
    root=tmp_path/'bad';root.mkdir();(root/'Bad.mp4').write_bytes(b'not-a-video');library.import_folder(root,'movie',fast=True)
    works=library.query();rows=inspect_versions(library,[work['id'] for work in works])
    assert len(rows)==2 and len([row for row in rows if row['error']])==1


def test_default_selection_rejects_other_work_and_offline_files(library,tmp_path):
    for name in ['One','Two']:
        root=tmp_path/name;root.mkdir();(root/(name+'.mp4')).write_bytes(name.encode());library.import_folder(root,'movie',fast=True)
    first,second=library.query()
    with pytest.raises(ValueError):set_preferred(library,first['id'],second['files'][0]['id'])
    chosen=first['files'][0];set_preferred(library,first['id'],chosen['id'])
    assert library.setting('preferred-file:'+str(first['id']))==chosen['id']
    assert library.resume_file(first['id'])['id']==chosen['id']
    Path(chosen['path']).unlink()
    with pytest.raises(ValueError):set_preferred(library,first['id'],chosen['id'])
    set_preferred(library,first['id'],None)
    assert library.setting('preferred-file:'+str(first['id'])) is None


def test_number_groups_are_candidates_not_identical_file_claims(library,tmp_path):
    for name in ['One','Two']:
        root=tmp_path/name;root.mkdir();(root/'ABC-123.mp4').write_bytes(name.encode());library.import_folder(root,'vr',fast=True)
    groups=duplicate_candidates(library)
    assert len(groups)==1 and groups[0]['basis']=='code' and len(groups[0]['work_ids'])==2
    assert len(library.query())==2


def test_saved_product_code_survives_descriptive_file_renaming():
    from lumen.ingestion import work_codes
    work={'title':'已编辑标题','kind':'vr','metadata':{'external_ids':{'product_code':'ABC-123'}},'files':[{'path':'/media/影片/正片.mp4'}]}
    assert work_codes(work)=={'ABC-123'}
