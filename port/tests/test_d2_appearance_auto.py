"""Asset-free checks for the automatic costume pipeline.

Synthetic donors exercise pose templates, pivot placement, complete repaint,
donor-specific cell enlargement and the one-command helper's allocation rules.
"""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

try:
    from PIL import Image
except ImportError:
    print('SKIP: Pillow unavailable')
    raise SystemExit(77)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import d2_anm_cells as cells
from d2_anm import parse_anm, STRIDES, COUNT_INDICES
from d2_asset_pack import compress_lzs
from d2_character_export import unlzs
from d2_rpg_autobuild import build, compose, resolve_pose
from d2_rpg_map import pages_of, page_image, sha
from d2_rpg_template import (SCHEMA, build_template, catalog, mask, merge_common, orient,
                             rectangle_usage)
from test_d2_asset_pack import archive

FORMATS = ('>2H', '>8H', '>6H', '>4H', '>6H', '>9H', '>8h', '>2h', '>10H', '>2H')


def synth(resource, tables, size=(64, 64), art=()):
    """One-block ANM with the given table rows and an indexed page.

    art: (x, y, w, h) boxes filled with palette index 1 (opaque red).
    """
    # Like retail files, the sheet table repeats the page size the renderer scales by.
    tables = dict(tables)
    tables.setdefault('sheet_refs', [(0, 0, size[0], size[1], 2064, 4096)])
    rows = [tables.get(name, []) for name in
            ('tags', 'tracks', 'keys', 'palette_refs', 'sheet_refs', 'rects', 'transforms', 'anchors', 'tints', 'extra')]
    values = [resource]+[len(r) for r in rows]+[0]
    offsets, cursor, body = [], 68, b''
    for stride, fmt, data in zip(STRIDES, FORMATS, rows):
        offsets.append(cursor)
        body += b''.join(struct.pack(fmt, *row) for row in data)
        cursor += stride*len(data)
    length = (cursor+15) & ~15
    block = struct.pack('>I12H10I', length, *values, *offsets)+body+bytes(length-cursor)
    width, height = size
    indices = bytearray(width*height)
    for x, y, w, h in art:
        for row in range(y, y+h):
            indices[row*width+x:row*width+x+w] = bytes([1])*w
    texture = bytes([9, 0, 0, 0])+struct.pack('>HHHHI', width, height, 1, 0, 0)
    palette = bytes(4)+struct.pack('>HHHHI', 256, 1, 1, 0, width*height)
    colors = bytes(4)+bytes([255, 255, 0, 0])+bytes([255, 0, 0, 255])*254
    payload = bytes(indices)+colors
    start = 32+length+32
    return struct.pack('>8I', start-16, len(payload), 1, 1, 1, 0, 0, 0)+block+texture+palette+payload


def sprite_dir(root, sprites):
    """Extraction-shaped folder: {'front/name': (image, pivot or None)}."""
    root.mkdir()
    bundles = {}
    for key, (image, pivot) in sprites.items():
        label, name = key.split('/')
        image.save(root/(label+'_'+name+'.png'))
        entry = dict(name=name, png=label+'_'+name+'.png')
        if pivot:
            entry['pivot'] = dict(x=pivot[0], y=pivot[1])
        bundles.setdefault(label, []).append(entry)
    (root/'manifest.json').write_text(json.dumps(dict(bundles=[dict(label=k, sprites=v) for k, v in bundles.items()])))
    return root


def block_image(size, box, color=(255, 0, 0, 255)):
    image = Image.new('RGBA', size)
    image.paste(color, box)
    return image


