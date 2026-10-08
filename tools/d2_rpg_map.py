#!/usr/bin/env python3
"""Map named RPG sprites onto D2 atlas rectangles; build offline diagnostics.

Requires Pillow. Suggestions are visual candidates, not decoded D2 actions.
The builder preserves metadata and palettes, reports quantization error, and
never installs files. Explicit placements are retained in a reusable manifest.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

from d2_anm import parse_anm
from d2_asset_pack import compress_lzs, validate_name
from d2_character_export import anm_pages, indexed_png, nispack, unlzs, _no_symlinks

MAX_BYTES = 64 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = _no_symlinks(Path(path).absolute())
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Input exceeds 64 MiB')
    return path.read_bytes()


def archive_member(path, name):
    path = _no_symlinks(Path(path).absolute())
    with path.open('rb') as f:
        matches = [r for r in nispack(f, path.stat().st_size) if r['name'] == name]
        if len(matches) != 1 or matches[0]['size'] > MAX_BYTES:
            raise ValueError('Missing, ambiguous or oversized ANM member')
        f.seek(matches[0]['offset'])
        packed = f.read(matches[0]['size'])
    return unlzs(packed)


def rgba(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.width > 4096 or image.height > 4096:
            raise ValueError('Image exceeds 4096 pixels per side')
        return image.convert('RGBA')


def pages_of(raw, palette=0):
    pages = {p['texture']: p for p in anm_pages(raw, include_rgba=False)
             if p['palette'] == palette}
    if not pages or any('indices' not in p for p in pages.values()):
        raise ValueError('Only decoded indexed ANM textures are supported')
    return pages


def page_image(page):
    return rgba(indexed_png(page['width'], page['height'], page['indices'], page['colors']))


def box(image, threshold=64):
    return image.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def normalized(image):
    bounds = box(image)
    canvas = Image.new('RGBA', (64, 96))
    if bounds:
        crop = image.crop(bounds)
        crop.thumbnail(canvas.size, Image.Resampling.NEAREST)
        canvas.alpha_composite(crop, ((64-crop.width)//2, 96-crop.height))
    flat = Image.new('RGBA', canvas.size, (0, 0, 0, 255))
    flat.alpha_composite(canvas)
    return flat


def sprite_catalog(root):
    root = _no_symlinks(Path(root).absolute())
    manifest = json.loads(read(root/'manifest.json'))
    result = {}
    for bundle in manifest['bundles']:
        if bundle['label'] not in ('front', 'back', 'wait_front', 'wait_back'):
            continue
        for sprite in bundle['sprites']:
            if not sprite.get('png'):
                continue
            key = bundle['label']+'/'+sprite['name']
            if key in result:
                raise ValueError('Ambiguous named sprite: '+key)
            relative = Path(sprite['png'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe sprite path')
            path = root/relative
            data = read(path)
            result[key] = dict(path=str(path), sha256=sha(data), image=rgba(data))
    return result


def rectangles(common, resource_id):
    blocks = [b for b in parse_anm(common)['blocks'] if b['resource_id'] == resource_id]
    if len(blocks) != 1:
        raise ValueError('Missing or ambiguous rectangle resource')
    return {r['index']: r for r in blocks[0]['tables']['rectangle_candidates']['records']}


def orient(image, flip_x, quarter_turns=0):
    if type(flip_x) is not bool or type(quarter_turns) is not int or quarter_turns not in range(4):
        raise ValueError('Orientation requires boolean flip and quarter turns0..3')
    if flip_x:image=ImageOps.mirror(image)
    if quarter_turns:
        image=image.transpose([None,Image.Transpose.ROTATE_90,Image.Transpose.ROTATE_180,
                               Image.Transpose.ROTATE_270][quarter_turns])
    return image


def suggest(donor, common, reference, appearance, resource_id=1, indices=None, quarter_turns=(0,)):
    pages = pages_of(donor)
    images = {i: page_image(p) for i, p in pages.items()}
    refs = sprite_catalog(reference)
    targets = sprite_catalog(appearance)
    if not quarter_turns or any(type(q) is not int or q not in range(4) for q in quarter_turns):
        raise ValueError('Requested quarter turns must be0..3')
    candidates = [(key, flip, turn, normalized(orient(s['image'],flip,turn)))
                  for key, s in refs.items() for flip in (False, True) for turn in quarter_turns]
    rects = rectangles(common, resource_id)
    if indices is not None and set(indices)-set(rects):
        raise ValueError('Unknown requested rectangle index')
    entries = []
    skipped = []
    for index, r in rects.items():
        if indices is not None and index not in indices:
            continue
        x, y, w, h = r['x'], r['y'], r['width'], r['height']
        page = images.get(r['page_candidate'])
        if page is None or min(w, h) <= 0 or x+w > page.width or y+h > page.height:
            skipped.append(dict(index=index, reason='Page or crop outside donor; shared binding unresolved'))
            continue
        crop = page.crop((x, y, x+w, y+h))
        bounds = box(crop)
        if not bounds:
            skipped.append(dict(index=index, reason='Empty crop'))
            continue
        norm = normalized(crop)
        scores = sorted((sum(ImageStat.Stat(ImageChops.difference(norm, image)).mean)/4,
                         key, flip, turn) for key, flip, turn, image in candidates)
        score, key, flip, turn = scores[0]
        if key not in targets:
            skipped.append(dict(index=index, reason='Appearance lacks matched pose', pose=key))
            continue
        source = targets[key]
        source_box = box(source['image'])
        operation='replace'
        if not source_box and source['image'].getchannel('A').getextrema()[1]!=0:
            skipped.append(dict(index=index, reason='Appearance pose below alpha threshold', pose=key))
            continue
        # Explicit diagnostic placement: retain the donor's opaque bottom and
        # center, fit source bounds proportionally. Native pivots remain unknown.
        if source_box:
            sw, sh = source_box[2]-source_box[0], source_box[3]-source_box[1]
            if turn%2:sw,sh=sh,sw
            scale = min((bounds[2]-bounds[0])/sw, (bounds[3]-bounds[1])/sh)
            dw, dh = max(1, round(sw*scale)), max(1, round(sh*scale))
            placement = [x+(bounds[0]+bounds[2]-dw)//2, y+bounds[3]-dh, dw, dh]
        else:
            # Some part sprites are fully transparent in the source.
            # Propose an explicit clear; selection and native clip review are
            # still required rather than treating it as a missing whole pose.
            operation='clear'
            source_box=[0,0,source['image'].width,source['image'].height]
            placement=[x,y,w,h]
        entries.append(dict(rectangle_index=index, page=r['page_candidate'],
                            destination=[x, y, w, h], pose=key, source=source['path'],
                            source_sha256=source['sha256'], source_crop=list(source_box),
                            flip_x=flip, quarter_turns=turn, placement=placement, visual_score=score,operation=operation,
                            second_candidate=list(scores[1]), selected=False))
    return dict(schema=1, mode='texture-diagnostic', donor_sha256=sha(donor),
                common_sha256=sha(common), rectangle_resource=resource_id, palette=0,
                placement_policy='Opaque bounds fit; donor bottom/center retained; native pivots unvalidated',
                entries=entries, skipped=skipped,
                limitations=['Visual suggestions require selection in the manifest.',
                             'No action timing, attachment, shared binding or gameplay validation.',
                             'Donor palettes preserved; other palette variants need review.'])


def validate_box(value, width, height, label):
    if (not isinstance(value, list) or len(value) != 4 or
            any(type(v) is not int for v in value)):
        raise ValueError('Invalid '+label)
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
        raise ValueError('Out of bounds '+label)
    return x, y, w, h


def quantize(image, colors):
    """Map RGBA to donor colors with explicit transparency and alpha weighting."""
    transparent = [i for i, c in enumerate(colors) if c[3] == 0]
    opaque = [i for i, c in enumerate(colors) if c[3] != 0]
    if not transparent or not opaque:
        raise ValueError('Donor palette must support transparent and visible pixels')
    cache = {}
    indices = bytearray()
    error = 0
    visible = 0
    for pixel in struct.iter_unpack('4B', image.tobytes()):
        if pixel not in cache:
            if pixel[3] < 64:
                cache[pixel] = transparent[0]
            else:
                cache[pixel] = min(opaque, key=lambda i: sum((colors[i][k]-pixel[k])**2
                                                            for k in range(3)) +
                                  3*(colors[i][3]-pixel[3])**2)
        index = cache[pixel]
        indices.append(index)
        if pixel[3] >= 64:
            error += sum((colors[index][k]-pixel[k])**2 for k in range(3))/3
            visible += 1
    return bytes(indices), (error/max(1, visible))**0.5


def render_sprite(e, page):
    """Validate and place a source sprite before any palette conversion."""
    x, y, w, h = validate_box(e['destination'], page['width'], page['height'], 'destination')
    source = read(e['source'])
    if sha(source) != e['source_sha256']:
        raise ValueError('Sprite source hash mismatch')
    image = rgba(source)
    operation=e.get('operation','replace')
    if operation not in ('replace','clear'):
        raise ValueError('Unknown mapping operation')
    if operation=='clear' and image.getchannel('A').getextrema()[1]!=0:
        raise ValueError('Clear requires a fully transparent source sprite')
    if operation=='replace' and image.getchannel('A').getextrema()[1]==0:
        raise ValueError('Fully transparent source requires an explicit clear operation')
    left, top, right, bottom = e['source_crop']
    validate_box([left, top, right-left, bottom-top], image.width, image.height, 'source crop')
    image = image.crop((left, top, right, bottom))
    image = orient(image,e['flip_x'],e.get('quarter_turns',0))
    px, py, pw, ph = validate_box(e['placement'], page['width'], page['height'], 'placement')
    if px < x or py < y or px+pw > x+w or py+ph > y+h:
        raise ValueError('Placement exceeds destination crop')
    canvas = Image.new('RGBA', (w, h))
    canvas.alpha_composite(image.resize((pw, ph), Image.Resampling.NEAREST), (px-x, py-y))
    return canvas


def build(donor, common, manifest):
    if manifest.get('schema') != 1 or manifest.get('mode') != 'texture-diagnostic':
        raise ValueError('Only schema 1 texture diagnostics supported')
    if manifest['donor_sha256'] != sha(donor) or manifest['common_sha256'] != sha(common):
        raise ValueError('Donor/common asset hash mismatch')
    if type(manifest['palette']) is not int:
        raise ValueError('Palette must be an integer')
    pages = pages_of(donor, manifest['palette'])
    rects = rectangles(common, manifest['rectangle_resource'])
    selected = [e for e in manifest['entries'] if e.get('selected') is True]
    if not selected:
        raise ValueError('Select explicit mappings before building')
    # Validate all sources/destinations before making any output.
    regions = {}
    prepared = []
    for e in selected:
        page = pages[e['page']]
        x, y, w, h = validate_box(e['destination'], page['width'], page['height'], 'destination')
        r = rects[e['rectangle_index']]
        if [r['page_candidate'], r['x'], r['y'], r['width'], r['height']] != [e['page'], x, y, w, h]:
            raise ValueError('Mapping does not match the common rectangle candidate')
        for ox, oy, ow, oh in regions.setdefault(e['page'], []):
            if x < ox+ow and ox < x+w and y < oy+oh and oy < y+h:
                raise ValueError('Selected destination rectangles overlap')
        regions[e['page']].append((x, y, w, h))
        canvas = render_sprite(e, page)
        indices, error = quantize(canvas, page['colors'])
        prepared.append((e, indices, error))
    output = bytearray(donor)
    reports = []
    for e, indices, error in prepared:
        page = pages[e['page']]
        x, y, w, h = e['destination']
        for row in range(h):
            start = page['data_offset']+(y+row)*page['width']+x
            output[start:start+w] = indices[row*w:(row+1)*w]
        reports.append(dict(pose=e['pose'], rectangle_index=e['rectangle_index'],
                            page=e['page'], flip_x=e['flip_x'], rgb_rmse=error,
                            quarter_turns=e.get('quarter_turns',0),
                            operation=e.get('operation','replace')))
    # Check the entire byte difference, not only the changed rectangle outputs.
    allowed = bytearray(len(donor))
    for e, _, _ in prepared:
        page = pages[e['page']]
        x, y, w, h = e['destination']
        for row in range(h):
            start = page['data_offset']+(y+row)*page['width']+x
            allowed[start:start+w] = bytes([1])*w
    if any(a != b and not allowed[i] for i, (a, b) in enumerate(zip(donor, output))):
        raise ValueError('Unexpected changes outside mapped index regions')
    meta = parse_anm(donor)
    if output[:meta['payload_start']] != donor[:meta['payload_start']]:
        raise ValueError('Animation metadata changed')
    for p in anm_pages(donor, include_rgba=False):
        header = p['palette_header_offset']
        size = struct.unpack_from('>H', donor, header+4)[0]*struct.unpack_from('>H', donor, header+6)[0]*4
        start = meta['payload_start']+struct.unpack_from('>I', donor, header+12)[0]
        if output[start:start+size] != donor[start:start+size]:
            raise ValueError('Palette data aliases patched texture region')
    parse_anm(output)
    packed = compress_lzs(bytes(output))
    if unlzs(packed) != output:
        raise ValueError('Compression roundtrip mismatch')
    return bytes(output), packed, dict(mode='texture-diagnostic', mapped_sprites=len(reports),
                                      poses=reports, expanded_bytes=len(output), packed_bytes=len(packed),
                                      output_sha256=sha(output), metadata_and_palettes='Byte-identical to donor',
                                      unchanged_regions='Every byte outside selected pixel regions checked',
                                      compression_roundtrip='passed', gameplay_validated=False)


def compose(donor, mappings):
    """Combine validated mappings from separate rectangle tables onto one body."""
    if not mappings:
        raise ValueError('Composition requires mappings')
    output = bytearray(donor)
    assigned = bytearray(len(donor))
    pages = pages_of(donor)
    reports = []
    touched = set()
    for common, manifest in mappings:
        expanded, _, report = build(donor, common, manifest)
        for e in manifest['entries']:
            if e.get('selected') is not True:
                continue
            page = pages[e['page']]
            touched.add(e['page'])
            x, y, w, h = e['destination']
            for row in range(h):
                start = page['data_offset']+(y+row)*page['width']+x
                for index in range(start, start+w):
                    if assigned[index] and output[index] != expanded[index]:
                        raise ValueError('Composition mappings conflict in shared atlas pixels')
                    output[index] = expanded[index]
                    assigned[index] = 1
        reports.append(report)
    packed = compress_lzs(bytes(output))
    if unlzs(packed) != output:
        raise ValueError('Composition compression roundtrip mismatch')
    return bytes(output), packed, dict(mode='texture-composition', mappings=reports,
        mapped_sprites=sum(r['mapped_sprites'] for r in reports), touched_pages=sorted(touched),
        expanded_bytes=len(output), packed_bytes=len(packed), output_sha256=sha(output),
        metadata_and_palettes='Byte-identical to donor', gameplay_validated=False)


def walk_preview(expanded, manifest, target):
    """Preview decoded output crops; cadence is illustrative, not native timing."""
    entries = {e['pose']: e for e in manifest['entries'] if e.get('selected') is True}
    needed = [f'{facing}/walk{i:02d}' for facing in ('front', 'back') for i in range(1,7)]
    if not set(needed).issubset(entries):
        return False
    pages = {i: page_image(p) for i, p in pages_of(expanded, manifest['palette']).items()}
    frames = []
    for i in range(1,7):
        canvas = Image.new('RGB', (384,240), (35,38,45))
        draw = ImageDraw.Draw(canvas)
        draw.text((12,8),'Atlas preview; D2 timing unvalidated',fill='white')
        for col, facing in enumerate(('front','back')):
            e=entries[f'{facing}/walk{i:02d}']
            x,y,w,h=e['destination']
            image=pages[e['page']].crop((x,y,x+w,y+h))
            canvas.paste(image,(col*192+(192-w)//2,230-h),image)
            draw.text((col*192+12,30),f'{facing} walk{i:02d}',fill='white')
        frames.append(canvas)
    frames[0].save(target,save_all=True,append_images=frames[1:],duration=100,loop=0,disposal=2)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('suggest', 'build', 'compose'))
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--member', default='anm00030.lzs')
    parser.add_argument('--common-member', default='anm00001.lzs')
    parser.add_argument('--rectangle-resource', type=int, default=1,
                        help='Resource block containing crop rectangles (default: shared resource 1)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--appearance', type=Path)
    parser.add_argument('--rectangles', help='Comma-separated candidate indices; omitted inspects all')
    parser.add_argument('--rotations',default='0',help='Candidate counterclockwise quarter turns, e.g.0,1,2,3; default0')
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    validate_name(args.member)
    validate_name(args.common_member)
    output = _no_symlinks(args.output.absolute())
    if output.exists():
        parser.error('Output directory must be new')
    donor = archive_member(args.archive, args.member)
    common = archive_member(args.archive, args.common_member)
    if args.command == 'suggest':
        if not args.reference or not args.appearance:
            parser.error('suggest requires --reference and --appearance')
        indices = list(map(int, args.rectangles.split(','))) if args.rectangles else None
        result = suggest(donor, common, args.reference, args.appearance,
                         resource_id=args.rectangle_resource, indices=indices,
                         quarter_turns=tuple(map(int,args.rotations.split(','))))
        result.update(archive=str(args.archive.absolute()), member=args.member, common_member=args.common_member)
        output.mkdir(parents=True)
        (output/'mapping.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(candidates=len(result['entries']), skipped=len(result['skipped']),
                              mapping=str(output/'mapping.json'))))
    else:
        if not args.manifest:
            parser.error('build requires --manifest')
        manifest = json.loads(read(args.manifest))
        if args.command == 'compose':
            if manifest.get('schema') != 1 or manifest.get('mode') != 'texture-composition':
                raise ValueError('Only schema 1 texture compositions supported')
            mappings = []
            for mapping_path in manifest['mappings']:
                path = Path(mapping_path)
                if not path.is_absolute():
                    path = args.manifest.absolute().parent/path
                mapping = json.loads(read(path))
                if mapping['member'] != args.member:
                    raise ValueError('Composition donor member mismatch')
                validate_name(mapping['common_member'])
                mappings.append((archive_member(args.archive, mapping['common_member']), mapping))
            expanded, packed, report = compose(donor, mappings)
        else:
            expanded, packed, report = build(donor, common, manifest)
        output.mkdir(parents=True)
        (output/args.member).write_bytes(packed)
        retained = manifest
        if args.command == 'compose':
            retained = dict(manifest, mappings=[])
            for index,(_,component) in enumerate(mappings):
                name = f'mapping-{index}.json'
                (output/name).write_text(json.dumps(component,indent=2)+'\n')
                retained['mappings'].append(name)
        (output/'mapping.json').write_text(json.dumps(retained, indent=2)+'\n')
        # Export every affected page/palette combination, not just palette zero.
        touched = (set(report['touched_pages']) if args.command == 'compose' else
                   {e['page'] for e in manifest['entries'] if e.get('selected') is True})
        for p in anm_pages(expanded, include_rgba=False):
            if p['texture'] in touched:
                (output/f"page-{p['texture']}-palette-{p['palette']}.png").write_bytes(
                    indexed_png(p['width'], p['height'], p['indices'], p['colors']))
        preview_manifest = mappings[0][1] if args.command == 'compose' else manifest
        report['walk_preview'] = 'walk-preview.gif' if walk_preview(expanded, preview_manifest, output/'walk-preview.gif') else None
        if report['walk_preview']:
            report['preview_cadence'] = 'Illustrative 100 ms per pose; native D2 timing unvalidated'
        (output/'validation.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
