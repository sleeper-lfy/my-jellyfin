"""Legacy baseline, retained verbatim for ordered database migrations."""
BASELINE = r'''
        CREATE TABLE IF NOT EXISTS works (
          id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, year INTEGER, metadata TEXT NOT NULL DEFAULT '{}',
          rating INTEGER CHECK(rating BETWEEN 1 AND 10), favorite INTEGER NOT NULL DEFAULT 0,
          watchlist INTEGER NOT NULL DEFAULT 0, disliked INTEGER NOT NULL DEFAULT 0,
          locked TEXT NOT NULL DEFAULT '[]', added TEXT NOT NULL, discovered TEXT, thumbnail TEXT);
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id), path TEXT UNIQUE NOT NULL,
          digest TEXT NOT NULL, root TEXT NOT NULL, season INTEGER, episode INTEGER,
          duration REAL NOT NULL, position REAL NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS files_work ON files(work_id);
        CREATE INDEX IF NOT EXISTS files_digest ON files(digest);
        CREATE INDEX IF NOT EXISTS works_kind ON works(kind,year);
        CREATE TABLE IF NOT EXISTS import_cache (
          file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
          size INTEGER NOT NULL, modified INTEGER NOT NULL, quick TEXT NOT NULL,
          full TEXT, sidecars TEXT NOT NULL DEFAULT '', pending INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS import_quick ON import_cache(quick,size);
        CREATE TABLE IF NOT EXISTS sources (
          work_id INTEGER REFERENCES works(id), plugin TEXT NOT NULL, site TEXT NOT NULL,
          source_id TEXT NOT NULL, url TEXT NOT NULL, updated TEXT NOT NULL, site_added TEXT,
          rating REAL, UNIQUE(plugin,source_id));
        CREATE TABLE IF NOT EXISTS name_keys (key TEXT PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id));
        CREATE TABLE IF NOT EXISTS external_ids (kind TEXT NOT NULL, namespace TEXT NOT NULL, value TEXT NOT NULL, work_id INTEGER NOT NULL REFERENCES works(id), UNIQUE(kind,namespace,value));
        INSERT OR IGNORE INTO name_keys SELECT identity,id FROM works;
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, file_id INTEGER REFERENCES files(id), started TEXT NOT NULL,
          ended TEXT, watched REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS activity (
          session_id TEXT REFERENCES sessions(id), day TEXT NOT NULL, watched REAL NOT NULL,
          PRIMARY KEY(session_id,day));
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT '{}', error TEXT, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lists (name TEXT PRIMARY KEY, filters TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS playback_preferences (
          file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE, value TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS bookmarks (
          id TEXT PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          position REAL NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', image TEXT, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS bookmarks_file ON bookmarks(file_id,position);
        '''
