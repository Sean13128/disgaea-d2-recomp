"""Asset-free selector/resource authoring and filesystem isolation checks."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_stage import rebind_anm, patch_character_table, patch_save_selector, clone_tree, append_visual_alias, prepare_save, prepare_character_table
from d2_anm import parse_anm
from test_d2_anm import fixture


class AppearanceStageTests(unittest.TestCase):
    def test_renderer_only_table_retains_existing_native_alternate(self):
        raw=bytearray(struct.pack('>HH',1,0)+bytes(676))
        struct.pack_into('>H',raw,4+0x194,410)
        struct.pack_into('>2H',raw,4+0x1bc,410,411)
        output,report=prepare_character_table(raw,410,902,True)
        self.assertEqual(output,bytes(raw))
        self.assertEqual(report['preserved_body_ids'],[410,411])
        with self.assertRaises(ValueError):prepare_character_table(raw,410,902,False)
        with self.assertRaises(ValueError):prepare_character_table(raw,30,902,True)
    def test_renderer_only_save_is_byte_identical(self):
        raw=bytearray(1498152)
        struct.pack_into('>H',raw,0x1507ec,1)
        struct.pack_into('>H',raw,0x598+0x1158,30)
        struct.pack_into('>2H',raw,0x598+0x11d8,30,31)
        for selector in (0,1):
            raw[0x598+0x117a]=selector
            result,report=prepare_save(bytes(raw),30,30000,renderer_only=True)
            self.assertEqual(result,bytes(raw))
            self.assertEqual(report['changed_bytes'],0)
            self.assertEqual(report['old_selector'],report['new_selector'])
    def test_visual_alias_preserves_donor_and_changes_only_visual_fields(self):
        record=bytearray((i%256 for i in range(676)))
        struct.pack_into('>H',record,0x194,30)
        raw=struct.pack('>HH',1,0)+record
        output,report=append_visual_alias(raw,30,30000)
        self.assertEqual(struct.unpack_from('>H',output)[0],2)
        self.assertEqual(output[2:len(raw)],raw[2:])
        alias=output[len(raw):]
        allowed={i for offset in (0x194,0x196,0x1bc,0x1be) for i in (offset,offset+1)}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(record,alias))))
        self.assertEqual(struct.unpack_from('>2H',alias,0x194),(30000,30000))
        self.assertEqual(struct.unpack_from('>2H',alias,0x1bc),(30000,0))
        self.assertEqual(report['row'],1)
        for resource in (30,0,-1,32768,True):
            with self.assertRaises(ValueError):append_visual_alias(raw,30,resource)
        with self.assertRaises(ValueError):append_visual_alias(raw,31,30000)
        with self.assertRaises(ValueError):append_visual_alias(output,30,30000)

    def test_rebind_changes_only_internal_id_and_rejects_wrong_donor(self):
        raw=fixture()
        output,report=rebind_anm(raw,30,30000)
        offset=report['offset']
        self.assertEqual(output[:offset],raw[:offset])
        self.assertEqual(output[offset+2:],raw[offset+2:])
        self.assertEqual(parse_anm(output)['blocks'][0]['resource_id'],30000)
        for old,new in [(31,30000),(30,30),(30,-1),(30,32768)]:
            with self.assertRaises(ValueError):rebind_anm(raw,old,new)

    def test_table_second_selector_preserves_primary_and_class(self):
        raw=bytearray(struct.pack('>HH',1,0)+bytes(676))
        struct.pack_into('>H',raw,4+0x194,30)
        struct.pack_into('>H',raw,4+0x1bc,30)
        output,report=patch_character_table(raw,30,30000)
        offset=report['offset']
        self.assertEqual(output[:offset],raw[:offset])
        self.assertEqual(output[offset+2:],raw[offset+2:])
        self.assertEqual(struct.unpack_from('>H',output,4+0x194)[0],30)
        self.assertEqual(struct.unpack_from('>2H',output,4+0x1bc),(30,30000))
        with self.assertRaises(ValueError):patch_character_table(output,30,30001)
        with self.assertRaises(ValueError):patch_character_table(raw,31,30000)

    def test_save_changes_one_selector_byte_and_requires_unique_unit(self):
        raw=bytearray(1498152)
        struct.pack_into('>H',raw,0x1507ec,1)
        struct.pack_into('>H',raw,0x598+0x1158,30)
        output,report=patch_save_selector(raw,30)
        self.assertEqual(sum(a!=b for a,b in zip(raw,output)),1)
        self.assertEqual(report['offset'],0x598+0x117a)
        struct.pack_into('>2H',raw,0x598+0x11d8,30,31)
        output,report=patch_save_selector(raw,30,cached_body=30000)
        self.assertEqual(sum(a!=b for a,b in zip(raw,output)),3)
        self.assertEqual(struct.unpack_from('>2H',output,0x598+0x11d8),(30000,31))
        self.assertEqual(report['changed_bytes'],3)
        for body in (-1,0,32768,True):
            with self.assertRaises(ValueError):patch_save_selector(raw,30,cached_body=body)
        struct.pack_into('>H',raw,0x1507ec,2)
        struct.pack_into('>H',raw,0x598+0x1a60+0x1158,30)
        with self.assertRaises(ValueError):patch_save_selector(raw,30)
        with self.assertRaises(ValueError):patch_save_selector(raw[:-1],30)

    def test_cloned_tree_has_independent_files_and_refuses_symlinks(self):
        with tempfile.TemporaryDirectory(prefix='d2-stage-test-') as temp:
            root=Path(temp);source=root/'source';source.mkdir()
            original=source/'data';original.write_bytes(b'original')
            clone_tree(source,root/'copy')
            (root/'copy/data').write_bytes(b'changed')
            self.assertEqual(original.read_bytes(),b'original')
            self.assertNotEqual(original.stat().st_ino,(root/'copy/data').stat().st_ino)
            (source/'link').symlink_to(original)
            with self.assertRaises(ValueError):clone_tree(source,root/'unsafe')
            self.assertFalse((root/'unsafe').exists())


if __name__=='__main__':
    unittest.main()
