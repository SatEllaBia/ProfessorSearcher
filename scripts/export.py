"""Convenience wrapper: python scripts/export.py [faculty CLI export options]."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from faculty_atlas.cli import main
sys.argv.insert(1,'export')
main()
