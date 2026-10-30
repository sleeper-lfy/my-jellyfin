BEGIN TRANSACTION;
CREATE TABLE activity (
          session_id TEXT REFERENCES sessions(id), day TEXT NOT NULL, watched REAL NOT NULL,
          PRIMARY KEY(session_id,day));
CREATE TABLE bookmarks (
          id TEXT PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          position REAL NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', image TEXT, created TEXT NOT NULL);
CREATE TABLE external_ids (kind TEXT NOT NULL, namespace TEXT NOT NULL, value TEXT NOT NULL, work_id INTEGER NOT NULL REFERENCES works(id), UNIQUE(kind,namespace,value));
CREATE TABLE files (
          id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id), path TEXT UNIQUE NOT NULL,
          digest TEXT NOT NULL, root TEXT NOT NULL, season INTEGER, episode INTEGER,
          duration REAL NOT NULL, position REAL NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0);
INSERT INTO "files" VALUES(1,1,'C:/fixture/movie.mp4','fixture-digest','C:/fixture',NULL,NULL,120.0,35.0,0);
CREATE TABLE import_cache (
          file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
          size INTEGER NOT NULL, modified INTEGER NOT NULL, quick TEXT NOT NULL,
          full TEXT, sidecars TEXT NOT NULL DEFAULT '', pending INTEGER NOT NULL DEFAULT 0);
CREATE TABLE lists (name TEXT PRIMARY KEY, filters TEXT NOT NULL);
CREATE TABLE name_keys (key TEXT PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id));
CREATE TABLE playback_preferences (
          file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE, value TEXT NOT NULL DEFAULT '{}');
CREATE TABLE sessions (
          id TEXT PRIMARY KEY, file_id INTEGER REFERENCES files(id), started TEXT NOT NULL,
          ended TEXT, watched REAL NOT NULL DEFAULT 0);
INSERT INTO "sessions" VALUES('fixture-session',1,'2026-01-01',NULL,35.0);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO "settings" VALUES('personal_unified_v1','true');
INSERT INTO "settings" VALUES('queue','[1]');
CREATE TABLE sources (
          work_id INTEGER REFERENCES works(id), plugin TEXT NOT NULL, site TEXT NOT NULL,
          source_id TEXT NOT NULL, url TEXT NOT NULL, updated TEXT NOT NULL, site_added TEXT,
          rating REAL, UNIQUE(plugin,source_id));
CREATE TABLE tasks (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT '{}', error TEXT, updated TEXT NOT NULL);
CREATE TABLE works (
          id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, year INTEGER, metadata TEXT NOT NULL DEFAULT '{}',
          rating INTEGER CHECK(rating BETWEEN 1 AND 10), favorite INTEGER NOT NULL DEFAULT 0,
          watchlist INTEGER NOT NULL DEFAULT 0, disliked INTEGER NOT NULL DEFAULT 0,
          locked TEXT NOT NULL DEFAULT '[]', added TEXT NOT NULL, discovered TEXT, thumbnail TEXT, liked INTEGER NOT NULL DEFAULT 0 CHECK(liked IN (0,1)));
INSERT INTO "works" VALUES(1,'old-fixture','movie','Historical fixture',NULL,'{}',8,1,0,0,'[]','2026-01-01',NULL,NULL,0);
CREATE INDEX files_work ON files(work_id);
CREATE INDEX files_digest ON files(digest);
CREATE INDEX works_kind ON works(kind,year);
CREATE INDEX import_quick ON import_cache(quick,size);
CREATE INDEX bookmarks_file ON bookmarks(file_id,position);
COMMIT;
