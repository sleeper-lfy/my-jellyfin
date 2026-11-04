import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('cleanup',Path(__file__).parents[1]/'scripts/cleanup-releases.py')
cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)


def release(tag):return {'tag_name':tag}


def test_keep_entire_014_family_and_delete_only_listed_older_releases():
    tags=['v0.4.14-preview.1','v0.4.14','0.4.14-preview.2','v0.4.12','windows-old','v0.4.140']
    keep,delete=cleanup.select_releases(list(map(release,tags)),'0.4.14',['v0.4.12','windows-old','v0.4.140'],'v0.4.14-preview.1')
    assert [r['tag_name'] for r in keep]==tags[:3]
    assert [r['tag_name'] for r in delete]==tags[3:]


def test_missing_protected_release_aborts_before_any_deletion():
    with pytest.raises(AssertionError,match='missing'):
        cleanup.select_releases([release('v0.4.12')],'0.4.14',['v0.4.12'],'v0.4.14-preview.1')


def test_unexpected_or_concurrently_added_release_aborts_before_any_deletion():
    with pytest.raises(AssertionError,match='Unexpected'):
        cleanup.select_releases([release('v0.4.14-preview.1'),release('v0.4.15')],'0.4.14',[],'v0.4.14-preview.1')


def test_already_clean_list_is_a_safe_noop():
    kept,deleting=cleanup.select_releases([release('v0.4.14-preview.1')],'0.4.14',['v0.4.12'],'v0.4.14-preview.1')
    assert len(kept)==1 and deleting==[]


def test_protection_cannot_point_outside_retained_version():
    with pytest.raises(AssertionError):cleanup.select_releases([release('v0.4.12')],'0.4.14',[],'v0.4.12')
