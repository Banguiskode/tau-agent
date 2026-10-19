#!/usr/bin/env python3
import os
import sys

path = sys.argv[1]
print(1 if os.path.isdir(path) else 0)