class AutoPipelineTests(unittest.TestCase):
    def setUp(self):
        # Resolve the directory: path guards refuse symlinked temp locations.
        self.tmp = tempfile.TemporaryDirectory(prefix='d2-auto-', dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        # Donor: body cell 1 (20x24 at 4,4) and a cloth part cell 2 (8x8 at 40,4),
        # both drawn by animation 6001; cell 3 belongs to a scaled transform.
        self.tables = dict(
            tags=[(0, 0), (6001, 1)],
            tracks=[(0, 0, 0, 0, 0xffff, 0, 0xffff, 0xffff), (0, 0, 0, 0, 0, 3, 0xffff, 0xffff)],
            keys=[(0, 0, 1, 1, 0, 0), (0, 0, 2, 2, 0, 0), (12, 0, 3, 3, 0, 0)],
            rects=[(0, 0, 0, 0, 0, 0, 0, 0, 240), (0, 0, 0, 0, 4, 4, 20, 24, 150),
                   (0, 0, 0, 0, 40, 4, 8, 8, 0), (0, 0, 0, 0, 4, 36, 20, 24, 0)],
            transforms=[(0, 0, 0, 0, 100, 100, 0, 0), (3, -20, 0, 1, 100, 100, 0, 0),
                        (-12, -30, 0, 2, 100, 100, 0, 0), (0, -20, 0, 3, 50, 100, 0, 0)],
            anchors=[(0, 0), (10, 12), (4, 4), (10, 12)])
        # Body art 12x16 inside cell 1 at (4,6); part art fills cell 2; cell 3 art.
        self.donor = synth(30, self.tables, art=[(8, 10, 12, 16), (41, 5, 6, 6), (8, 42, 12, 16)])
        self.common = synth(1, dict(rects=[(0, 0, 0, 0, 0, 0, 0, 0, 240)]), size=(8, 8))
        # Reference pose: same 12x16 art on a 30x30 canvas at (9,7), pivot at canvas centre.
        self.reference = sprite_dir(self.root/'reference', {
            'wait_front/wait01': (block_image((30, 30), (9, 7, 21, 23)), (0.5, 0.5))})

    def template(self):
        result = build_template(self.donor, self.common, self.reference, 30)
        result.update(member='anm00030.lzs', common_member='anm00001.lzs')
        return result

    def test_orientation_moves_pivot_with_the_pixels(self):
        image = Image.new('RGBA', (5, 7))
        image.putpixel((1, 2), (255, 0, 0, 255))
        for flip in (False, True):
            for turns in range(4):
                turned, pivot = orient(image, (1.5, 2.5), flip, turns)
                x, y = int(pivot[0]), int(pivot[1])
                self.assertEqual(turned.getpixel((x, y))[3], 255, (flip, turns))
        with self.assertRaises(ValueError):
            orient(image, (0, 0), 1, 0)

    def test_usage_and_cell_origins_follow_keys(self):
        usage, rects = rectangle_usage(self.donor, 30)
        self.assertEqual(usage[1], dict(layers=[0], animations=[6001]))
        self.assertEqual(len(rects), 4)
        origins = cells.cell_origins(cells.own_tables(self.donor, 30))
        self.assertEqual(origins[1], (3-10, -20-12))
        self.assertEqual(origins[2], (-12-4, -30-4))
        self.assertNotIn(3, origins)  # scaled placement is not a plain cell origin

    def test_template_aligns_reference_and_clears_parts(self):
        t = self.template()
        own = {e['rectangle_index']: e for e in t['entries'] if e['block'] == 'own'}
        self.assertEqual(own[1]['match'], 'exact')
        self.assertEqual(own[1]['pose'], 'wait_front/wait01')
        # Canvas (9,7) art sits at cell (4,6): canvas offset (-5,-1); pivot = offset + centre.
        self.assertEqual(own[1]['canvas_offset'], [-5, -1])
        self.assertEqual(own[1]['pivot'], [10.0, 14.0])
        self.assertEqual(own[2]['match'], 'clear')
        self.assertEqual(t['own_canvas_origin']['wait_front']['origin'], [3-10-5, -20-12-1])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            other = sprite_dir(self.root/'other', {'front/stand': (block_image((30, 30), (2, 2, 6, 28)), None)})
            build_template(self.donor, self.common, other, 30)

    def test_repaint_leaves_no_donor_pixels_and_keeps_metadata(self):
        t = self.template()
        costume = catalog(sprite_dir(self.root/'same', {
            'wait_front/wait01': (block_image((30, 30), (9, 7, 21, 23), (0, 255, 0, 255)), (0.5, 0.5))}))
        donor, images, report, residual, growth = compose(self.donor, t, costume, self.common)
        self.assertEqual(donor, self.donor)  # fits: no metadata edits
        self.assertIsNone(growth)
        page = images[0]
        self.assertEqual(page.getpixel((8, 10)), (0, 255, 0, 255))
        self.assertEqual(page.getpixel((43, 7))[3], 0)   # part cleared
        reds = [p for p in page.crop((4, 4, 24, 28)).get_flattened_data() if p[:3] == (255, 0, 0) and p[3]]
        self.assertEqual(reds, [])

    def test_oversized_costume_enlarges_own_cell_and_hides_part(self):
        t = self.template()
        # Art 26x28 on the same canvas: overflows the 20x24 cell on every side.
        big = block_image((30, 30), (2, 1, 28, 29), (0, 0, 255, 255))
        root = sprite_dir(self.root/'big', {'wait_front/wait01': (big, (0.5, 0.5))})
        donor, images, report, residual, growth = compose(self.donor, t, catalog(root), self.common)
        self.assertNotEqual(donor, self.donor)
        move = growth['enlarged']['1']
        left, top = move['margin']
        x, y, w, h = move['destination']
        # Art spans cell x -3..23, y 0..28; with the 1 px rim it needs 4 px left and
        # right, 1 px on top and 5 px below.
        self.assertEqual((left, top), (4, 1))
        self.assertEqual((w, h), (20+4+4, 24+1+5))
        after = cells.own_tables(donor, 30)
        self.assertEqual(after['rects'][1][4:8], (x, y, w, h))
        self.assertEqual(after['anchors'][1], (10+left, 12+top))
        self.assertEqual(after['keys'][1][2], 0)           # cloth key now draws nothing
        self.assertEqual(after['keys'][0], cells.own_tables(self.donor, 30)['keys'][0])
        self.assertEqual(after['anchors'][3], (10, 12))    # scaled group untouched
        self.assertEqual(growth['hidden_parts'], [2])
        # Same character-space position: new cell origin plus art offset is unchanged.
        origin = cells.cell_origins(after)[1]
        self.assertEqual((origin[0]+left, origin[1]+top), cells.cell_origins(cells.own_tables(self.donor, 30))[1])
        blues = sum(1 for p in images[0].crop((x, y, x+w, y+h)).get_flattened_data() if p == (0, 0, 255, 255))
        self.assertEqual(blues, 26*28)
        row = next(r for r in report if r['rectangle_index'] == 1 and r['block'] == 'own')
        self.assertEqual(row['clipped_pixels'], 0)
        # Every byte outside rectangle 1, pivot 1 and the hidden key is identical.
        meta = parse_anm(self.donor)['blocks'][0]['tables']
        allowed = set(range(meta['rectangle_candidates']['offset']+18+8, meta['rectangle_candidates']['offset']+18+16))
        allowed |= set(range(meta['anchor_candidates']['offset']+4, meta['anchor_candidates']['offset']+8))
        allowed |= set(range(meta['keys']['offset']+12+4, meta['keys']['offset']+12+6))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.donor, donor))))

    def test_atlas_limited_frames_fit_whole_art_at_consistent_sequence_scale(self):
        t = self.template()
        # Lock the body pivot so growth is unavailable, as with shared or
        # attachment-linked native frames. Fit preserves the whole silhouette.
        tables = dict(self.tables)
        tables['transforms'] = list(tables['transforms'])
        tables['transforms'][1] = (3, -20, 0, 1, 50, 100, 0, 0)
        donor = synth(30, tables, art=[(8, 10, 12, 16), (41, 5, 6, 6)])
        t['donor_sha256'] = sha(donor)
        big = block_image((30, 30), (1, 1, 29, 29), (0, 0, 255, 255))
        root = sprite_dir(self.root/'locked-big', {'wait_front/wait01': (big, (0.5, 0.5))})
        after, images, report, _, growth = compose(donor, t, catalog(root), self.common)
        self.assertEqual(after, donor)
        row = next(r for r in report if r['rectangle_index'] == 1 and r['block'] == 'own')
        self.assertEqual(row['clipped_pixels'], 0)
        self.assertLess(row['frame_fit']['scale'], 1)
        self.assertEqual(images[0].getpixel((4, 4))[3], 0)
        self.assertEqual(row['frame_fit']['source_opaque_pixels'], 28*28)

    def test_fitting_shared_numbered_frames_keeps_scale_and_rim(self):
        from d2_rpg_autobuild import fit_overflow
        entries=[]
        for index, width in enumerate((28, 22)):
            image=block_image((32, 32), (1, 1, width+1, 29))
            entries.append(dict(block='common',pose_used='front/walk0'+str(index+1),
                                image=image,offset=(-3,-2),source_pivot=(16,16),
                                destination=[0,0,20,24],row={}))
        fit_overflow(entries)
        self.assertEqual(entries[0]['row']['frame_fit']['scale'],entries[1]['row']['frame_fit']['scale'])
        for e in entries:
            x,y=e['offset'];w,h=e['destination'][2:]
            self.assertGreaterEqual(x,1);self.assertGreaterEqual(y,1)
            self.assertLessEqual(x+e['image'].width,w-1)
            self.assertLessEqual(y+e['image'].height,h-1)

    def test_frames_on_a_foreign_canvas_share_one_placement_correction(self):
        from d2_rpg_autobuild import steady_mismatched
        # Taller canvas, same width: a cape changes the outline every frame,
        # yet the body must not wander sideways.
        entries = [dict(block='own', pose_used='wait_back/wait0%d' % (n+1), flip_x=True, quarter_turns=0,
                        image=Image.new('RGBA', (170, 200)), reference_size=[170, 180], offset=(-31, -37),
                        stand=stand, row={})
                   for n, stand in enumerate(((-3, -11), (7, -10), (13, -10), (9, -10), (12, -10)))]
        other = dict(block='own', pose_used='back/damage', flip_x=True, quarter_turns=0,
                     image=Image.new('RGBA', (90, 60)), reference_size=[80, 60], offset=(4, 5), stand=(6, -2), row={})
        steady_mismatched(entries+[other])
        self.assertEqual({e['offset'] for e in entries}, {(-31, -47)})
        self.assertEqual(entries[0]['row']['canvas_shift'], [0, -10])
        self.assertEqual(other['offset'], (10, 5))
        self.assertNotIn('stand', other)

    def test_growth_without_room_or_on_scaled_groups_is_skipped(self):
        t = self.template()
        own = [dict(e) for e in t['entries']]
        sizes = {0: (64, 64)}
        self.assertIsNone(cells.plan(self.donor, 30, own, {}, [], sizes))
        blocked = cells.plan(self.donor, 30, own, {1: (400, 400, 400, 400)}, [], sizes)
        self.assertEqual(blocked['moves'], {})
        self.assertIn('No free atlas space', blocked['skipped'][-1]['reason'])
        # A need the page can only partly hold is met as far as possible and reported.
        partial = cells.plan(self.donor, 30, own, {1: (40, 40, 40, 40)}, [], sizes)
        self.assertLess(partial['skipped'][-1]['margin_factor'], 1)
        self.assertLess(partial['moves'][1]['margin'][0], 40)
        # Rectangle 3 is drawn through a scaled transform: its pivot may not move.
        own.append(dict(block='own', rectangle_index=3, page=0, destination=[4, 36, 20, 24], match='exact'))
        scaled = cells.plan(self.donor, 30, own, {3: (2, 0, 0, 0)}, [], sizes)
        self.assertEqual(scaled['moves'], {})
        self.assertIn('scaled', scaled['skipped'][0]['reason'])
        # Shared rectangles of other animations are never reused as free space.
        reserved = [(0, 0, 0, 0, 0, 0, 64, 64, 0)]
        full = cells.plan(self.donor, 30, [dict(e) for e in t['entries']], {1: (2, 2, 2, 2)}, reserved, sizes,
                          taller_pages=False)
        self.assertEqual(full['moves'], {})
        # With taller pages the cell goes into new rows below, still clear of the shared area.
        below = cells.plan(self.donor, 30, [dict(e) for e in t['entries']], {1: (2, 2, 2, 2)}, reserved, sizes)
        self.assertEqual(below['page_resize'], {0: [64, 128]})
        self.assertGreaterEqual(below['moves'][1]['destination'][1], 64)

    def test_pinned_pivots_grow_right_and_down_and_groups_may_span_pages(self):
        t = self.template()
        tables = {k: list(v) for k, v in self.tables.items()}
        # Rectangle 3 is now also drawn scaled about rectangle 1's pivot; rectangle 4 lives on a
        # second, narrow page and shares pivot 4 with rectangle 5; rectangle 6 stands alone.
        tables['rects'] += [(1, 0, 0, 0, 0, 0, 10, 12, 0), (0, 0, 0, 0, 40, 20, 8, 8, 0), (0, 0, 0, 0, 50, 40, 8, 8, 0)]
        tables['transforms'] += [(0, -20, 0, 1, 50, 100, 0, 0), (0, 0, 0, 4, 100, 100, 0, 0),
                                 (0, 0, 0, 4, 100, 100, 0, 0), (0, 0, 0, 5, 100, 100, 0, 0)]
        tables['anchors'] += [(4, 4), (4, 4)]
        tables['keys'] += [(24, 0, 3, 4, 0, 0), (0, 0, 4, 5, 0, 0), (0, 0, 5, 6, 0, 0), (0, 0, 6, 7, 0, 0)]
        donor = synth(30, tables, art=[(8, 10, 12, 16)])
        own = [dict(e) for e in t['entries']]+[
            dict(block='own', rectangle_index=3, page=0, destination=[4, 36, 20, 24], match='exact'),
            dict(block='own', rectangle_index=4, page=1, destination=[0, 0, 10, 12], match='exact'),
            dict(block='own', rectangle_index=5, page=0, destination=[40, 20, 8, 8], match='exact'),
            dict(block='own', rectangle_index=6, page=0, destination=[50, 40, 8, 8], match='exact')]
        sizes = {0: (64, 64), 1: (16, 64)}
        # The shared pivot cannot move, but room to the right and below needs no pivot change.
        pinned = cells.plan(donor, 30, own, {1: (2, 0, 3, 2)}, [], sizes)
        self.assertEqual(pinned['moves'][1]['margin'], [0, 0])
        self.assertEqual(pinned['moves'][1]['destination'][2:], [23, 26])
        self.assertEqual(set(pinned['moves']), {1})
        self.assertEqual(pinned['anchor_edits'], {})
        self.assertEqual((pinned['pinned'][0]['rectangles'], pinned['pinned'][0]['still_short']), ([1], [1]))
        left_only = cells.plan(donor, 30, own, {1: (2, 0, 0, 0)}, [], sizes)
        self.assertEqual(left_only['moves'], {})
        self.assertFalse(cells.plan(donor, 30, own, {1: (0, 0, 3, 2)}, [], sizes, symmetric=True)['moves'])
        # One pivot, two pages: both cells gain the same margin.
        both = cells.plan(donor, 30, own, {5: (2, 1, 0, 0)}, [], sizes)
        self.assertEqual(both['anchor_edits'], {4: [2, 1]})
        self.assertEqual((both['moves'][4]['destination'][2:], both['moves'][5]['destination'][2:]), ([12, 13], [10, 9]))
        self.assertEqual(both['skipped'], [])
        # The narrow page cannot hold its cell: that group stays, an independent one still grows.
        narrow = cells.plan(donor, 30, own, {5: (8, 0, 0, 0), 6: (1, 1, 1, 1)}, [], sizes)
        self.assertEqual(set(narrow['moves']), {6})
        self.assertIn('spans several pages', narrow['skipped'][0]['reason'])
        self.assertEqual(narrow['skipped'][0]['rectangles'], [4, 5])

    def test_page_grows_taller_so_enlarged_cells_keep_native_size(self):
        from d2_character_export import anm_pages
        from d2_rpg_palette import encode_images
        t = self.template()
        own = [dict(e) for e in t['entries']]
        sizes = {0: (64, 64)}
        # 20x24 cell needing 40 px above and below cannot fit a 64 px page; the page doubles.
        tall = cells.plan(self.donor, 30, own, {1: (2, 40, 2, 40)}, [], sizes)
        self.assertEqual(tall['page_resize'], {0: [64, 128]})
        self.assertEqual(tall['moves'][1]['margin'], [2, 40])
        x, y, w, h = tall['moves'][1]['destination']
        self.assertEqual((w, h), (24, 104))
        self.assertTrue(0 <= x and x+w <= 64 and 0 <= y and y+h <= 128)
        self.assertFalse(any('margin_factor' in s for s in tall['skipped']))
        # Without taller pages the old behaviour remains: a smaller margin, reported.
        limited = cells.plan(self.donor, 30, own, {1: (2, 40, 2, 40)}, [], sizes, taller_pages=False)
        self.assertEqual(limited['page_resize'], {})
        self.assertLess(limited['skipped'][-1]['margin_factor'], 1)
        grown = cells.apply(self.donor, 30, tall)
        self.assertEqual(len(grown), len(self.donor)+64*64)
        before, after = anm_pages(self.donor, include_rgba=False)[0], anm_pages(grown, include_rgba=False)[0]
        self.assertEqual((after['width'], after['height']), (64, 128))
        self.assertEqual(bytes(after['indices'][:64*64]), bytes(before['indices']))
        self.assertEqual(bytes(after['indices'][64*64:]), bytes(64*64))
        self.assertEqual(after['colors'], before['colors'])
        self.assertEqual(cells.own_tables(grown, 30)['rects'][1][4:8], (x, y, w, h))
        self.assertEqual(cells.own_tables(grown, 30)['transforms'], cells.own_tables(self.donor, 30)['transforms'])
        # The renderer scales texture coordinates by the sheet table's size, so it must follow.
        sheet = parse_anm(grown)['blocks'][0]['tables']['sheet_refs']
        self.assertEqual(struct.unpack_from('>6H', grown, sheet['offset']), (0, 0, 64, 128, 2064, 4096))
        stale = bytearray(self.donor)
        struct.pack_into('>H', stale, parse_anm(self.donor)['blocks'][0]['tables']['sheet_refs']['offset']+6, 32)
        with self.assertRaisesRegex(ValueError, 'Sheet table size'):
            cells.resize_pages(bytes(stale), {0: 128})
        for bad in ({0: 100}, {0: 32}, {0: 4096}, {1: 128}, {0: '128'}):
            with self.assertRaises(ValueError, msg=str(bad)):
                cells.resize_pages(self.donor, bad)
        self.assertEqual(cells.resize_pages(self.donor, {}), self.donor)
        # End to end: a costume frame taller than the page is painted whole, at native scale.
        giant = block_image((30, 100), (9, 4, 21, 96), (0, 0, 255, 255))
        root = sprite_dir(self.root/'giant', {'wait_front/wait01': (giant, (0.5, 0.5))})
        donor, images, report, residual, growth = compose(self.donor, t, catalog(root), self.common)
        self.assertEqual(growth['taller_pages'], {'0': [64, 128]})
        self.assertEqual(images[0].size, (64, 128))
        row = next(r for r in report if r['rectangle_index'] == 1 and r['block'] == 'own')
        self.assertEqual((row['clipped_pixels'], row.get('frame_fit')), (0, None))
        cx, cy, cw, ch = growth['enlarged']['1']['destination']
        blues = sum(1 for p in images[0].crop((cx, cy, cx+cw, cy+ch)).get_flattened_data() if p == (0, 0, 255, 255))
        self.assertEqual(blues, 12*92)
        expanded, packed, _ = encode_images(donor, images, 1)
        page = pages_of(expanded)[0]
        self.assertEqual((page['width'], page['height']), (64, 128))
        self.assertEqual(parse_anm(expanded)['blocks'][0]['resource_id'], 30)

    def test_build_writes_checked_outputs_from_an_archive(self):
        t = self.template()
        template_path = self.root/'template.json'
        template_path.write_text(json.dumps(t))
        source = self.root/'ANM_HI.dat'
        source.write_bytes(archive([('anm00030.lzs', compress_lzs(self.donor), 0),
                                    ('anm00001.lzs', compress_lzs(self.common), 0)]))
        before = source.read_bytes()
        costume = sprite_dir(self.root/'costume', {
            'wait_front/wait01': (block_image((30, 30), (9, 7, 21, 23), (0, 255, 0, 255)), (0.5, 0.5))})
        summary = build(source, template_path, costume, self.root/'out')
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(summary['painted'], 2)   # both cells holding the reference pose
        self.assertEqual(summary['donor_pixels_inside_templated_rectangles'], 0)
        expanded = (self.root/'out/expanded.bin').read_bytes()
        self.assertEqual(unlzs((self.root/'out/anm00030.lzs').read_bytes()), expanded)
        self.assertEqual(sha(expanded), summary['encoding']['output_sha256'])
        page = page_image(pages_of(expanded)[0])
        self.assertEqual(page.getpixel((8, 10))[:3], (0, 255, 0))
        self.assertTrue((self.root/'out/review.png').is_file())
        with self.assertRaisesRegex(ValueError, 'must be new'):
            build(source, template_path, costume, self.root/'out')
        t['donor_sha256'] = '0'*64
        template_path.write_text(json.dumps(t))
        with self.assertRaisesRegex(ValueError, 'different donor'):
            build(source, template_path, costume, self.root/'out2')

    def test_missing_poses_use_documented_substitutes(self):
        solid = dict(image=block_image((4, 4), (0, 0, 4, 4)))
        empty = dict(image=Image.new('RGBA', (4, 4)))
        sprites = {'front/attack_sword03': solid, 'front/stand': solid, 'front/dash_hand': empty}
        self.assertEqual(resolve_pose('front/stand', sprites), ('front/stand', None))
        self.assertEqual(resolve_pose('front/attack_sword02', sprites)[0], 'front/attack_sword03')
        self.assertEqual(resolve_pose('front/kabutowari', sprites)[0], 'front/stand')
        self.assertIsNone(resolve_pose('front/dash_hand', sprites)[0])      # transparent part -> clear
        self.assertIsNone(resolve_pose('back/launch_hand01', sprites)[0])   # absent part -> clear
        self.assertIsNone(resolve_pose('back/walk01', sprites)[0])          # no back art at all

    def test_common_votes_prefer_agreement_over_one_strong_guess(self):
        def donor_template(body, pose, iou, match='fallback'):
            return dict(schema=SCHEMA, mode='pose-template', body_id=body, common_resource=1, common_sha256='c',
                        entries=[dict(block='common', rectangle_index=5, destination=[0, 0, 8, 8], layers=[1],
                                      animation_count=2, match=match, pose=pose, flip_x=False, quarter_turns=0,
                                      pivot=[4, 4], iou=iou),
                                 dict(block='own', rectangle_index=1, destination=[0, 0, 8, 8], layers=[0],
                                      animation_count=1, match='clear')])
        merged = merge_common([donor_template(10, 'front/a', 0.80), donor_template(30, 'front/a', 0.82),
                               donor_template(50, 'front/b', 0.90)])
        entry = merged['entries'][0]
        self.assertEqual((entry['pose'], entry['support'], entry['match']), ('front/a', 2, 'fallback'))
        self.assertEqual(merged['disagreements']['5'][1]['bodies'], [50])
        self.assertEqual(len(merged['entries']), 1)   # donor-specific rectangles never merge
        with self.assertRaises(ValueError):
            merge_common([donor_template(10, 'front/a', 0.8), dict(schema=1, mode='pose-template')])


    def test_idle_body_with_separately_keyed_piece_matches_whole_figure(self):
        from d2_rpg_template import idle_composites
        # Idle body (cell 1) and a detached piece (cell 2) run on parallel tracks;
        # the RPG idle frame shows both. Cell 3 is an ordinary action frame.
        tables = dict(self.tables,
                      tags=[(0, 0), (6001, 1), (100, 3)],
                      tracks=[(0, 0, 0, 0, 0xffff, 0, 0xffff, 0xffff), (0, 0, 0, 0, 0, 1, 0xffff, 0xffff),
                              (0, 0, 0, 0, 1, 1, 0xffff, 0xffff), (0, 0, 0, 0, 2, 1, 0xffff, 0xffff)],
                      keys=[(0, 0, 1, 1, 0, 0), (0, 0, 2, 2, 0, 0), (0, 0, 3, 1, 0, 0)])
        donor = synth(30, tables, art=[(8, 10, 12, 16), (41, 5, 6, 6), (8, 38, 12, 20)])
        whole = Image.new('RGBA', (40, 40))
        whole.paste((255, 0, 0, 255), (19, 17, 31, 33))
        whole.paste((255, 0, 0, 255), (7, 10, 13, 16))
        reference = sprite_dir(self.root/'whole', {
            'wait_front/wait01': (whole, (0.5, 0.5)),
            'front/stand': (block_image((30, 30), (9, 5, 21, 25)), (0.5, 0.5))})
        pictures = idle_composites(donor, 30)
        self.assertEqual(sorted(pictures), [(6001, 1), (6001, 2)])
        self.assertEqual((pictures[(6001, 1)]['origin'], pictures[(6001, 1)]['cell'], pictures[(6001, 1)]['pieces']),
                         ((-16, -34), (-7, -32), 2))
        self.assertEqual(pictures[(6001, 1)]['image'].size, (29, 26))
        template = build_template(donor, self.common, reference, 30)
        own = {e['rectangle_index']: e for e in template['entries'] if e['block'] == 'own'}
        body = own[1]
        self.assertEqual((body['match'], body['pose'], body['flip_x'], body['iou'], body['composite_pieces']),
                         ('exact', 'wait_front/wait01', False, 1.0, 2))
        # Canvas position relative to the body cell: the frame's body lands on the donor body.
        self.assertEqual(body['canvas_offset'], [-15, -11])
        self.assertEqual(body['pivot'], [5.0, 9.0])
        self.assertEqual(own[2]['match'], 'clear')
        self.assertEqual((own[3]['match'], own[3]['pose']), ('exact', 'front/stand'))
        # The costume's whole idle frame is painted into an enlarged body cell; the piece is hidden.
        grown, images, report, _, growth = compose(donor, dict(template, member='anm00030.lzs',
                                                              common_member='anm00001.lzs'), catalog(reference),
                                                 self.common)
        self.assertIn(1, {int(k) for k in growth['enlarged']})
        self.assertEqual(growth['hidden_parts'], [2])


