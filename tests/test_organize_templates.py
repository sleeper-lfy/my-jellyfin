from pathlib import Path
import pytest
from PySide6.QtWidgets import QPushButton
from lumen.files import plan_move, execute_move
from lumen.organize_templates import validate_rule, save_rule, load_rule
from lumen.organize_ui import Organizer
from lumen.ui import MainWindow


def work_with_files(library, tmp_path, names):
    root = tmp_path/'incoming'; root.mkdir()
    for name in names: (root/name).write_bytes(('video-'+name).encode())
    library.import_folder(root, 'vr', fast=True)
    work = library.query()[0]
    library.edit_metadata(work['id'], {'title':'ABC-123 Title', 'year':2024}, [])
    return root, library.work(work['id'])


def test_default_plan_is_unchanged_and_preview_never_moves(library, tmp_path):
    root, work = work_with_files(library,tmp_path,['ABC-123.mp4'])
    source=root/'ABC-123.mp4';(root/'ABC-123.zh.srt').write_text('subtitle')
    plan=plan_move(library,work['id'],tmp_path/'out')
    assert {Path(pair['target']).relative_to(tmp_path/'out') for pair in plan} == {
        Path('ABC-123 Title (2024)/ABC-123.mp4'),Path('ABC-123 Title (2024)/ABC-123.zh.srt')}
    assert source.exists() and not (tmp_path/'out').exists()
    assert library.work(work['id'])['files'][0]['path']==str(source)
    assert not library.db.execute("SELECT 1 FROM tasks WHERE kind='move'").fetchone()


def test_template_renames_video_and_matching_sidecars_and_preserves_history(library,tmp_path):
    root,work=work_with_files(library,tmp_path,['abc_123-CD1.mp4'])
    for suffix in ('.zh.forced.srt','.nfo','.jpg'):(root/('abc_123-CD1'+suffix)).write_text('sidecar '+suffix)
    library.update_personal(work['id'],favorite=True,rating=9)
    file_id=work['files'][0]['id']
    with library.db:library.db.execute('UPDATE files SET position=42 WHERE id=?',(file_id,))
    rule={'folder':'{code}/{title}{year_suffix}','filename':'{code}'}
    plan=plan_move(library,work['id'],tmp_path/'out',rule)
    assert len(plan)==4
    assert {Path(pair['target']).name for pair in plan}=={'ABC-123-CD1.mp4','ABC-123-CD1.zh.forced.srt','ABC-123-CD1.nfo','ABC-123-CD1.jpg'}
    task=execute_move(library,plan)
    updated=library.work(work['id'])
    assert updated['files'][0]['id']==file_id and updated['files'][0]['position']==42
    assert updated['rating']==9 and updated['favorite']
    assert all(Path(pair['target']).is_file() and not Path(pair['source']).exists() for pair in plan)
    assert execute_move(library,task_id=task)==task


def test_parts_and_versions_do_not_collide(library,tmp_path):
    _,work=work_with_files(library,tmp_path,['ABC-123-CD1.mp4','ABC-123-CD2.mp4','ABC-123.1080p.mkv','ABC-123.2160p.mkv'])
    plan=plan_move(library,work['id'],tmp_path/'out',{'folder':'{code}','filename':'{code}'})
    names={Path(pair['target']).name for pair in plan}
    assert 'ABC-123-CD1.mp4' in names and 'ABC-123-CD2.mp4' in names
    assert len(names)==4 and len([name for name in names if '-V' in name])==2


def test_saved_target_rule_precedes_category_and_empty_override_preserves_names(library,tmp_path):
    _,work=work_with_files(library,tmp_path,['ABC-123.mp4'])
    destination=tmp_path/'out'
    save_rule(library,'vr',{'folder':'{code}','filename':'{title}'})
    assert Path(plan_move(library,work['id'],destination)[0]['target']).name=='ABC-123 Title.mp4'
    save_rule(library,'vr',{'folder':'','filename':''},destination)
    assert Path(plan_move(library,work['id'],destination)[0]['target']).name=='ABC-123.mp4'
    assert load_rule(library,'vr',destination)=={'folder':'','filename':''}


@pytest.mark.parametrize('template',['../{title}','/{title}','C:/Movies/{title}','{title.__class__}','{title!r}','{title:20}','{title}//x','{title}/..','{missing}','{title'])
def test_invalid_template_is_rejected(template):
    with pytest.raises(ValueError):validate_rule({'folder':template})


def test_missing_code_and_existing_targets_are_not_silently_replaced(library,tmp_path):
    _,work=work_with_files(library,tmp_path,['ABC-123.mp4'])
    target=tmp_path/'out'/'ABC-123'/'ABC-123.mp4';target.parent.mkdir(parents=True);target.write_bytes(b'existing')
    with pytest.raises(FileExistsError):plan_move(library,work['id'],tmp_path/'out',{'folder':'{code}','filename':'{code}'})
    assert target.read_bytes()==b'existing'
    library.edit_metadata(work['id'],{'year':None},[])
    with pytest.raises(ValueError,match='year'):plan_move(library,work['id'],tmp_path/'out',{'folder':'{year}','filename':''})


def test_target_symlink_escape_is_rejected(library,tmp_path):
    _,work=work_with_files(library,tmp_path,['ABC-123.mp4'])
    destination=tmp_path/'out';destination.mkdir();outside=tmp_path/'outside';outside.mkdir()
    try:(destination/'ABC-123').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('当前系统没有创建符号链接的特权（Windows 需要管理员或开发者模式）')
    with pytest.raises(ValueError,match='符号链接'):plan_move(library,work['id'],destination,{'folder':'{code}','filename':'{code}'})
    assert not list(outside.iterdir())


