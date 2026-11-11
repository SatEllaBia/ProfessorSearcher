"""Package portable source, snapshots and a consistent SQLite backup; omit caches."""
import argparse
from pathlib import Path
import sqlite3
import tempfile
import zipfile

def package(destination):
    root=Path(__file__).resolve().parents[1]
    excluded={'.git','.venv','.uv-cache','__pycache__','work','dist','embedding-cache','discovery-cache'}
    destination=destination.resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        backup=Path(temp)/'faculty.sqlite'
        with sqlite3.connect(f'file:{root / "data/faculty.sqlite"}?mode=ro',uri=True) as source:
            with sqlite3.connect(backup) as target:source.backup(target)
        with sqlite3.connect(backup) as con:
            dump='\n'.join(con.iterdump())+'\n'
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(root.rglob('*')):
                relative=file.relative_to(root)
                if not file.is_file() or any(part in excluded for part in relative.parts):continue
                if file==destination or file.suffix in ('.pyc','.log') or file.name.endswith(('.sqlite-wal','.sqlite-shm')):continue
                name=str(Path('faculty-atlas')/relative)
                if relative==Path('data/faculty.sqlite'):archive.write(backup,name)
                elif relative==Path('data/faculty.sql'):archive.writestr(name,dump)
                else:archive.write(file,name)
    print(destination)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    package(parser.parse_args().out)
