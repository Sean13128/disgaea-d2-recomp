#!/usr/bin/env python3
"""Enlarge a costume's donor-specific atlas cells so larger artwork fits.

A body resource carries its own animation block (idle and unique actions).
Because every costume is a separate resource, that block's rectangle table
can be edited per costume without touching shared animations:

* cells grow by the same margin on opposite sides and their pivot entry moves
  by that margin, so the drawn position is unchanged whether the engine
  positions a cell by its stored pivot or by its centre;
* keys of separately animated cloth/hair pieces that the RPG frame already
  contains are pointed at the empty rectangle 0, freeing their atlas space;
* grown cells are re-packed into free atlas space of the same page.

Table sizes, offsets, tracks, timing and every shared (common) rectangle are
untouched. Rectangles drawn by shared animations cannot be enlarged here.
"""
import collections
import struct

from PIL import Image

from d2_anm import parse_anm

PLAIN = (0, 100, 100, 0, 0)  # transform words 2,4,5,6,7: no scale/rotation/extra


def own_tables(raw, body_id):
    meta = parse_anm(raw)
    blocks = [b for b in meta['blocks'] if b['resource_id'] == body_id]
    if len(blocks) != 1:
        raise ValueError('Missing or ambiguous donor block')
    t = blocks[0]['tables']

    def rows(name, fmt):
        size = struct.calcsize(fmt)
        if size != t[name]['stride']:
            raise ValueError('Unexpected table stride: '+name)
        return [struct.unpack_from(fmt, raw, t[name]['offset']+i*size) for i in range(t[name]['count'])]
    return dict(offsets={name: t[name]['offset'] for name in t},
                keys=rows('keys', '>6H'), rects=rows('rectangle_candidates', '>9H'),
                transforms=rows('transform_candidates', '>8h'), anchors=rows('anchor_candidates', '>2h'))


def _free(occupied, x, y, w, h):
    if x < 0 or y < 0 or x+w > occupied.width or y+h > occupied.height:
        return False
    return occupied.crop((x, y, x+w, y+h)).getbbox() is None


def _place(occupied, w, h, preferred):
    """Preferred spot first, then the first free window scanning rows."""
    for x, y in preferred:
        if _free(occupied, x, y, w, h):
            return x, y
    for y in range(0, occupied.height-h+1, 4):
        for x in range(0, occupied.width-w+1, 4):
            if _free(occupied, x, y, w, h):
                return x, y
    return None


def cell_origins(tables):
    """Rectangle index -> top-left of the cell in character space.

    A sprite key draws its rectangle with the pivot entry of its transform at
    the transform position, so the cell's top-left is position minus pivot.
    Only rectangles with one unscaled, unrotated placement are reported.
    """
    seen = collections.defaultdict(set)
    for key in tables['keys']:
        if key[1] != 0 or not key[2] or key[3] >= len(tables['transforms']):
            continue
        transform = tables['transforms'][key[3]]
        if not 0 <= transform[3] < len(tables['anchors']):
            continue
        plain = (transform[2], transform[4], transform[5], transform[6], transform[7]) == PLAIN
        anchor = tables['anchors'][transform[3]]
        seen[key[2]].add((transform[0]-anchor[0], transform[1]-anchor[1]) if plain else None)
    return {rect: next(iter(values)) for rect, values in seen.items() if len(values) == 1 and None not in values}


def _pack(size, reserved, items):
    """First-fit placement of (key, w, h, preferred) items; None when one fails."""
    occupied = Image.new('L', size)
    for box in reserved:
        occupied.paste(255, box)
    placed = {}
    for key, w, h, preferred in sorted(items, key=lambda i: (-i[2], -i[1])):
        spot = _place(occupied, w, h, preferred)
        if spot is None:
            return None
        occupied.paste(255, (spot[0], spot[1], spot[0]+w, spot[1]+h))
        placed[key] = spot
    return placed


