#!/usr/bin/env python3
import os
import sys

path = sys.argv[1]
print(1 if os.path.isfile(path) and os.path.getsize(path) > 0 else 0)
