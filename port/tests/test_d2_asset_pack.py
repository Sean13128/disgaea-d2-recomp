"""Asset-free regression tests for D2 compression and overlay archive builds."""
import os
import io
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from d2_asset_pack import compress_lzs, rebuild
from d2_character_export import nispack, unlzs


def archive(members):
    header = b'NISPACK\0'+struct.pack('>II',0x01000000,len(members))
    cursor = 16+44*len(members)
    directory = bytearray()
    body = bytearray()
    for name, payload, word in members:
        directory.extend(name.encode().ljust(32,b'\0')+struct.pack('>III',cursor,len(payload),word))
        body.extend(payload)
        cursor += len(payload)
    return header+directory+body


class CompressionTests(unittest.TestCase):
    def test_markers_overlap_and_length_boundaries(self):
        rng = random.Random(42)
        fixtures = [b'',bytes(range(256)),bytes(range(256))*3,
                    bytes([0,1,255])*1024,bytes(rng.randrange(256) for _ in range(4096))]
        fixtures += [b'A'*n for n in (1,3,4,254,255,256,510,511,4096)]
        fixtures += [bytes(range(n))*12 for n in (1,2,17,253,254,255)]
        for raw in fixtures:
            with self.subTest(size=len(raw), prefix=raw[:8]):
                self.assertEqual(unlzs(compress_lzs(raw)),raw)

    def test_references_do_not_depend_on_overlapping_memcpy(self):
        packed=compress_lzs(b'ABCD'*8192+bytes(range(256))*16)
        marker=struct.unpack_from('<I',packed,12)[0]
        cursor=16;references=0
        while cursor<len(packed):
            value=packed[cursor];cursor+=1
            if value==marker:
                encoded=packed[cursor];cursor+=1
                if encoded!=marker:
                    distance=encoded-(encoded>marker)
                    count=packed[cursor];cursor+=1
                    self.assertLessEqual(count,distance)
                    references+=1
        self.assertGreater(references,0)

    def test_repetition_actually_compresses(self):
        raw=b'ABCD'*8192
        self.assertLess(len(compress_lzs(raw)),len(raw)//10)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='d2-pack-test-',dir=os.path.realpath(tempfile.gettempdir()))
        self.root=Path(self.temp.name)
        self.source=self.root/'source.dat'
        self.original=archive([('first.dat',b'one',0x12345678),('second.dat',b'two',0xabcdef01)])
        self.source.write_bytes(self.original)
        self.patch=self.root/'patch.bin'
        self.patch.write_bytes(b'replacement'*300)

    def tearDown(self):
        self.temp.cleanup()

    def test_replacement_addition_alignment_and_unknown_words(self):
        output=self.root/'overlay.dat'
        report=rebuild(self.source,output,{'first.dat':self.patch},{'new.lzs':self.patch})
        self.assertEqual(report['count'],3)
        self.assertEqual(self.source.read_bytes(),self.original)
        with output.open('rb') as f:
            rows=nispack(f,output.stat().st_size)
            self.assertEqual([r['name'] for r in rows],['first.dat','second.dat','new.lzs'])
            self.assertEqual([r['unknown_be32'] for r in rows],[0x12345678,0xabcdef01,0])
            for row, expected in zip(rows,[self.patch.read_bytes(),b'two',self.patch.read_bytes()]):
                self.assertEqual(row['offset']%2048,0)
                f.seek(row['offset'])
                self.assertEqual(f.read(row['size']),expected)

    def test_rejects_overwrite_ambiguous_names_and_bad_source(self):
        existing=self.root/'existing.dat';existing.write_bytes(b'preserve')
        for replacements,additions in [({'absent.dat':self.patch},{}),({}, {'first.dat':self.patch}),
                                      ({'../bad':self.patch},{}),({'first.dat':self.patch},{'first.dat':self.patch})]:
            with self.assertRaises(ValueError):
                rebuild(self.source,self.root/'bad.dat',replacements,additions)
            self.assertFalse((self.root/'bad.dat').exists())
        with self.assertRaises(ValueError):
            rebuild(self.source,existing,{'first.dat':self.patch})
        self.assertEqual(existing.read_bytes(),b'preserve')
        self.source.write_bytes(self.original[:20])
        with self.assertRaises(ValueError):
            rebuild(self.source,self.root/'truncated.dat',{})
        self.assertFalse((self.root/'truncated.dat').exists())

    def test_explicit_new_directory_word_and_invalid_values(self):
        output=self.root/'explicit.dat'
        rebuild(self.source,output,{}, {'new.lzs':self.patch},
                addition_unknown_words={'new.lzs':0x12345678})
        with output.open('rb') as f:
            self.assertEqual(nispack(f,output.stat().st_size)[-1]['unknown_be32'],0x12345678)
        for values in ({'absent.lzs':0},{'new.lzs':-1},{'new.lzs':2**32},{'new.lzs':True}):
            with self.assertRaises(ValueError):
                rebuild(self.source,self.root/'invalid.dat',{}, {'new.lzs':self.patch},
                        addition_unknown_words=values)
            self.assertFalse((self.root/'invalid.dat').exists())

    def test_rejects_source_patch_and_destination_symlinks(self):
        link=self.root/'link';link.symlink_to(self.patch)
        with self.assertRaises(ValueError):
            rebuild(self.source,self.root/'bad.dat',{'first.dat':link})
        target=self.root/'folder';target.mkdir()
        directory_link=self.root/'folder-link';directory_link.symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):
            rebuild(self.source,directory_link/'bad.dat',{})


if __name__=='__main__':
    unittest.main()
