import json
from pathlib import Path
import pytest
from PySide6.QtGui import QImage,QColor
from lumen.local_artwork import refresh_local_artwork
from lumen.artwork import still_paths
from lumen.core import ImportCancelled


def picture(path,color,width=160,height=90):
    image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(QColor(color));image.save(str(path));return str(path)


def test_missing_and_overwrite_only_change_images_and_leave_originals(qapp,library,video_factory):
    source=video_factory('Manual artwork.mp4');library.import_folder(source.parent,'movie',fast=True)
    work=library.query()[0];file=work['files'][0]
    old=picture(library.directory/'cache'/'existing.jpg','blue')
    with library.db:
        library.db.execute('UPDATE works SET thumbnail=?,rating=9,favorite=1,locked=? WHERE id=?',(old,json.dumps(['poster']),work['id']))
        library.db.execute('UPDATE files SET position=42 WHERE id=?',(file['id'],))
    folder=source.parent
    picture(folder/'poster.jpg','red',100,180);picture(folder/'thumb.jpg','green');picture(folder/'shot.jpg','yellow')
    nfo=source.with_suffix('.nfo');nfo.write_text('<movie><title>Do not replace title</title><poster>poster.jpg</poster><thumb>thumb.jpg</thumb><fanart>shot.jpg</fanart></movie>',encoding='utf-8')
    originals={path:path.read_bytes() for path in [source,nfo,folder/'poster.jpg',folder/'thumb.jpg',folder/'shot.jpg']}
    result=refresh_local_artwork(library,folder,'missing',work['id'])
    current=library.work(work['id'])
    assert result['poster']==0 and result['thumbnail']==1 and result['stills']==1
    assert current['thumbnail']==old and current['rating']==9 and current['favorite']==1
    assert current['files'][0]['position']==42 and current['title']==work['title']
    assert QImage(current['metadata']['nfo_thumbnails'][str(file['id'])]).pixelColor(10,10).green()>80
    result=refresh_local_artwork(library,folder,'overwrite',work['id'])
    current=library.work(work['id'])
    assert result['poster']==1 and QImage(current['thumbnail']).pixelColor(10,10).red()>200
    assert len(still_paths(current))==1
    assert all(path.read_bytes()==data for path,data in originals.items())
    window_metadata=current['metadata'];assert 'Do not replace title' not in json.dumps(window_metadata)


def test_batch_scope_and_cancel_keep_unrelated_works(qapp,library,video_factory):
    first=video_factory('Batch selected.mp4');other=video_factory('Batch unrelated.mp4','red')
    for video in [first,other]:library.import_folder(video.parent,'movie',fast=True)
    picture(first.parent/'poster.jpg','green',100,180)
    first.with_suffix('.nfo').write_text('<movie><title>Artwork</title><poster>poster.jpg</poster></movie>')
    result=refresh_local_artwork(library,first.parent)
    assert result['works']==1
    unrelated=next(work for work in library.query() if work['title']=='Batch unrelated')
    assert not unrelated['thumbnail']
    with pytest.raises(ImportCancelled):refresh_local_artwork(library,first.parent,cancelled=lambda:True)


def test_unsafe_nfo_paths_and_malformed_nfo_are_reported_without_erasing_images(qapp,library,video_factory,tmp_path):
    video=video_factory('Untrusted art.mp4');library.import_folder(video.parent,'movie',fast=True);work=library.query()[0]
    outside=Path(picture(tmp_path/'outside.jpg','red'))
    video.with_suffix('.nfo').write_text('<movie><poster>'+str(outside)+'</poster><thumb>../../outside.jpg</thumb></movie>')
    result=refresh_local_artwork(library,video.parent,'overwrite',work['id'])
    assert result['poster']==0 and result['thumbnail']==0
    video.with_suffix('.nfo').write_text('<movie><title>Broken')
    assert refresh_local_artwork(library,video.parent,work_id=work['id'])['warnings']
