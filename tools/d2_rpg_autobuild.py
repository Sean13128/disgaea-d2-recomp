#!/usr/bin/env python3
"""Build a complete D2 body appearance from an RPG costume and a pose template.

Every atlas rectangle named by the template is repainted: exact poses at
native scale where they fit, bounded fitting for oversized art, and poses the RPG art
lacks, plus explicit clears for overlay parts. No donor artwork remains inside
templated rectangles. Animation metadata, headers and dimensions are kept
byte-identical; colours are authored once for all native palette slots.
Output is offline only and never installs files.
"""
import argparse
import collections
import json
from pathlib import Path
import re

from PIL import Image, ImageChops, ImageDraw

from d2_asset_pack import validate_name
from d2_character_export import _no_symlinks, anm_pages, indexed_png
from d2_rpg_map import archive_member, page_image, pages_of, read, sha
from d2_rpg_palette import encode_images
from d2_rpg_template import SCHEMA, _tables, catalog, mask, orient
import d2_anm_cells as cells

RANK = dict(clear=1, fallback=2, exact=3)
PART = re.compile(r'_hand(\d\d)?$')
FRAME = re.compile(r'\d+$')


def resolve_pose(pose, sprites):
    """Costume sprite for a template pose, or an explicit documented substitute."""
    def usable(key):
        return key in sprites and sprites[key]['image'].getchannel('A').getextrema()[1] >= 64
    if usable(pose):
        return pose, None
    facing, name = pose.split('/', 1)
    if PART.search(name):
        return None, 'Part sprite absent or transparent in costume; cleared'
    stem = re.sub(r'\d\d$', '', name)
    siblings = sorted(k for k in sprites if k.startswith(facing+'/'+stem) and
                      re.fullmatch(re.escape(stem)+r'\d\d', k.split('/', 1)[1]) and usable(k))
    if siblings:
        return siblings[0], 'Pose absent; nearest numbered frame reused'
    for other in (facing+'/stand', facing.replace('wait_', '')+'/stand', facing+'/wait01'):
        if usable(other):
            return other, 'Pose absent; standing frame reused'
    return None, 'Pose absent and no standing frame; cleared'


def fit_overflow(entries):
    """Keep remaining oversized art inside the native cell's transparent rim.

    Growable own cells are handled first. Shared cells and atlas-limited own
    cells retain their geometry; their art is fitted about its authored pivot.
    Numbered poses in one sequence use the same scale to avoid size pulsing.
    """
    groups = collections.defaultdict(list)
    for e in entries:
        if 'image' not in e:
            continue
        facing, name = e['pose_used'].split('/', 1)
        groups[(e['block'], facing, re.sub(r'\d\d$', '', name), bool(e['row'].get('enlarged')))].append(e)
    for group in groups.values():
        scale = 1.0
        for e in group:
            bounds = mask(e['image']).getbbox()
            if not bounds:
                continue
            w, h = e['destination'][2:]
            if w < 3 or h < 3:
                raise ValueError('Costume cell has no room for a transparent rim')
            scale = min(scale, (w-2)/(bounds[2]-bounds[0]), (h-2)/(bounds[3]-bounds[1]))
        for e in group:
            image = e['image']
            bounds = mask(image).getbbox()
            if not bounds:
                continue
            px, py = e['offset']
            w, h = e['destination'][2:]
            if scale == 1 and px+bounds[0] >= 1 and py+bounds[1] >= 1 and px+bounds[2] <= w-1 and py+bounds[3] <= h-1:
                continue
            crop = image.crop(bounds)
            size = (max(1, min(w-2, int(crop.width*scale))), max(1, min(h-2, int(crop.height*scale))))
            fitted = crop.resize(size, Image.Resampling.NEAREST)
            # Preserve the intended pivot position as far as cell bounds permit.
            sx, sy = size[0]/crop.width, size[1]/crop.height
            pivot = e['source_pivot']
            x = round(px+pivot[0]-(pivot[0]-bounds[0])*sx)
            y = round(py+pivot[1]-(pivot[1]-bounds[1])*sy)
            x, y = max(1, min(w-1-size[0], x)), max(1, min(h-1-size[1], y))
            e['row']['frame_fit'] = dict(scale=round(scale, 6), source_bounds=list(bounds),
                                        size=list(size), offset=[x, y],
                                        source_opaque_pixels=sum(mask(image).histogram()[255:]))
            e.update(image=fitted, offset=(x, y))