def test_ui_requires_preview_and_invalidates_it_when_template_changes(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        root,work=work_with_files(window.library,tmp_path,['ABC-123.mp4'])
        window.run_job=lambda title,function,callback=None:callback(function(window.library,lambda *args:None)) if callback else function(window.library,lambda *args:None)
        dialog=Organizer(window,work['id']);dialog.show();dialog.target.setText(str(tmp_path/'out'))
        assert not dialog.execute.isEnabled()
        dialog.fields.folder.setText('{code}');dialog.fields.filename.setText('{code}')
        dialog.preview.click()
        assert dialog.execute.isEnabled() and dialog.table.rowCount()==1
        assert (root/'ABC-123.mp4').exists() and not (tmp_path/'out').exists()
        dialog.fields.filename.setText('{title}')
        assert not dialog.execute.isEnabled() and dialog.plan is None
        dialog.close()
    finally:window.close()


def test_multipart_nfo_image_references_survive_renaming_and_shared_sources_remain(library,tmp_path):
    import xml.etree.ElementTree as ET
    root,work=work_with_files(library,tmp_path,['ABC-123-CD1.mp4','ABC-123-CD2.mp4'])
    shared=root/'lumen-poster-hash.jpg';shared.write_bytes(b'picture')
    for video in ('ABC-123-CD1','ABC-123-CD2'):
        (root/(video+'.nfo')).write_text('<movie><title>ABC-123</title><thumb aspect="poster">lumen-poster-hash.jpg</thumb><actor><name>Actor</name><thumb>lumen-poster-hash.jpg</thumb></actor></movie>')
    plan=plan_move(library,work['id'],tmp_path/'out',{'folder':'{code}/{part}','filename':'{title}'})
    image_copies=[pair for pair in plan if Path(pair['source'])==shared]
    assert len(image_copies)==2 and all(pair['keep_source'] for pair in image_copies)
    execute_move(library,plan)
    assert shared.read_bytes()==b'picture'
    for nfo in (tmp_path/'out').rglob('*.nfo'):
        tree=ET.parse(nfo)
        assert (nfo.parent/tree.findtext('thumb')).read_bytes()==b'picture'
        assert nfo.with_suffix('.mp4').is_file()


def test_copy_attachment_recovery_after_publication_preserves_source(library,tmp_path):
    from lumen.core import fingerprint
    import shutil
    root,work=work_with_files(library,tmp_path,['ABC-123.mp4'])
    picture=root/'poster.jpg';picture.write_bytes(b'original-picture')
    plan=plan_move(library,work['id'],tmp_path/'out')
    image=next(pair for pair in plan if pair['source']==str(picture))
    assert image['keep_source']
    target=Path(image['target']);target.parent.mkdir(parents=True);shutil.copy2(picture,target)
    image['state']='published';library.task('copy-recovery','move','running',[image])
    execute_move(library,task_id='copy-recovery')
    assert picture.is_file() and fingerprint(picture)==fingerprint(target)
    execute_move(library,task_id='copy-recovery')
    assert picture.is_file()


def test_nfo_image_escape_is_not_copied(library,tmp_path):
    root,work=work_with_files(library,tmp_path,['ABC-123.mp4'])
    secret=tmp_path/'private.jpg';secret.write_bytes(b'outside')
    (root/'ABC-123.nfo').write_text('<movie><thumb aspect="poster">../private.jpg</thumb></movie>')
    plan=plan_move(library,work['id'],tmp_path/'out',{'folder':'{code}','filename':'{code}'})
    assert all(pair['source']!=str(secret) for pair in plan)
    assert secret.read_bytes()==b'outside'


def test_exported_multifile_nfo_and_images_survive_template_organization(qapp,library,tmp_path):
    import xml.etree.ElementTree as ET
    from PySide6.QtGui import QImage,QColor
    from lumen.nfo_export import export_works
    root,work=work_with_files(library,tmp_path,['ABC-123-CD1.mp4','ABC-123-CD2.mp4'])
    picture=tmp_path/'cached-poster.png'
    image=QImage(24,36,QImage.Format.Format_RGB32);image.fill(QColor('blue'));assert image.save(str(picture))
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(picture),work['id']))
    library.edit_metadata(work['id'],{'actors':[{'name':'Actor','photo_cache':str(picture)}],
                                    'stills_cache':[{'url':'https://example.org/still','path':str(picture)}]},[])
    exported=export_works(library,[work['id']])
    assert not exported['errors']
    assert len(list(root.glob('*.nfo')))==2
    original_images=list(root.glob('lumen-*'));assert original_images
    plan=plan_move(library,work['id'],tmp_path/'out',{'folder':'{code}/{part}','filename':'{code} - {title}'})
    execute_move(library,plan)
    written=list((tmp_path/'out').rglob('*.nfo'));assert len(written)==2
    for nfo in written:
        tree=ET.parse(nfo)
        references=[element.text.strip() for element in tree.iter() if element.tag in {'thumb','poster','fanart','image'} and element.text and element.text.strip().startswith('lumen-')]
        assert references and all((nfo.parent/reference).is_file() for reference in references)
        assert nfo.with_suffix('.mp4').is_file()
    assert all(path.exists() for path in original_images)
