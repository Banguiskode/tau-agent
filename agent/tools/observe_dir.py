#!/usr/bin/env python3
import os
import sys

print(1 if os.path.isdir(sys.argv[1]) else 0)