def steady_mismatched(entries):
    """One placement correction for all frames of an animation on a foreign canvas.

    Standing every frame on its own opaque outline makes the figure wander as a
    cape or weapon changes shape. Frames of one animation share a canvas, so
    they share one correction: none along an axis whose canvas length matches
    the reference, otherwise the median of what the frames ask for.
    """
    groups = collections.defaultdict(list)
    for e in entries:
        if 'stand' in e:
            groups[(e['block'], FRAME.sub('', e['pose_used']), e['flip_x'], e['quarter_turns'],
                    e['image'].size, tuple(e['reference_size']))].append(e)
    for key, members in groups.items():
        size, reference = key[4], key[5]
        shift = [0 if size[axis] == reference[axis] else sorted(e['stand'][axis] for e in members)[len(members)//2]
                 for axis in (0, 1)]
        for e in members:
            e['offset'] = (e['offset'][0]+shift[0], e['offset'][1]+shift[1])
            e['row']['canvas_shift'] = shift
            del e['stand']


def compose(donor, template, sprites, common=None, grow=True):
    """RGBA pages with every templated rectangle repainted from the costume.

    Returns the donor bytes to encode against (edited only when donor-specific
    cells were enlarged), the pages, a per-rectangle report, leftover donor
    pixel counts and the cell-growth report.
    """
    if template.get('schema') != SCHEMA or template.get('mode') != 'pose-template':
        raise ValueError('Expected a donor pose template')
    if template['donor_sha256'] != sha(donor):
        raise ValueError('Template was built for a different donor body')
    pages = pages_of(donor)
    images = {key: page_image(page) for key, page in pages.items()}
    original = {key: mask(image) for key, image in images.items()}
    entries = [dict(e) for e in sorted(template['entries'],
                                       key=lambda e: (RANK[e['match']], -e['destination'][2]*e['destination'][3]))]
    covered = {key: Image.new('L', image.size) for key, image in images.items()}

    def wipe(e):
        x, y, w, h = e['destination']
        image = images[e['page']]
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > image.width or y+h > image.height:
            raise ValueError('Template rectangle outside donor page')
        image.paste((0, 0, 0, 0), (x, y, x+w, y+h))
        covered[e['page']].paste(255, (x, y, x+w, y+h))
    # First empty every templated rectangle so no donor pixels can survive.
    for e in entries:
        wipe(e)
    # Resolve each pose and where its art lands inside the present cell.
    for e in entries:
        e['row'] = row = dict(block=e['block'], rectangle_index=e['rectangle_index'], page=e['page'],
                              match=e['match'], template_pose=e.get('pose'))
        if e['match'] == 'clear':
            continue
        pose, note = resolve_pose(e['pose'], sprites)
        if note:
            row['substitution'] = note
        if not pose:
            row['cleared'] = True
            continue
        image, pivot = orient(sprites[pose]['image'], sprites[pose]['pivot'], e['flip_x'], e['quarter_turns'])
        px, py = round(e['pivot'][0]-pivot[0]), round(e['pivot'][1]-pivot[1])
        e.update(image=image, offset=(px, py), pose_used=pose, source_pivot=pivot)
        if list(image.size) != e.get('reference_size', list(image.size)):
            # Different canvas than the reference character's pose: the art
            # stands on the reference's opaque bottom/centre instead.
            sb, rb = mask(image).getbbox(), e['reference_bounds']
            e['stand'] = (round((rb[0]+rb[2])/2-(sb[0]+sb[2])/2)-px, rb[3]-sb[3]-py)
            row['canvas_mismatch'] = True
    steady_mismatched(entries)
    growth = None
    if grow and common is not None:
        needs, content = {}, {}
        for e in entries:
            if e['block'] == 'own' and 'image' in e:
                sb = mask(e['image']).getbbox()
                w, h = e['destination'][2:]
                px, py = e['offset']
                # Art must stay inside the one-pixel transparent rim of its cell.
                need = (max(0, 1-(px+sb[0])), max(0, 1-(py+sb[1])), max(0, px+sb[2]-(w-1)), max(0, py+sb[3]-(h-1)))
                if any(need):
                    needs[e['rectangle_index']] = need
                content[e['rectangle_index']] = (e['pose_used'], e['flip_x'], e['quarter_turns'], e['offset'], w, h)
        if needs:
            growth = cells.plan(donor, template['body_id'], entries, needs, _tables(common, 1)['rects'],
                                {key: image.size for key, image in images.items()},
                                symmetric=(grow == 'symmetric'), content=content)
    if growth and growth['moves']:
        donor = cells.apply(donor, template['body_id'], growth)
        # A page made taller gains transparent rows below its original art.
        for page, (width, height) in (growth.get('page_resize') or {}).items():
            for store, mode, fill in ((images, 'RGBA', (0, 0, 0, 0)), (original, 'L', 0), (covered, 'L', 0)):
                taller = Image.new(mode, (width, height), fill)
                taller.paste(store[page], (0, 0))
                store[page] = taller
        kept = []
        for e in entries:
            if e['block'] == 'own' and e['rectangle_index'] in growth['hidden']:
                e['row'].update(hidden=True, cleared=True)
                continue
            move = growth['moves'].get(e['rectangle_index']) if e['block'] == 'own' else None
            if move:
                mx, my = move['margin']
                e['destination'] = move['destination']
                e['offset'] = (e['offset'][0]+mx, e['offset'][1]+my)
                e['row']['enlarged'] = dict(destination=move['destination'], margin=move['margin'])
                wipe(e)
            kept.append(e)
        hidden_rows = [e['row'] for e in entries if e['row'].get('hidden')]
        entries = kept
    else:
        hidden_rows = []
    fit_overflow(entries)
    report = hidden_rows
    for e in entries:
        row = e.pop('row')
        report.append(row)
        if 'image' not in e:
            continue
        x, y, w, h = e['destination']
        px, py = e['offset']
        layer = Image.new('RGBA', (w, h))
        layer.paste(e['image'], (px, py))
        # A transparent one-pixel rim keeps filtered sampling from pulling a
        # neighbouring cell's edge into view when art reaches the cell border.
        rim = Image.new('RGBA', (w, h))
        rim.paste(layer.crop((1, 1, w-1, h-1)), (1, 1))
        visible = mask(e['image'])
        total = sum(visible.histogram()[255:])
        kept_pixels = sum(mask(rim).histogram()[255:])
        row.update(pose=e['pose_used'], source_sha256=sprites[e['pose_used']]['sha256'], placement=[x+px, y+py],
                   opaque_pixels=total, clipped_pixels=total-kept_pixels,
                   clipped_fraction=round((total-kept_pixels)/total, 4) if total else 0.0)
        images[e['page']].alpha_composite(rim, (x, y))
    residual = {}
    shared = {key: Image.new('L', image.size) for key, image in images.items()}
    if common is not None:
        for words in _tables(common, 1)['rects']:
            image = images.get(words[0])
            if image is not None and words[6] and words[7] and words[4]+words[6] <= image.width \
                    and words[5]+words[7] <= image.height:
                shared[words[0]].paste(255, (words[4], words[5], words[4]+words[6], words[5]+words[7]))
    for key, image in images.items():
        outside = Image.composite(Image.new('L', image.size), original[key], covered[key])
        # Donor pixels that no template rectangle owns but a shared rectangle
        # could still draw are removed; the rest is never drawn by known art.
        stray = ImageChops.multiply(outside, shared[key])
        if stray.getbbox():
            image.paste((0, 0, 0, 0), mask=stray)
            outside = ImageChops.subtract(outside, stray)
        count = sum(outside.histogram()[255:])
        if count:
            residual[str(key)] = count
    growth_report = None
    if growth:
        growth_report = dict(enlarged={str(r): m for r, m in growth['moves'].items()}, hidden_parts=growth['hidden'],
                             symmetric=growth.get('symmetric'), shared_cells=growth.get('shared_cells', 0),
                             taller_pages={str(p): size for p, size in (growth.get('page_resize') or {}).items()},
                             skipped=growth['skipped'],
                             right_down_only=growth.get('pinned', []),
                             pivot_edits={str(a): m for a, m in growth.get('anchor_edits', {}).items()},
                             key_edits=len(growth.get('key_edits', [])))
    return donor, images, report, residual, growth_report


def review_sheet(donor, template, images, report, target):
    pages = {i: page_image(p) for i, p in pages_of(donor).items()}
    rows = {(r['block'], r['rectangle_index']): r for r in report}
    entries = template['entries']
    cols, cw, ch = 5, 300, 214
    canvas = Image.new('RGBA', (cols*cw, ch*((len(entries)+cols-1)//cols)), (30, 30, 34, 255))
    draw = ImageDraw.Draw(canvas)
    colors = dict(exact=(120, 220, 140), fallback=(240, 200, 90), clear=(240, 120, 120))
    for n, e in enumerate(entries):
        r = rows[(e['block'], e['rectangle_index'])]
        ox, oy = (n % cols)*cw, (n//cols)*ch
        boxes = (e['destination'], r.get('enlarged', {}).get('destination', e['destination']))
        for col, (source, (x, y, w, h)) in enumerate(zip((pages, images), boxes)):
            if col and r.get('hidden'):
                continue
            scale = min(1.0, 140/w, 176/h)
            size = (max(1, round(w*scale)), max(1, round(h*scale)))
            crop = source[e['page']].crop((x, y, x+w, y+h)).resize(size, Image.Resampling.NEAREST)
            canvas.alpha_composite(crop, (ox+4+col*148, oy+4))
        flags = ''.join((' CLIP%d' % r['clipped_pixels'] if r.get('clipped_pixels') else '',
                         ' SUB' if r.get('substitution') else '', ' BIGGER' if r.get('enlarged') else '',
                         ' HIDDEN' if r.get('hidden') else ''))
        draw.text((ox+4, oy+182), '%s %d p%d %s%s' % (e['block'][0], e['rectangle_index'], e['page'], e['match'], flags),
                  fill=colors[e['match']])
        draw.text((ox+4, oy+196), str(r.get('pose') or '-'), fill='white')
    canvas.convert('RGB').save(target)


def build(archive, template_path, costume, output, pages_png=True, grow=True):
    output = _no_symlinks(Path(output).absolute())
    if output.exists():
        raise ValueError('Output directory must be new')
    template = json.loads(read(template_path))
    member = template['member']
    validate_name(member)
    original = archive_member(archive, member)
    common = archive_member(archive, template.get('common_member', 'anm00001.lzs'))
    sprites = catalog(costume)
    donor, images, report, residual, growth = compose(original, template, sprites, common, grow)
    expanded, packed, encoded = encode_images(donor, images, sum(1 for r in report if r.get('pose')))
    encoded['metadata'] = ('Byte-identical animation definitions and headers' if donor == original else
                           'Only the listed donor-specific rectangle, pivot and hidden-part key entries differ')
    clipped = [r for r in report if r.get('clipped_fraction', 0) > 0.01]
    summary = dict(schema=1, mode='automatic-appearance-build', member=member, body_id=template['body_id'],
                   template_sha256=sha(read(template_path)), costume=str(Path(costume).absolute()),
                   costume_manifest_sha256=sha(read(Path(costume)/'manifest.json')),
                   counts=dict(collections.Counter(r['match'] for r in report)),
                   painted=sum(1 for r in report if r.get('pose')),
                   cleared=sum(1 for r in report if not r.get('pose')),
                   substitutions=[r for r in report if r.get('substitution')],
                   clipped_over_1_percent=clipped,
                   fitted_frames=sum(1 for r in report if r.get('frame_fit')),
                   canvas_mismatches=sum(1 for r in report if r.get('canvas_mismatch')),
                   cell_growth=growth,
                   donor_pixels_inside_templated_rectangles=0,
                   donor_pixels_outside_any_rectangle=residual,
                   residual_note='Pixels outside every known rectangle keep donor art; no known animation draws them.',
                   encoding=encoded, entries=report, gameplay_validated=False)
    output.mkdir(parents=True)
    (output/member).write_bytes(packed)
    (output/'expanded.bin').write_bytes(expanded)
    if pages_png:
        for page in anm_pages(expanded, include_rgba=False, palette_indices=[0]):
            (output/f"page-{page['texture']}.png").write_bytes(
                indexed_png(page['width'], page['height'], page['indices'], page['colors']))
    review_sheet(original, template, images, report, output/'review.png')
    (output/'build.json').write_text(json.dumps(summary, indent=1)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--costume', type=Path, required=True, help='Extracted RPG costume directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--grow', choices=('yes', 'symmetric', 'no'), default='yes',
                        help='Enlarge donor-specific cells for oversized art: yes (default), symmetric (equal '
                             'margins on opposite sides), or no (original cells; oversized art is fitted)')
    args = parser.parse_args()
    s = build(args.archive, args.template, args.costume, args.output,
              grow=dict(yes=True, symmetric='symmetric', no=False)[args.grow])
    print(json.dumps({k: s[k] for k in ('member', 'counts', 'painted', 'cleared', 'donor_pixels_outside_any_rectangle')}
                     | dict(substitutions=len(s['substitutions']), clipped_over_1_percent=len(s['clipped_over_1_percent']),
                            canvas_mismatches=s['canvas_mismatches'],
                            enlarged_cells=len((s['cell_growth'] or {}).get('enlarged', {})),
                            hidden_parts=len((s['cell_growth'] or {}).get('hidden_parts', [])),
                            growth_skipped=(s['cell_growth'] or {}).get('skipped', []),
                            packed_bytes=s['encoding']['packed_bytes'], output_sha256=s['encoding']['output_sha256']), indent=1))


if __name__ == '__main__':
    main()
