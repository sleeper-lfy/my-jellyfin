import sqlite3
from pathlib import Path
import pytest
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from lumen.core import Library
from lumen.backup import restore_database
from lumen.player import Player
from test_core import add_work


def spin(app,seconds=.1):
    loop=QEventLoop();QTimer.singleShot(round(seconds*1000),loop.quit);loop.exec();app.processEvents()


def test_likes_are_favorites_exclusive_and_persistent(library):
    work=add_work(library,'Preferences')
    library.update_personal(work,favorite=True,liked=True,rating=8)
    library.update_personal(work,disliked=True)
    saved=library.work(work);assert saved['favorite']==0 and saved['liked']==0 and saved['disliked']==1 and saved['rating']==8
    library.update_personal(work,liked=True);assert library.work(work)['disliked']==0
    library.update_personal(work,liked=False,rating=None);assert library.work(work)['favorite']==0
    with pytest.raises(ValueError):library.update_personal(work,liked=True,disliked=True)
    other=Library(library.directory);assert other.work(work)['liked']==0 and other.work(work)['rating'] is None;other.close()


def test_old_database_and_old_backup_migrate_without_changing_original(tmp_path):
    folder=tmp_path/'old';lib=Library(folder);work=add_work(lib,'Old favorite');lib.update_personal(work,favorite=True,rating=7);lib.close()
    database=folder/'library.sqlite';db=sqlite3.connect(database);db.execute('ALTER TABLE works DROP COLUMN liked');db.commit();db.close()
    backup=tmp_path/'old-backup.sqlite';backup.write_bytes(database.read_bytes())
    migrated=Library(folder);assert migrated.work(work)['favorite']==1 and migrated.work(work)['liked']==1
    migrated.update_personal(work,liked=True);restore_database(migrated,backup)
    assert migrated.work(work)['rating']==7 and migrated.work(work)['liked']==1
    original=sqlite3.connect(backup);assert 'liked' not in {row[1] for row in original.execute('PRAGMA table_info(works)')};original.close();migrated.close()


def test_playing_controls_save_without_restarting_video(qapp,library,video_factory):
    source=video_factory('Player preferences.mp4','blue',10);library.import_folder(source.parent,'movie')
    file=library.query()[0]['files'][0];player=Player(library);player.open_file(file);spin(qapp,.7)
    session=player.session.id;assert player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
    player.like.click();assert library.work(file['work_id'])['liked']==1
    player.negative.click();work=library.work(file['work_id']);assert work['favorite']==0 and work['disliked']==1 and work['liked']==0
    def choose(value):
        def trigger():
            menu=QApplication.activePopupWidget();action=next(a for a in menu.actions() if a.text()==('清除评分' if value is None else f'{value} 分'));action.trigger();menu.close()
        QTimer.singleShot(30,trigger);player.personal_rating.click()
    choose(9);assert library.work(file['work_id'])['rating']==9
    choose(None);assert library.work(file['work_id'])['rating'] is None
    assert player.file['id']==file['id'] and player.session.id==session and player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
    player.close()


def test_failed_player_save_restores_buttons_and_success_clears_error(qapp,library,monkeypatch):
    work=add_work(library,'Retry');player=Player(library);player.file=library.work(work)['files'][0];player.update_like(library.work(work))
    original=library.update_personal
    def fail(*args,**kwargs):raise ValueError('temporary database error')
    monkeypatch.setattr(library,'update_personal',fail);player.like.click()
    assert library.work(work)['liked']==0 and not player.like.isChecked() and '偏好未保存' in player.error.text()
    monkeypatch.setattr(library,'update_personal',original);player.like.click()
    assert library.work(work)['liked']==1 and '偏好未保存' not in player.error.text();player.close()


def test_independent_legacy_preferences_merge_once_and_backup_stays_unchanged(tmp_path):
    folder=tmp_path/'legacy';lib=Library(folder);positive=add_work(lib,'Legacy positive');negative=add_work(lib,'Legacy negative')
    with lib.db:
        lib.db.execute('UPDATE works SET favorite=0,liked=1,rating=8 WHERE id=?',(positive,))
        lib.db.execute('UPDATE works SET favorite=1,liked=0,disliked=1 WHERE id=?',(negative,))
        lib.db.execute("DELETE FROM settings WHERE key='personal_unified_v1'")
    backup=tmp_path/'independent.sqlite';lib.backup(backup);lib.close()
    lib=Library(folder);assert lib.work(positive)['favorite']==lib.work(positive)['liked']==1
    assert lib.work(positive)['rating']==8 and lib.work(negative)['favorite']==0 and lib.work(negative)['disliked']==1
    lib.update_personal(positive,favorite=False);lib.close();lib=Library(folder);assert lib.work(positive)['favorite']==0
    restore_database(lib,backup);assert lib.work(positive)['favorite']==1 and lib.work(positive)['rating']==8
    original=sqlite3.connect(backup);assert original.execute('SELECT favorite,liked FROM works WHERE id=?',(positive,)).fetchone()==(0,1);original.close();lib.close()
