"""Exact guest decoder/copy regression for native-compatible compression."""
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_asset_pack import compress_lzs
from d2_lzs_probe import probe


class NativeLzsTests(unittest.TestCase):
    def test_guest_copy_rejects_overlap_assumption_and_accepts_new_compression(self):
        if not shutil.which('clang++'):self.skipTest('clang++ unavailable')
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='d2-native-lzs-') as tmp:
            p=Path(tmp);expected=p/'expected';packed=p/'packed'
            raw=b'abcdefgh'+b'h'*24;expected.write_bytes(raw)
            tokens=b'abcdefgh'+bytes([255,1,24])
            packed.write_bytes(b'dat\0'+struct.pack('<III',len(raw),len(tokens)+12,255)+tokens)
            self.assertFalse(probe(repo,packed,expected,p)['matches'])
            expected.write_bytes(raw+bytes(range(256))*16+b'ABCD'*1024)
            packed.write_bytes(compress_lzs(expected.read_bytes()))
            self.assertTrue(probe(repo,packed,expected,p)['matches'])


if __name__=='__main__':unittest.main()
