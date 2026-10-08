#!/usr/bin/env python3
"""Inspect D2 ANM resource blocks without guessing animation semantics.

Block/table geometry is empirical, checked against exact counts and bounds.
Rectangle candidates expose coordinates for mapping work, not decoded frames.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from d2_character_export import unlzs, anm_pages


TABLES = ('tags', 'tracks', 'keys', 'palette_refs', 'sheet_refs',
          'rectangle_candidates', 'transform_candidates', 'anchor_candidates',
          'tint_candidates', 'extra_words')
STRIDES = (4,16,12,8,12,18,16,4,20,4)
COUNT_INDICES = (1,2,3,4,5,6,7,8,9,10)


def parse_anm(data):
    if data.startswith(b'dat\0'):
        data = unlzs(data)
    if len(data) < 32:
        raise ValueError('Truncated ANM header')
    meta_end, payload_bytes, textures, palettes, block_count = struct.unpack_from('>5I', data)
    payload_start = meta_end+16
    table_start = payload_start-(textures+palettes)*16
    if not 0 < block_count <= 4096 or table_start < 32 or payload_start+payload_bytes != len(data):
        raise ValueError('Invalid ANM block/payload geometry')
    if textures > 4096 or palettes > 4096 or not textures or not palettes:
        raise ValueError('Invalid texture/palette counts')
    result = dict(sha256=hashlib.sha256(data).hexdigest(), expanded_bytes=len(data),
                  payload_start=payload_start, texture_table_start=table_start,
                  textures=textures, palettes=palettes, blocks=[],
                  interpretation='Empirical block/table geometry; track/key/event semantics unresolved')
    cursor = 32
    for block_index in range(block_count):
        if cursor+68 > table_start:
            raise ValueError('Truncated resource block header')
        length = struct.unpack_from('>I',data,cursor)[0]
        values = struct.unpack_from('>12H',data,cursor+4)
        offsets = struct.unpack_from('>10I',data,cursor+28)
        if length < 68 or cursor+length > table_start:
            raise ValueError('Resource block exceeds metadata bounds')
        block = dict(index=block_index, offset=cursor, bytes=length, resource_id=values[0],
                     header_u16=list(values), unknown_header_u16=[values[9],values[11]], tables={})
        for i,(name,stride,count_index,off) in enumerate(zip(TABLES,STRIDES,COUNT_INDICES,offsets)):
            count = values[count_index]
            size = count*stride
            if off < 68 or off+size > length or (i+1 < len(offsets) and off+size > offsets[i+1]):
                raise ValueError('Resource table count/stride/offset mismatch: '+name)
            raw = data[cursor+off:cursor+off+size]
            info = dict(offset=cursor+off, relative_offset=off, count=count, stride=stride,
                        sha256=hashlib.sha256(raw).hexdigest())
            if name == 'rectangle_candidates':
                info['records'] = []
                for row in range(count):
                    words = struct.unpack_from('>9H',raw,row*18)
                    info['records'].append(dict(index=row, offset=cursor+off+row*18,
                        words=list(words), page_candidate=words[0], x=words[4], y=words[5],
                        width=words[6], height=words[7], flags_candidate=words[8],
                        interpretation='Atlas rectangle geometry candidate; page binding and flag semantics require native consumer validation'))
            elif name == 'tags':
                info['records'] = [list(struct.unpack_from('>2H',raw,row*4)) for row in range(count)]
            block['tables'][name] = info
        result['blocks'].append(block)
        cursor += length
    if cursor != table_start:
        raise ValueError('Resource block lengths do not end at texture headers')
    # Existing bounded page reader validates texture/palette offsets separately.
    pages = anm_pages(data, include_rgba=False, palette_indices=[0])
    result['page_pairs'] = textures*palettes
    result['inspected_page_pairs'] = len(pages)
    result['inspected_palettes'] = [0]
    result['page_sizes'] = [dict(texture=p['texture'],width=p['width'],height=p['height'])
                            for p in pages if p['palette']==0]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = parse_anm(args.source.read_bytes())
    text = json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as f:
            f.write(text)
    else:
        print(text,end='')
