import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.getenv('WATCHMYWORK_DATA_DIR', str(Path(__file__).parent / 'data')))

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return uuid.uuid4().hex

@contextmanager
def connect():
    database = Path(os.environ['DATABASE_PATH']) if os.getenv('DATABASE_PATH') else DATA / 'watchmywork.sqlite3'
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS objects (kind TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS results (run_id TEXT, row_index INTEGER, status TEXT NOT NULL, value TEXT, reason TEXT, retries INTEGER DEFAULT 0, seconds REAL DEFAULT 0, source TEXT DEFAULT 'executor', PRIMARY KEY(run_id,row_index));
        CREATE TABLE IF NOT EXISTS inference (id TEXT PRIMARY KEY, dataset_id TEXT, workflow_id TEXT, latency REAL, success INTEGER, created_at TEXT);
        ''')
    for demo in listing('demo'):
        if demo['state'] == 'recording':
            demo['state'] = 'interrupted'
            put('demo', demo)
    for run in listing('run'):
        if run['state'] in ('running', 'retrying'):
            run['state'] = 'paused'
            put('run', run)

def put(kind, item):
    with connect() as db:
        db.execute('INSERT INTO objects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (kind, item['id'], json.dumps(item)))
    return item

def get(kind, item_id):
    with connect() as db:
        row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, item_id)).fetchone()
    return json.loads(row['body']) if row else None

def listing(kind):
    with connect() as db:
        rows = db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
    return [json.loads(r['body']) for r in rows]

def results(run_id):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM results WHERE run_id=? ORDER BY row_index', (run_id,))]

def checkpoint(run_id, row_index, status, value='', reason='', retries=0, seconds=0, source='executor'):
    with connect() as db:
        db.execute('INSERT INTO results VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(run_id,row_index) DO UPDATE SET status=excluded.status,value=excluded.value,reason=excluded.reason,retries=excluded.retries,seconds=excluded.seconds,source=excluded.source', (run_id, row_index, status, value, reason, retries, seconds, source))
