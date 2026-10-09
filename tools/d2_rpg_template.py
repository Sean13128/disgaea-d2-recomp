#!/usr/bin/env python3
"""Derive a reusable pose template for a D2 donor body from RPG reference art.

D2 and RPG sprites of the same character share scale and artwork. Aligning a
reference character against the donor atlas therefore identifies, for every
atlas rectangle, the named pose it holds and where that pose's pivot sits in
the rectangle. A template stores only rectangle indices, pose names,
orientation and pivot positions; it contains no artwork and applies to any RPG
costume drawn on the same pose set. Rectangles without an exact reference pose
receive a reviewed-by-rule fallback (nearest silhouette) or an explicit clear.
Animation usage is read from the empirical track/key tables to classify
rectangles; native action behaviour still requires in-game acceptance.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import struct

from PIL import Image, ImageChops, ImageOps, ImageStat

from d2_anm import parse_anm
from d2_asset_pack import validate_name
from d2_character_export import _no_symlinks
from d2_rpg_map import (archive_member, box, normalized, page_image, pages_of,
                        read, rgba, sha)

SCHEMA = 2
LABELS = ('front', 'back', 'wait_front', 'wait_back')
SURE_IOU = 0.97
EXACT_IOU = 0.93
WEAK_IOU = 0.62
VOTE_IOU = 0.55
BODY_FRACTION = 0.62
SECONDARY_LAYERS = {0x15, 0x1f}
# Donor-specific animation tags observed in every surveyed unique body.
IDLE = {(6001,): 'wait_front', (6007,): 'wait_back'}
PART = re.compile(r'_hand(\d\d)?$')


def catalog(root):
    """Named RPG sprites with pivots in image pixels (top-left origin)."""
    root = _no_symlinks(Path(root).absolute())
    manifest = json.loads(read(root/'manifest.json'))
    result = {}
    for bundle in manifest['bundles']:
        if bundle['label'] not in LABELS:
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
            data = read(root/relative)
            image = rgba(data)
            pivot = sprite.get('pivot') or dict(x=0.5, y=0.0)
            px, py = float(pivot['x']), float(pivot['y'])
            if not (-4 <= px <= 4 and -4 <= py <= 4):
                raise ValueError('Implausible sprite pivot: '+key)
            result[key] = dict(path=str(root/relative), sha256=sha(data), image=image,
                               pivot=(px*image.width, (1-py)*image.height))
    if not result:
        raise ValueError('No named battle sprites in '+str(root))
    return result


def orient(image, pivot, flip, turns):
    """Mirror, then rotate counterclockwise; return image and moved pivot."""
    if type(flip) is not bool or turns not in (0, 1, 2, 3):
        raise ValueError('Orientation requires boolean flip and quarter turns 0..3')
    x, y = pivot
    w, h = image.size
    if flip:
        image = ImageOps.mirror(image)
        x = w-x
    if turns == 1:
        image = image.transpose(Image.Transpose.ROTATE_90)
        x, y = y, w-x
    elif turns == 2:
        image = image.transpose(Image.Transpose.ROTATE_180)
        x, y = w-x, h-y
    elif turns == 3:
        image = image.transpose(Image.Transpose.ROTATE_270)
        x, y = h-y, x
    return image, (x, y)


def mask(image):
    return image.getchannel('A').point(lambda a: 255 if a >= 64 else 0)


def _tables(raw, resource_id):
    meta = parse_anm(raw)
    blocks = [b for b in meta['blocks'] if b['resource_id'] == resource_id]
    if len(blocks) != 1:
        raise ValueError('Missing or ambiguous resource block %d' % resource_id)
    tables = blocks[0]['tables']

    def rows(name, fmt):
        t = tables[name]
        size = struct.calcsize(fmt)
        if size != t['stride']:
            raise ValueError('Unexpected table stride: '+name)
        return [struct.unpack_from(fmt, raw, t['offset']+i*size) for i in range(t['count'])]
    return dict(tags=rows('tags', '>2H'), tracks=rows('tracks', '>8H'), keys=rows('keys', '>6H'),
                rects=rows('rectangle_candidates', '>9H'))


def rectangle_usage(raw, resource_id):
    """Rectangle index -> sorted layers and animation tags that draw it.

    Empirical reading: tag=(animation id, first track); track word1 high byte
    is a layer, words 4/5 a key range; key word1 high byte marks control keys
    and word2 is the rectangle index. Used for classification only.
    """
    t = _tables(raw, resource_id)
    usage = collections.defaultdict(lambda: dict(layers=set(), animations=set()))
    tags, tracks, keys = t['tags'], t['tracks'], t['keys']
    for i, (animation, first) in enumerate(tags):
        last = tags[i+1][1] if i+1 < len(tags) else len(tracks)
        if not first <= last <= len(tracks):
            raise ValueError('Animation tag track range out of order')
        for track in tracks[first:last]:
            if track[4] == 0xffff:
                continue
            if track[4]+track[5] > len(keys):
                raise ValueError('Track key range exceeds key table')
            layer = track[1] >> 8
            for key in keys[track[4]:track[4]+track[5]]:
                if key[1] & 0xff00 or key[2] >= len(t['rects']):
                    continue
                usage[key[2]]['layers'].add(layer)
                usage[key[2]]['animations'].add(animation)
    return {index: dict(layers=sorted(v['layers']), animations=sorted(v['animations']))
            for index, v in usage.items()}, t['rects']


def _iou(a, b):
    inter = ImageStat.Stat(ImageChops.multiply(a, b)).sum[0]/255
    union = ImageStat.Stat(ImageChops.lighter(a, b)).sum[0]/255
    return inter/union if union else 0.0


def _placed_iou(target, cand, ox, oy):
    placed = Image.new('L', target.size)
    placed.paste(cand['mask'], (ox, oy))
    return _iou(target, placed)


def align(crop, candidates):
    """Best exact placement of an oriented reference sprite inside a crop."""
    target = mask(crop)
    bounds = target.getbbox()
    if not bounds:
        return None
    width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
    best = None
    for cand in candidates:
        cb = cand['bounds']
        if abs((cb[2]-cb[0])-width) > 6 or abs((cb[3]-cb[1])-height) > 6:
            continue
        for jx in (0, -1, 1, -2, 2):
            for jy in (0, -1, 1, -2, 2):
                ox, oy = bounds[0]-cb[0]+jx, bounds[1]-cb[1]+jy
                score = _placed_iou(target, cand, ox, oy)
                if best is None or score > best[0]:
                    best = (score, cand, ox, oy)
            if best and best[0] > 0.985:
                break
    return best


def _reduced(image, factor=4):
    """Area-averaged mask at 1/factor scale for a cheap shortlist search."""
    size = (max(1, -(-image.width//factor)), max(1, -(-image.height//factor)))
    return image.resize(size, Image.Resampling.BOX)


def nearest(crop, candidates, shortlist=6, loose=False):
    """Closest reference pose by translated silhouette overlap (no scaling).

    ``loose`` drops the size screen, for donor cells that hold only part of
    the figure the reference frame shows (a body whose cape is keyed apart)."""
    target = mask(crop)
    bounds = target.getbbox()
    width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
    small = _reduced(target)
    coarse = []
    for n, cand in enumerate(candidates):
        cb = cand['bounds']
        cw, ch = cb[2]-cb[0], cb[3]-cb[1]
        if not loose and not (0.6 <= cw/width <= 1.6 and 0.6 <= ch/height <= 1.6):
            continue
        # Stand on the donor's opaque bottom/centre, then search nearby.
        sx = round((bounds[0]+bounds[2])/2-(cb[0]+cb[2])/2)
        sy = bounds[3]-cb[3]
        if 'small' not in cand:
            cand['small'] = _reduced(cand['mask'])
        local = None
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                placed = Image.new('L', small.size)
                placed.paste(cand['small'], (sx//4+dx, sy//4+dy))
                score = _iou(small, placed)
                if local is None or score > local[0]:
                    local = (score, sx+dx*4, sy+dy*4)
        coarse.append((local[0], n, local[1], local[2]))
    best = None
    for _, n, cx, cy in sorted(coarse, reverse=True)[:shortlist]:
        cand = candidates[n]
        local = (_placed_iou(target, cand, cx, cy), cx, cy)
        for step in (2, 1):
            _, bx, by = local
            for dx in (-2*step, -step, 0, step, 2*step):
                for dy in (-2*step, -step, 0, step, 2*step):
                    score = _placed_iou(target, cand, bx+dx, by+dy)
                    if score > local[0]:
                        local = (score, bx+dx, by+dy)
        if best is None or local[0] > best[0]:
            best = (local[0], cand, local[1], local[2])
    return best


def reference_candidates(reference):
    sprites = catalog(reference)
    candidates = []
    for key, sprite in sprites.items():
        for flip in (False, True):
            for turns in (0, 1, 2, 3):
                image, pivot = orient(sprite['image'], sprite['pivot'], flip, turns)
                m = mask(image)
                b = m.getbbox()
                if b:
                    candidates.append(dict(pose=key, flip=flip, turns=turns, pivot=pivot, mask=m, bounds=b))
    return sprites, candidates


def donor_rectangles(donor, common, body_id, common_id=1):
    """Non-empty atlas rectangles the donor actually owns, donor layout first."""
    pages = {i: page_image(p) for i, p in pages_of(donor).items()}
    entries, skipped, claimed = [], [], {}
    for block, raw, resource in (('own', donor, body_id), ('common', common, common_id)):
        usage, rects = rectangle_usage(raw, resource)
        for index, words in enumerate(rects):
            page, x, y, w, h = words[0], words[4], words[5], words[6], words[7]
            image = pages.get(page)
            if min(w, h) <= 0:
                continue
            if image is None or x+w > image.width or y+h > image.height:
                skipped.append(dict(block=block, rectangle_index=index, reason='Page or crop outside donor'))
                continue
            crop = image.crop((x, y, x+w, y+h))
            if not box(crop):
                continue
            if block == 'common' and any(p == page and x < ox+ow and ox < x+w and y < oy+oh and oy < y+h
                                         for (b, _), (p, ox, oy, ow, oh) in claimed.items() if b == 'own'):
                skipped.append(dict(block=block, rectangle_index=index,
                                    reason='Overlaps a donor-specific rectangle; donor layout takes precedence'))
                continue
            claimed[(block, index)] = (page, x, y, w, h)
            use = usage.get(index, dict(layers=[], animations=[]))
            entries.append((dict(block=block, rectangle_index=index, page=page, destination=[x, y, w, h],
                                 layers=use['layers'], animations=use['animations'][:12],
                                 animation_count=len(use['animations'])), crop))
    return entries, skipped


def idle_composites(donor, body_id, palette=0):
    """Donor idle frames as the game draws them.

    Several characters key the idle body and its cape, scarf or hair as
    separate cells on parallel tracks, while an RPG idle frame holds the whole
    figure. For every rectangle of an idle animation this returns the complete
    picture at the moment that rectangle is shown, with the character-space
    position of the picture and of the rectangle's own cell. Only plain
    (unscaled, unrotated) sprite keys are drawn; a frame with any other active
    sprite key is left out.
    """
    import d2_anm_cells
    t = _tables(donor, body_id)
    own = d2_anm_cells.own_tables(donor, body_id)
    transforms, anchors, rects = own['transforms'], own['anchors'], t['rects']
    from d2_character_export import anm_pages
    pages = {p['texture']: page_image(p) for p in anm_pages(donor, include_rgba=False, palette_indices=[palette])}
    tags, tracks, keys = t['tags'], t['tracks'], t['keys']
    result = {}
    for i, (animation, first) in enumerate(tags):
        if (animation,) not in IDLE:
            continue
        last = tags[i+1][1] if i+1 < len(tags) else len(tracks)
        lanes = []
        for track in tracks[first:last]:
            if track[4] == 0xffff or track[4]+track[5] > len(keys):
                continue
            lane = [k for k in keys[track[4]:track[4]+track[5]] if k[1] == 0]
            if lane:
                lanes.append(lane)
        for moment in sorted({k[0] for lane in lanes for k in lane if k[2]}):
            drawn, plain = [], True
            for lane in lanes:
                active = [k for k in lane if k[0] <= moment]
                if not active or not active[-1][2]:
                    continue
                key = active[-1]
                if key[2] >= len(rects) or key[3] >= len(transforms):
                    plain = False
                    break
                transform = transforms[key[3]]
                if (transform[2], transform[4], transform[5], transform[6], transform[7]) != d2_anm_cells.PLAIN \
                        or not 0 <= transform[3] < len(anchors):
                    plain = False
                    break
                words = rects[key[2]]
                page, x, y, w, h = words[0], words[4], words[5], words[6], words[7]
                image = pages.get(page)
                if image is None or min(w, h) <= 0 or x+w > image.width or y+h > image.height:
                    plain = False
                    break
                anchor = anchors[transform[3]]
                drawn.append((key[2], transform[0]-anchor[0], transform[1]-anchor[1], image.crop((x, y, x+w, y+h))))
            if not plain or len(drawn) < 2:
                continue
            left, top = min(d[1] for d in drawn), min(d[2] for d in drawn)
            right = max(d[1]+d[3].width for d in drawn)
            bottom = max(d[2]+d[3].height for d in drawn)
            picture = Image.new('RGBA', (right-left, bottom-top))
            for _, x, y, crop in drawn:
                picture.alpha_composite(crop, (x-left, y-top))
            for rect, x, y, _ in drawn:
                result.setdefault((animation, rect), dict(image=picture, origin=(left, top), cell=(x, y),
                                                          pieces=len(drawn)))
    return result


def build_template(donor, common, reference, body_id, common_id=1, votes=None):
    """Template for one donor. ``votes`` is an optional merged common template
    naming the pose other donors proved for shared rectangles; placement is
    always measured against this donor's own artwork."""
    sprites, candidates = reference_candidates(reference)
    # Unique emote/skill art usually faces the camera, so substitutes do too.
    # Lying art reuses the damage frame turned on its side, as the shared
    # knocked-down rectangles do.
    neutral = [c for c in candidates if c['turns'] == 0 and not c['flip'] and c['pose'] == 'wait_front/wait01'] or \
        [c for c in candidates if c['turns'] == 0 and c['pose'] == 'front/stand']
    lying = [c for c in candidates if c['turns'] == 1 and c['pose'] == 'front/damage']
    voted = {}
    if votes is not None:
        if votes.get('mode') != 'common-pose-template' or votes.get('schema') != SCHEMA:
            raise ValueError('Expected a merged common pose template')
        if votes['common_sha256'] != sha(common):
            raise ValueError('Common template was built from a different shared animation member')
        voted = {e['rectangle_index']: e for e in votes['entries']
                 if e['match'] != 'clear' and (e['match'] == 'exact' or e['support'] >= 2)}
    rectangles, skipped = donor_rectangles(donor, common, body_id, common_id)
    composites = idle_composites(donor, body_id)
    entries, pending, extents = [], [], []

    def record(entry, found, match):
        score, cand, ox, oy = found
        cb = cand['bounds']
        entry.update(match=match, pose=cand['pose'], flip_x=cand['flip'], quarter_turns=cand['turns'],
                     pivot=[round(ox+cand['pivot'][0], 3), round(oy+cand['pivot'][1], 3)], iou=round(score, 4),
                     canvas_offset=[ox, oy], reference_size=list(cand['mask'].size),
                     reference_bounds=[ox+cb[0], oy+cb[1], ox+cb[2], oy+cb[3]])

    for entry, crop in rectangles:
        found = align(crop, candidates)
        if found and found[0] >= SURE_IOU:
            record(entry, found, 'exact')
            b = box(crop)
            if not PART.search(found[1]['pose']):
                extents.append(max(b[2]-b[0], b[3]-b[1]))
        else:
            pending.append((entry, crop, found))
        entries.append(entry)
    if not extents:
        raise ValueError('Reference art does not match this donor; choose the RPG version of the same character')
    extents.sort()
    body_extent = extents[len(extents)//2]*BODY_FRACTION
    for entry, crop, exact in pending:
        b = box(crop)
        part = max(b[2]-b[0], b[3]-b[1]) < body_extent
        # Rectangles drawn only on the secondary layers are separate cloth,
        # hair or hand pieces; RPG sprites already contain them.
        overlay = bool(entry['layers']) and set(entry['layers']) <= SECONDARY_LAYERS
        vote = voted.get(entry['rectangle_index']) if entry['block'] == 'common' and not overlay else None
        if vote:
            same = [c for c in candidates if (c['pose'], c['flip'], c['turns']) ==
                    (vote['pose'], vote['flip_x'], vote['quarter_turns'])]
            found = max((f for f in (align(crop, same), nearest(crop, same, shortlist=1)) if f),
                        key=lambda f: f[0], default=None)
            if found and found[0] >= VOTE_IOU:
                record(entry, found, 'exact' if found[0] >= EXACT_IOU else 'fallback')
                entry['voted_by'] = vote['support']
                continue
        if exact and exact[0] >= EXACT_IOU and part and not overlay:
            record(entry, exact, 'exact')
            continue
        idle = IDLE.get(tuple(entry['animations'])) if entry['block'] == 'own' and not part else None
        if idle:
            # Donor idle frames often omit separately animated cloth that the
            # RPG idle frames include; keep them on the matching idle set.
            same = [c for c in candidates if c['pose'].startswith(idle+'/') and c['turns'] == 0]
            # First compare the whole figure as drawn (body plus its separately
            # keyed pieces): that is what the RPG frame shows, so a pixel match
            # also fixes the frame's exact place in character space.
            whole = composites.get((entry['animations'][0], entry['rectangle_index']))
            if whole:
                found = align(whole['image'], same)
                if found and found[0] >= EXACT_IOU:
                    shift = (whole['origin'][0]-whole['cell'][0], whole['origin'][1]-whole['cell'][1])
                    record(entry, (found[0], found[1], found[2]+shift[0], found[3]+shift[1]), 'exact')
                    entry.update(idle_set=idle, composite_pieces=whole['pieces'])
                    continue
            found = max((f for f in (align(crop, same), nearest(crop, same, shortlist=len(same))) if f),
                        key=lambda f: f[0], default=None)
            if found and found[0] >= VOTE_IOU:
                record(entry, found, 'exact' if found[0] >= EXACT_IOU else 'fallback')
                entry['idle_set'] = idle
                continue
            # Nothing close: stay inside the idle set anyway. A frame from
            # another action in the middle of an idle loop is worse than a
            # neighbouring idle frame; anchoring below fixes its position.
            found = nearest(crop, same, shortlist=len(same), loose=True)
            if found:
                record(entry, found, 'fallback')
                entry.update(idle_set=idle, reason='No close idle frame; nearest frame of the same idle set')
                continue
        if part or overlay:
            entry.update(match='clear', reason='Secondary-layer piece; RPG sprites already contain it' if overlay
                         else 'Part without reference art')
            if overlay:
                entry['secondary'] = True
            continue
        # No pixel-identical reference pose. Reuse the closest silhouette at
        # native scale, positioned for maximum overlap with the donor art.
        found = nearest(crop, candidates)
        if exact and (not found or exact[0] >= found[0]):
            found = exact
        if not found:
            entry.update(match='clear', reason='No comparable reference pose')
            continue
        unique = entry['block'] == 'own' and found[0] < EXACT_IOU
        if found[0] < WEAK_IOU or unique:
            # A pose the reference lacks entirely (unique skill or emote art):
            # a neutral frame is the least misleading substitute.
            wide = (b[2]-b[0]) > 1.2*(b[3]-b[1])
            pool = lying if wide and lying else neutral
            calm = nearest(crop, pool, shortlist=len(pool))
            if calm:
                record(entry, calm, 'fallback')
                entry.update(weak=True, reason='No comparable reference pose; neutral %s frame' %
                             ('lying' if pool is lying else 'standing'))
                continue
        record(entry, found, 'exact' if found[0] >= EXACT_IOU else 'fallback')
    origins = anchor_idle_frames(donor, body_id, entries)
    return dict(schema=SCHEMA, mode='pose-template', body_id=body_id, common_resource=common_id,
                own_canvas_origin=origins,
                donor_sha256=sha(donor), common_sha256=sha(common),
                reference_poses=len(sprites), entries=entries, skipped=skipped,
                counts=dict(collections.Counter(e['match'] for e in entries)),
                interpretation='Exact entries are pixel alignments of reference art; fallback/clear entries '
                               'are rule-based substitutions. Native action acceptance is separate.')


def anchor_idle_frames(donor, body_id, entries):
    """Give every donor-specific idle frame one shared canvas position.

    RPG idle frames of a set share a canvas that sits at a fixed place in
    character space. The donor's own keys say where each cell is drawn, so the
    best-matched frames fix that place and the others follow it exactly,
    instead of each frame drifting with its own silhouette match. Neutral
    substitutes for unique art stand on the front idle position too.
    """
    import d2_anm_cells
    cell = d2_anm_cells.cell_origins(d2_anm_cells.own_tables(donor, body_id))
    origins = {}

    def canvas(e):
        offset = e['canvas_offset']
        return (cell[e['rectangle_index']][0]+offset[0], cell[e['rectangle_index']][1]+offset[1])

    def move(e, origin):
        wanted = (origin[0]-cell[e['rectangle_index']][0], origin[1]-cell[e['rectangle_index']][1])
        dx, dy = wanted[0]-e['canvas_offset'][0], wanted[1]-e['canvas_offset'][1]
        if dx or dy:
            e['pivot'] = [e['pivot'][0]+dx, e['pivot'][1]+dy]
            e['canvas_offset'] = list(wanted)
            b = e['reference_bounds']
            e['reference_bounds'] = [b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy]
        e['character_space'] = True
    own = [e for e in entries if e['block'] == 'own' and e['match'] != 'clear' and e['rectangle_index'] in cell]
    for tags, name in sorted(IDLE.items()):
        frames = [e for e in own if tuple(e['animations']) == tags and e['pose'].startswith(name+'/') and
                  e['quarter_turns'] == 0]
        if not frames:
            continue
        best = max(e['iou'] for e in frames)
        trusted = [e for e in frames if e['iou'] >= min(EXACT_IOU, best)]
        size, flip = trusted[0]['reference_size'], trusted[0]['flip_x']
        votes = collections.Counter(canvas(e) for e in trusted if e['reference_size'] == size and e['flip_x'] == flip)
        origin = votes.most_common(1)[0][0]
        origins[name] = dict(origin=list(origin), reference_size=size, flip_x=flip, frames=len(frames))
        for e in frames:
            # Pixel-matched frames keep their own (sometimes bobbing) position.
            if e['reference_size'] == size and e['flip_x'] == flip and e['iou'] < EXACT_IOU:
                move(e, origin)
    front = origins.get('wait_front')
    if front:
        for e in own:
            if e.get('weak') and e['pose'] == 'wait_front/wait01' and e['reference_size'] == front['reference_size'] \
                    and e['flip_x'] == front['flip_x']:
                move(e, front['origin'])
    return origins


def merge_common(templates):
    """Shared-rectangle knowledge from several donors.

    Common rectangles are drawn by shared animations, so the pose proven by
    one donor's reference art applies to every donor using them.
    Donors vote on the pose. Placement inside a rectangle differs by a few
    pixels between characters, so pivots here are informational only; each
    donor template measures its own placement.
    """
    votes = collections.defaultdict(list)
    for template in templates:
        if template.get('schema') != SCHEMA or template.get('mode') != 'pose-template':
            raise ValueError('Expected pose templates')
        if template['common_sha256'] != templates[0]['common_sha256']:
            raise ValueError('Templates use different shared animation members')
        for e in template['entries']:
            if e['block'] == 'common':
                votes[e['rectangle_index']].append((template['body_id'], e))
    entries, disagreements = [], {}
    for index in sorted(votes):
        groups = collections.defaultdict(list)
        for body, e in votes[index]:
            key = ('clear',) if e['match'] == 'clear' else (e['pose'], e['flip_x'], e['quarter_turns'])
            groups[key].append((body, e))
        ranked = sorted(groups.items(), key=lambda g: (g[0] != ('clear',), len(g[1]),
                                                       max(e.get('iou', 0) for _, e in g[1])), reverse=True)
        key, members = ranked[0]
        first = members[0][1]
        kept = dict(block='common', rectangle_index=index, size=first['destination'][2:],
                    layers=first['layers'], animation_count=first['animation_count'],
                    support=len(members), evidence_bodies=[body for body, _ in members])
        if key == ('clear',):
            kept.update(match='clear')
        else:
            xs = sorted(e['pivot'][0] for _, e in members)
            ys = sorted(e['pivot'][1] for _, e in members)
            best = max(e['iou'] for _, e in members)
            kept.update(match='exact' if best >= EXACT_IOU else 'fallback', pose=key[0], flip_x=key[1],
                        quarter_turns=key[2], pivot=[xs[len(xs)//2], ys[len(ys)//2]], iou=best,
                        pivot_spread=[xs[-1]-xs[0], ys[-1]-ys[0]])
        if len(ranked) > 1:
            disagreements[str(index)] = [dict(choice=list(k), bodies=[b for b, _ in m],
                                              iou=max(e.get('iou', 0) for _, e in m)) for k, m in ranked]
        entries.append(kept)
    return dict(schema=SCHEMA, mode='common-pose-template', common_resource=templates[0]['common_resource'],
                common_sha256=templates[0]['common_sha256'], donors=[t['body_id'] for t in templates],
                entries=entries, disagreements=disagreements,
                counts=dict(collections.Counter(e['match'] for e in entries)))


def review_sheet(donor, template, reference, target):
    """Donor crop beside the reference pose placed by the template."""
    from PIL import ImageDraw
    pages = {i: page_image(p) for i, p in pages_of(donor).items()}
    sprites = catalog(reference) if reference else {}
    entries = template['entries']
    cols, cw, ch = 5, 300, 214
    canvas = Image.new('RGBA', (cols*cw, ch*((len(entries)+cols-1)//cols)), (30, 30, 34, 255))
    draw = ImageDraw.Draw(canvas)
    colors = dict(exact=(120, 220, 140), fallback=(240, 200, 90), clear=(240, 120, 120))
    for n, e in enumerate(entries):
        x, y, w, h = e['destination']
        ox, oy = (n % cols)*cw, (n//cols)*ch
        crop = pages[e['page']].crop((x, y, x+w, y+h))
        scale = min(1.0, 140/w, 176/h)
        size = (max(1, round(w*scale)), max(1, round(h*scale)))
        canvas.alpha_composite(crop.resize(size, Image.Resampling.NEAREST), (ox+4, oy+4))
        if e['match'] != 'clear' and e['pose'] in sprites:
            image, pivot = orient(sprites[e['pose']]['image'], sprites[e['pose']]['pivot'], e['flip_x'], e['quarter_turns'])
            layer = Image.new('RGBA', (w, h))
            px, py = round(e['pivot'][0]-pivot[0]), round(e['pivot'][1]-pivot[1])
            layer.paste(image, (px, py))
            canvas.alpha_composite(layer.resize(size, Image.Resampling.NEAREST), (ox+152, oy+4))
        label = '%s %d p%d %s' % (e['block'][0], e['rectangle_index'], e['page'], e['match'])
        draw.text((ox+4, oy+182), label, fill=colors[e['match']])
        draw.text((ox+4, oy+196), '%s%s%s %s' % (e.get('pose', '-'), ' flip' if e.get('flip_x') else '',
                                                 ' r%d' % e['quarter_turns'] if e.get('quarter_turns') else '',
                                                 e.get('iou', '')), fill='white')
    canvas.convert('RGB').save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='Template for one D2 donor from the RPG version of that character')
    build.add_argument('--archive', type=Path, required=True)
    build.add_argument('--body', type=int, required=True, help='D2 body resource ID, e.g. 30 for Etna')
    build.add_argument('--common-member', default='anm00001.lzs')
    build.add_argument('--reference', type=Path, required=True,
                       help='Extracted RPG assets of the same character as the D2 donor')
    build.add_argument('--common-template', type=Path, help='Merged shared-rectangle pose votes from other donors')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--review', type=Path, help='Optional new PNG comparing donor crops and placed poses')
    merge = sub.add_parser('merge', help='Combine shared-rectangle evidence from several donor templates')
    merge.add_argument('templates', type=Path, nargs='+')
    merge.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = _no_symlinks(args.output.absolute())
    if output.exists():
        parser.error('Output file must be new')
    if args.command == 'merge':
        result = merge_common([json.loads(read(p)) for p in args.templates])
    else:
        if not 1 <= args.body <= 32767:
            parser.error('Body ID out of range')
        member = 'anm%05d.lzs' % args.body
        validate_name(member)
        validate_name(args.common_member)
        if args.review and _no_symlinks(args.review.absolute()).exists():
            parser.error('Review image must be new')
        donor = archive_member(args.archive, member)
        votes = json.loads(read(args.common_template)) if args.common_template else None
        result = build_template(donor, archive_member(args.archive, args.common_member), args.reference, args.body,
                                votes=votes)
        result.update(member=member, common_member=args.common_member)
        if args.review:
            review_sheet(donor, result, args.reference, args.review)
    with output.open('x') as f:
        f.write(json.dumps(result, indent=1)+'\n')
    print(json.dumps(dict(output=str(output), counts=result['counts'],
                          skipped=len(result.get('skipped', [])), disagreements=len(result.get('disagreements', {})))))


if __name__ == '__main__':
    main()
