from pathlib import Path
import struct
import sys
import unittest

try:
    import PIL
except ImportError:
    if __name__=='__main__':raise SystemExit(77)
    raise unittest.SkipTest('Pillow is required for face conversion')

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_face_atlas import decode,pack,append_row,image,mark_row,allocate_cell


class FaceAtlasTests(unittest.TestCase):
    def test_column_allocation_keeps_retail_and_previous_costume_cells(self):
        from PIL import Image
        raw=bytes(4)+struct.pack('>HHHHI',384,192,1,0,384*192*4)+bytes([127,11,22,33])*(384*192)
        expanded,packed,first=allocate_cell(pack(raw),Image.new('RGBA',(96,96),(10,20,30,255)))
        self.assertEqual((first['face_x'],first['face_y'],first['face_width']),(384,0,480))
        self.assertEqual(image(expanded,480,192).crop((0,0,384,192)).tobytes(),image(raw,384,192).tobytes())
        with self.assertRaisesRegex(ValueError,'Unregistered artwork'):allocate_cell(packed,Image.new('RGBA',(96,96)))
        second,packed2,info=allocate_cell(packed,Image.new('RGBA',(96,96),(40,50,60,255)),[(384,0)])
        self.assertEqual((info['face_x'],info['face_y'],info['face_width']),(384,96,480))
        self.assertEqual(image(second,480,192).crop((384,0,480,96)).tobytes(),image(expanded,480,192).crop((384,0,480,96)).tobytes())
        third,_,info=allocate_cell(packed2,Image.new('RGBA',(96,96)),[(384,0),(384,96)])
        self.assertEqual(info['face_width'],576)
        self.assertEqual(image(third,576,192).crop((0,0,480,192)).tobytes(),image(second,480,192).tobytes())
        for occupied in [[(0,0)],[(384,0),(384,0)],[(480,0)],[(384,192)],[(True,0)]]:
            with self.subTest(occupied=occupied),self.assertRaises(ValueError):
                allocate_cell(packed,Image.new('RGBA',(1,1)),occupied)
        with self.assertRaises(ValueError):allocate_cell(packed,Image.new('RGBA',(1,1)),None)

    def test_marker_changes_only_selected_row_rgb(self):
        raw=bytes(4)+struct.pack('>HHHHI',384,192,1,0,384*192*4)+bytes([127,11,22,33])*(384*192)
        packed=pack(raw);expanded,result,report=mark_row(packed,1)
        split=16+384*96*4
        self.assertEqual(expanded[:split],raw[:split])
        self.assertEqual(expanded[split::4],raw[split::4])
        self.assertEqual(image(expanded,384,192).getpixel((0,96)),(255,0,255,127))
        self.assertEqual(decode(result)[0],expanded)
        for row,rgb in [(True,(0,0,0)),(-1,(0,0,0)),(2,(0,0,0)),(0,(True,0,0)),(0,(256,0,0))]:
            with self.subTest(row=row,rgb=rgb),self.assertRaises(ValueError):mark_row(packed,row,rgb)

    def test_row_append_preserves_donor_and_rgba_channels(self):
        from PIL import Image
        raw=bytes([0,1,1,1])+struct.pack('>HHHHI',384,96,1,0,384*96*4)+bytes([128,11,22,33])*(384*96)
        packed=pack(raw)
        pose=Image.new('RGBA',(96,96),(5,6,7,123))
        expanded,output,report=append_row(packed,pose)
        self.assertEqual(decode(output),(expanded,384,192))
        self.assertEqual(expanded[16:16+384*96*4],raw[16:])
        preview=image(expanded,384,192)
        self.assertEqual(preview.getpixel((0,0)),(11,22,33,128))
        for column in range(4):self.assertEqual(preview.getpixel((column*96,96)),(5,6,7,123))
        self.assertTrue(report['preserved_donor_pixels'])
        self.assertFalse(report['runtime_routing_validated'])

    def test_reject_header_and_capacity_errors(self):
        from PIL import Image
        for raw in [bytes(16),bytes([11])+bytes(15),
                    bytes(4)+struct.pack('>HHHHI',1,1,2,0,4)+bytes(4)]:
            with self.assertRaises(ValueError):pack(raw)
        with self.assertRaises(ValueError):decode(b'dat\0'+bytes(20))
        raw=bytes(4)+struct.pack('>HHHHI',384,4032,1,0,384*4032*4)+bytes(384*4032*4)
        # No expensive compressor needed to exercise the capacity guard.
        from unittest.mock import patch
        with patch('d2_face_atlas.decode',return_value=(raw,384,4032)),self.assertRaises(ValueError):
            append_row(b'',Image.new('RGBA',(1,1)))


if __name__=='__main__':unittest.main()
