#!/usr/bin/env python3
import os
import sys
from pathlib import Path

path, exists_out, size_out = sys.argv[1:4]
if os.path.isfile(path):
    exists = 1
    size = 1 if os.path.getsize(path) > 0 else 0
else:
    exists = 0
    size = 0
Path(exists_out).write_text(f'{exists}\n')
Path(size_out).write_text(f'{size}\n')
