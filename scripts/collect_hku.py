"""Run bounded HTTP or Playwright discovery and collection on a network-enabled host."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faculty_atlas.collect import DIRECTORY,MESSAGES,collect,discover,fetch,prepare
from faculty_atlas.db import connect

p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--browser',action='store_true');p.add_argument('--refresh',action='store_true');p.add_argument('--limit',type=int)
a=p.parse_args();con=connect(a.data)
sid=fetch(con,a.data,DIRECTORY,browser=a.browser,refresh=a.refresh)
records=discover(con,a.data,sid)
print(f'Discovered {len(records)} professors')
collect(con,a.data,browser=a.browser,refresh=a.refresh,limit=a.limit)
fetch(con,a.data,MESSAGES,browser=a.browser,refresh=a.refresh)
prepare(con,a.data,Path('work/batches'))
con.close()
