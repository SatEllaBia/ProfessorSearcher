"""Restore the packaged SQL dump into a new SQLite file; never overwrite a database."""
import argparse
import sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--dump',type=Path,default=Path('data/faculty.sql'));p.add_argument('--out',type=Path,default=Path('work/rebuilt.sqlite'))
a=p.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
if a.out.exists():raise SystemExit(f'Refusing to overwrite {a.out}')
c=sqlite3.connect(a.out)
try:
    c.executescript(a.dump.read_text())
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    print(a.out)
finally:c.close()