def plan(donor, body_id, entries, needs, common_rects, page_sizes, border=0, symmetric=False, content=None):
    """Decide new own-block cells.

    entries: template entries; needs: {rectangle_index: (left, top, right, bottom)}
    overflow in pixels of the costume art beyond the present own-block cell
    (callers include any transparent rim they want kept inside the cell);
    content: optional {rectangle_index: hashable} identifying identical cell
    pictures, which then share one atlas cell. symmetric grows opposite sides
    equally so placement is also correct if the engine used cell centres.
    Returns None when nothing has to change. Pages that cannot hold the
    enlarged cells are retried with smaller margins, then left alone.
    """
    t = own_tables(donor, body_id)
    own = {e['rectangle_index']: e for e in entries if e['block'] == 'own'}
    content = content or {}
    sprite_keys = collections.defaultdict(list)   # rect -> key indices drawing it as a sprite
    other_use = set()
    for n, key in enumerate(t['keys']):
        if key[1] & 0xff00:
            continue
        if key[1] == 0:
            sprite_keys[key[2]].append(n)
        else:
            other_use.add(key[2])
    anchors_of = collections.defaultdict(set)
    locked_anchor = set()
    for rect, keys in sprite_keys.items():
        for n in keys:
            transform = t['transforms'][t['keys'][n][3]] if t['keys'][n][3] < len(t['transforms']) else None
            if transform is None or not 0 <= transform[3] < len(t['anchors']):
                other_use.add(rect)
                continue
            anchors_of[rect].add(transform[3])
            if (transform[2], transform[4], transform[5], transform[6], transform[7]) != PLAIN:
                locked_anchor.add(transform[3])
    for n, key in enumerate(t['keys']):
        if not key[1] & 0xff00 and key[1] != 0 and key[3] < len(t['transforms']):
            locked_anchor.add(t['transforms'][key[3]][3])  # attachment transforms keep their pivots
    # Group rectangles that share a pivot entry: they must move together.
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for rect, anchors in anchors_of.items():
        for anchor in anchors:
            parent[find(('r', rect))] = find(('a', anchor))
    groups = collections.defaultdict(lambda: dict(rects=set(), anchors=set()))
    for rect, anchors in anchors_of.items():
        g = groups[find(('r', rect))]
        g['rects'].add(rect)
        g['anchors'].update(anchors)
    growing, skipped = [], []
    for g in groups.values():
        if not any(r in needs for r in g['rects']):
            continue
        reason = None
        if g['anchors'] & locked_anchor or 0 in g['anchors']:
            reason = 'Pivot entry is shared with a scaled, rotated or attachment transform'
        elif g['rects'] & other_use:
            reason = 'Rectangle is also used by a non-sprite key'
        elif any(r not in own or own[r]['match'] == 'clear' for r in g['rects']):
            reason = 'Group includes a rectangle without costume art'
        if reason:
            skipped.append(dict(rectangles=sorted(g['rects']), reason=reason))
        else:
            growing.append(g)
    if not growing:
        return dict(moves={}, hidden=[], skipped=skipped) if skipped else None
    hidden = sorted(r for r, e in own.items() if e['match'] == 'clear' and r not in other_use and r in sprite_keys)
    result = dict(moves={}, hidden=hidden, skipped=skipped, anchor_edits={}, key_edits=[], tables=t,
                  symmetric=symmetric, shared_cells=0)
    by_page = collections.defaultdict(list)
    for g in growing:
        pages = {own[r]['page'] for r in g['rects']}
        if len(pages) != 1:
            skipped.append(dict(rectangles=sorted(g['rects']), reason='Pivot group spans several pages'))
            continue
        by_page[pages.pop()].append(g)
    for page, page_groups in by_page.items():
        width, height = page_sizes[page]
        moving = set().union(*(g['rects'] for g in page_groups))
        reserved = []
        for words in common_rects:  # shared animations may draw these; never reuse them
            if words[0] == page and words[6] and words[7] and words[4]+words[6] <= width and words[5]+words[7] <= height:
                reserved.append((words[4], words[5], words[4]+words[6], words[5]+words[7]))
        for index, words in enumerate(t['rects']):
            if words[0] != page or not words[6] or not words[7] or index in moving or index in hidden:
                continue
            if words[4]+words[6] <= width and words[5]+words[7] <= height:
                reserved.append((words[4], words[5], words[4]+words[6], words[5]+words[7]))
        chosen = None
        for factor in (1.0, 0.8, 0.6, 0.45, 0.3, 0.15):
            def pad(value):
                return int(-(-value*factor//1))+border if value else 0
            items, cells_of, margins = [], {}, {}
            for number, g in enumerate(page_groups):
                wanted = [needs[r] for r in g['rects'] if r in needs]
                left, top = pad(max(n[0] for n in wanted)), pad(max(n[1] for n in wanted))
                right, bottom = max(n[2] for n in wanted), max(n[3] for n in wanted)
                if symmetric:
                    left = right = max(left, pad(right))
                    top = bottom = max(top, pad(bottom))
                for r in g['rects']:
                    x, y, w, h = own[r]['destination']
                    need = needs.get(r, (0, 0, 0, 0))
                    grow_r = right if symmetric else pad(need[2])
                    grow_b = bottom if symmetric else pad(need[3])
                    size = (w+left+grow_r, h+top+grow_b)
                    key = (number, content[r], size) if r in content else (number, 'rect', r)
                    if key not in cells_of:
                        items.append((key, size[0], size[1], [(x-left, y-top), (x, y)]))
                    cells_of.setdefault(key, []).append(r)
                    margins[r] = (left, top, size)
            placed = _pack((width, height), reserved, items)
            if placed is not None:
                chosen = (factor, placed, cells_of, margins)
                break
        if chosen is None:
            skipped.append(dict(rectangles=sorted(moving), page=page, reason='No free atlas space for enlarged cells'))
            continue
        factor, placed, cells_of, margins = chosen
        if factor < 1:
            skipped.append(dict(rectangles=sorted(moving), page=page, margin_factor=factor,
                                reason='Atlas space allows only part of the needed enlargement; the rest is clipped'))
        for key, rects in cells_of.items():
            result['shared_cells'] += len(rects)-1
            for r in rects:
                left, top, size = margins[r]
                result['moves'][r] = dict(destination=[placed[key][0], placed[key][1], size[0], size[1]],
                                          margin=[left, top])
        for g in page_groups:
            left, top, _ = margins[next(iter(g['rects']))]
            for anchor in g['anchors']:
                result['anchor_edits'][anchor] = [left, top]
    if result['moves']:
        # Hide only when something was actually re-packed into the freed space.
        for r in hidden:
            result['key_edits'].extend(sprite_keys[r])
    else:
        result['hidden'] = []
    return result


def apply(donor, body_id, growth):
    """Write the planned rectangle, pivot and key edits; everything else stays."""
    t = growth['tables']
    out = bytearray(donor)
    allowed = set()
    for r, move in growth['moves'].items():
        offset = t['offsets']['rectangle_candidates']+r*18+8
        struct.pack_into('>4H', out, offset, *move['destination'])
        allowed.update(range(offset, offset+8))
    for anchor, (mx, my) in growth['anchor_edits'].items():
        offset = t['offsets']['anchor_candidates']+anchor*4
        ax, ay = t['anchors'][anchor]
        struct.pack_into('>2h', out, offset, ax+mx, ay+my)
        allowed.update(range(offset, offset+4))
    for n in growth['key_edits']:
        offset = t['offsets']['keys']+n*12+4
        struct.pack_into('>H', out, offset, 0)
        allowed.update(range(offset, offset+2))
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(donor, out))):
        raise ValueError('Unexpected metadata change')
    after = own_tables(bytes(out), body_id)
    if len(after['keys']) != len(t['keys']) or len(after['rects']) != len(t['rects']):
        raise ValueError('Table geometry changed')
    return bytes(out)
