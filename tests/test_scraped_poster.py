from pathlib import Path
import pytest
from PySide6.QtGui import QImage,QColor
from lumen.artwork import still_paths
from test_gallery_downloads import manager_for
from test_core import add_work


def image_bytes(tmp_path,name,width,height,color='blue'):
    path=tmp_path/(name+'.png')
    image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(QColor(color))
    assert image.save(str(path))
    return path.read_bytes()


@pytest.mark.parametrize('poster_size,expected',[( (200,300),'poster'),((600,300),'portrait'),((200,600),'portrait'),(None,'portrait')])
def test_scrape_selects_portrait_still_only_when_poster_ratio_wrong(library,qapp,tmp_path,monkeypatch,poster_size,expected):
    manager=manager_for(library);requests=[]
    data={'https://example.test/wide':image_bytes(tmp_path,'wide',640,360),
          'https://example.test/portrait':image_bytes(tmp_path,'portrait',200,300,'red')}
    metadata={'id':'ratio','title':'Poster ratio','url':'https://example.test/detail',
              'stills':['https://example.test/wide','https://example.test/portrait']}
    if poster_size:
        metadata['poster']='https://example.test/poster'
        data[metadata['poster']]=image_bytes(tmp_path,'poster',*poster_size)
    def fetch(plugin,url,**kwargs):requests.append(url);return data[url],'image/png'
    monkeypatch.setattr(manager,'fetch',fetch)
    identifier=manager.merge('catalog-json',metadata)
    work=library.work(identifier);stills=still_paths(work)
    assert len(stills)==2
    if expected=='portrait':
        assert work['thumbnail']==stills[1]
        assert QImage(work['thumbnail']).pixelColor(20,20).red()>240
    else:assert work['thumbnail'] not in stills
    assert requests.count('https://example.test/portrait')==1
    manager.merge('catalog-json',metadata,identifier)
    assert requests.count('https://example.test/portrait')==1


def test_all_wide_stills_crop_copy_and_keep_originals(library,qapp,tmp_path,monkeypatch):
    manager=manager_for(library)
    data=image_bytes(tmp_path,'wide',900,300)
    monkeypatch.setattr(manager,'fetch',lambda *args,**kwargs:(data,'image/png'))
    identifier=manager.merge('catalog-json',{'id':'crop','title':'Crop still','url':'https://example.test/detail',
        'poster':'https://example.test/poster','stills':['https://example.test/still']})
    work=library.work(identifier);original=still_paths(work)[0]
    assert work['thumbnail']!=original
    image=QImage(work['thumbnail']);assert image.width()/image.height()==pytest.approx(2/3,.01)
    assert QImage(original).width()==900 and QImage(original).height()==300
    before=Path(original).read_bytes()
    manager.merge('catalog-json',{'id':'crop','title':'Crop still','url':'https://example.test/detail',
        'poster':'https://example.test/poster','stills':['https://example.test/still']},identifier)
    assert Path(original).read_bytes()==before
    assert library.work(identifier)['thumbnail']==work['thumbnail']


@pytest.mark.parametrize('protection',['manual','locked','nfo'])
def test_scraping_keeps_protected_poster(library,qapp,tmp_path,monkeypatch,protection):
    manager=manager_for(library);identifier=add_work(library,'Protected poster')
    saved=tmp_path/'saved.png';saved.write_bytes(image_bytes(tmp_path,'original',300,200))
    metadata={'nfo_poster':str(saved)} if protection=='nfo' else {}
    library.edit_metadata(identifier,metadata,['poster'] if protection=='locked' else [])
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(saved),identifier))
    if protection=='manual':library.set_setting(f'artwork_{identifier}',{'poster':str(saved)})
    monkeypatch.setattr(manager,'fetch',lambda *args,**kwargs:(image_bytes(tmp_path,'remote',200,300),'image/png'))
    manager.merge('catalog-json',{'id':'protected','title':'Protected poster','year':2024,
        'url':'https://example.test/detail','poster':'https://example.test/poster','stills':['https://example.test/still']},identifier)
    assert library.work(identifier)['thumbnail']==str(saved)


def test_bad_poster_and_failed_still_keep_work_and_log_image_failures(library,qapp,monkeypatch):
    manager=manager_for(library)
    monkeypatch.setattr(manager,'fetch',lambda *args,**kwargs:(b'broken','image/png'))
    identifier=manager.merge('catalog-json',{'id':'broken','title':'Broken images','url':'https://example.test/detail',
        'poster':'https://example.test/poster','stills':['https://example.test/still']})
    assert library.work(identifier)['thumbnail'] is None
    assert library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='image' AND status='failed'").fetchone()[0]==2


def test_wrong_ratio_without_stills_keeps_available_poster(library,qapp,tmp_path,monkeypatch):
    manager=manager_for(library);data=image_bytes(tmp_path,'wide-only',640,360)
    monkeypatch.setattr(manager,'fetch',lambda *args,**kwargs:(data,'image/png'))
    identifier=manager.merge('catalog-json',{'id':'no-stills','title':'No stills','url':'https://example.test/detail',
        'poster':'https://example.test/poster'})
    assert QImage(library.work(identifier)['thumbnail']).width()==640
