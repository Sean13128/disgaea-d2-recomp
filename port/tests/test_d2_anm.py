"""Asset-free bounds tests for empirical ANM resource table inspection."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_anm import parse_anm, STRIDES, COUNT_INDICES
from d2_character_export import anm_pages


def fixture():
    values=[30,1,1,1,1,1,1,1,1,1,0,0]
    offsets=[];cursor=68
    for stride,index in zip(STRIDES,COUNT_INDICES):
        offsets.append(cursor);cursor+=stride*values[index]
    length=(cursor+15)&~15
    block=bytearray(struct.pack('>I12H10I',length,*values,*offsets)+bytes(length-68))
    # Zero rectangle and tables remain geometry-only, not a playable fixture.
    texture=bytes([9,0,0,0])+struct.pack('>HHHHI',2,2,1,0,0)
    palette=bytes(4)+struct.pack('>HHHHI',256,1,1,0,4)
    payload=bytes(4)+bytes([255,255,0,0])*256
    payload_start=32+length+32
    return struct.pack('>8I',payload_start-16,len(payload),1,1,1,0,0,0)+block+texture+palette+payload


class MetadataTests(unittest.TestCase):
    def test_shared_container_palette_count_and_bounded_selection(self):
        raw=fixture();payload_start=struct.unpack_from('>I',raw)[0]+16
        table=payload_start-32;block=raw[32:table]
        texture=raw[table:table+16];palette=raw[table+16:payload_start]
        payload=raw[payload_start:];textures=60;palettes=600
        start=32+len(block)+(textures+palettes)*16
        shared=struct.pack('>8I',start-16,len(payload),textures,palettes,1,0,0,0)+block+texture*textures+palette*palettes+payload
        with self.assertRaisesRegex(ValueError,'page-pair limit'):
            anm_pages(shared,include_rgba=False)
        pages=anm_pages(shared,include_rgba=False,palette_indices=[599])
        self.assertEqual(len(pages),60)
        self.assertEqual({p['palette'] for p in pages},{599})
        meta=parse_anm(shared)
        self.assertEqual(meta['page_pairs'],36000)
        self.assertEqual(meta['inspected_page_pairs'],60)
        for selection in ([],[True],[600],[-1],[0,0]):
            with self.subTest(selection=selection),self.assertRaises(ValueError):
                anm_pages(shared,False,selection)
        broken=bytearray(shared)
        broken[32+len(block)+textures*16+599*16]=255
        with self.assertRaises(NotImplementedError):
            anm_pages(broken,False,[0])

    def test_geometry_resource_id_and_exact_end(self):
        result=parse_anm(fixture())
        self.assertEqual(result['blocks'][0]['resource_id'],30)
        self.assertEqual(result['page_pairs'],1)
        self.assertEqual(result['blocks'][0]['tables']['rectangle_candidates']['count'],1)

    def test_rejects_header_count_offset_and_payload_corruption(self):
        raw=fixture()
        changes=[(16,'>I',2),(32,'>I',0xffffffff),(32+28,'>I',0),
                 (32+28+5*4,'>I',0xffffff),(32+4+6*2,'>H',0xffff)]
        for off,fmt,value in changes:
            with self.subTest(offset=off):
                data=bytearray(raw);struct.pack_into(fmt,data,off,value)
                with self.assertRaises(ValueError):parse_anm(data)
        for data in (b'',raw[:60],raw[:-1],raw+b'\0'):
            with self.assertRaises(ValueError):parse_anm(data)


if __name__=='__main__':
    unittest.main()
