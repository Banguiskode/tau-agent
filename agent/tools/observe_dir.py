#!/usr/bin/env python3
import os
import sys
from pathlib import Path

path, dir_out = sys.argv[1:3]
Path(dir_out).write_text(f'{1 if os.path.isdir(path) else 0}\n')
