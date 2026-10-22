#!/usr/bin/env python3
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def read_disk(path: Path) -> dict:
    out = path.parent / 'disk_bit.out'
    if out.exists():
        out.unlink()
    spec = (
        f'w:sbf := in file("{path}").\n'
        f'o:sbf := out file("{out}").\n'
        'r o[0] = w[0]\n'
        'q\nquit\n'
    )
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=spec,
        capture_output=True,
        text=True,
        timeout=20,
    )
    blob = result.stdout + result.stderr
    lines = out.read_text().splitlines() if out.exists() else []
    return {
        'lines': lines,
        'failed_open': 'Failed to open file' in blob,
        'bit': int(lines[0]) if lines and lines[0] in {'0', '1'} else None,
    }


@unittest.skipUnless(shutil.which('tau'), 'tau binary required; CI does not execute Tau')
class DiskReadTests(unittest.TestCase):
    def test_tau_does_not_read_the_disk_as_a_bit(self):
        folder = Path(tempfile.mkdtemp())
        text = folder / 'note.txt'
        text.write_text('pas un bit\n')
        empty = folder / 'empty.txt'
        empty.write_text('')
        missing = folder / 'absent'
        directory = folder

        text_read = read_disk(text)
        empty_read = read_disk(empty)
        missing_read = read_disk(missing)
        dir_read = read_disk(directory)

        self.assertIsNone(text_read['bit'])
        self.assertNotIn(text_read['lines'][0], {'0', '1'})
        self.assertIsNone(empty_read['bit'])
        self.assertEqual(empty_read['lines'], [])
        self.assertTrue(missing_read['failed_open'])
        self.assertIsNone(missing_read['bit'])
        self.assertIsNone(dir_read['bit'])
        self.assertEqual(dir_read['lines'], [])
        self.assertFalse(dir_read['failed_open'])