class OneCommandHelperTests(unittest.TestCase):
    def test_new_costume_gets_the_next_free_choose_color_slot(self):
        from d2_appearance_add import assign_color_slot
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as tmp:
            stage = Path(tmp)/'stage.json'

            def costume(cls, name, resource):
                return dict(class_id=cls, selector=1, new_resource=resource, visual_class_id=resource,
                            selection_mode='renderer-only', costume_id=name)
            costumes = [costume(10, 'santa', 900), costume(10, 'thunder', 901), costume(320, 'future', 902)]
            data = dict(mode='isolated-runtime-experiment', appearances=[costumes[0], costumes[2]], costumes=costumes)
            stage.write_text(json.dumps(data))
            before = stage.read_bytes()
            # A profile that does not use Choose Color is left exactly as it was.
            self.assertEqual(assign_color_slot(stage, 10, 'thunder'), (None, None))
            self.assertEqual(stage.read_bytes(), before)
            stage.write_text(json.dumps(dict(data, color_slots=[dict(class_id=10, color=1, costume_id='santa')])))
            self.assertEqual(assign_color_slot(stage, 10, 'thunder'), (2, None))
            slots = json.loads(stage.read_text())['color_slots']
            self.assertEqual([(s['class_id'], s['color'], s['costume_id']) for s in slots],
                             [(10, 1, 'santa'), (10, 2, 'thunder'), (320, 1, 'future')])
            # A fifth costume cannot be assigned: reported, nothing written.
            many = costumes+[costume(10, 'extra-%d' % i, 910+i) for i in range(3)]
            stage.write_text(json.dumps(dict(data, costumes=many, color_slots=slots)))
            before = stage.read_bytes()
            slot, note = assign_color_slot(stage, 10, 'extra-2')
            self.assertIsNone(slot)
            self.assertIn('more than four', note)
            self.assertEqual(stage.read_bytes(), before)

    def test_free_ids_skip_classes_files_and_registered_costumes(self):
        from d2_appearance_add import free_resource
        facts = dict(classes={900, 960}, anm_names={'anm00901.lzs', 'anm00903.dat'},
                     inventory=[dict(new_resource=902, visual_class_id=902, illustration_resource=10900)])
        self.assertEqual(free_resource(facts, 900, 999), 904)
        self.assertEqual(free_resource(facts, 10900, 10999), 10901)
        with self.assertRaises(SystemExit):
            free_resource(dict(classes=set(range(900, 1000)), anm_names=set(), inventory=[]), 900, 999)

    def test_add_conveniences_resolve_name_id_and_output(self):
        import argparse
        from d2_appearance_add import REPO, class_by_name, resolve_add, slug
        self.assertEqual(class_by_name('etna'), 30)
        self.assertEqual(class_by_name('Pure Flonne'), 60)
        self.assertEqual(class_by_name('pure-flonne'), 60)
        with self.assertRaises(SystemExit):
            class_by_name('Prinny')
        self.assertEqual(slug("  Dark Santa: Laharl!  "), 'dark-santa-laharl')
        args = resolve_add(argparse.Namespace(class_id=None, character='Laharl', costume_id=None,
                                              display_name='Dark Santa Laharl', output=None))
        self.assertEqual((args.class_id, args.costume_id), (10, 'dark-santa-laharl'))
        self.assertEqual(args.output.parent, REPO/'work/appearance-profiles')
        self.assertTrue(args.output.name.endswith('-dark-santa-laharl'))
        kept = resolve_add(argparse.Namespace(class_id=30, character=None, costume_id='x1', display_name=None,
                                              output=Path('/somewhere/new')))
        self.assertEqual((kept.class_id, kept.costume_id, kept.output), (30, 'x1', Path('/somewhere/new')))
        for bad in (dict(class_id=30, character='Etna'), dict(class_id=None, character=None),
                    dict(class_id=30, character=None, costume_id=None, display_name=None)):
            base = dict(costume_id='x', display_name='X', output=Path('/o'))
            base.update(bad)
            with self.assertRaises(SystemExit):
                resolve_add(argparse.Namespace(**base))

    def test_head_crop_is_a_square_at_the_top_of_the_art(self):
        from d2_appearance_add import head_crop
        image = Image.new('RGBA', (120, 192))
        image.paste((255, 0, 0, 255), (30, 20, 90, 180))     # body
        image.paste((255, 0, 0, 255), (40, 20, 110, 60))     # lopsided hair
        x0, y0, x1, y1 = head_crop(dict(image=image))
        self.assertEqual(x1-x0, y1-y0)
        self.assertTrue(64 <= x1-x0 <= 96)
        self.assertTrue(0 <= x0 and x1 <= 120 and y0 <= 20 < y1)
        self.assertTrue(x0 < 60 < x1)


if __name__ == '__main__':
    unittest.main()
