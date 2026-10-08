#!/usr/bin/env python3
"""Author a coordinated source-color palette for a mapped RPG appearance.

Re-encode every donor texture against a palette trained on the final RGBA
atlases. All native recolor slots use the same authored colors. Unmapped art
is retained from donor palette zero; this does not complete missing poses.
"""
import argparse
import json
from pathlib import Path
import struct

from PIL import Image, __version__ as PILLOW_VERSION

from d2_anm import parse_anm
from d2_asset_pack import compress_lzs, validate_name
from d2_character_export import _no_symlinks, anm_pages, indexed_png, unlzs
from d2_rpg_map import (archive_member, compose, page_image, pages_of,
                        quantize, read, render_sprite, sha)


def author(donor, mappings):
    # Reuse the complete geometry/hash/placement/palette validation first.
    _, _, components = compose(donor, mappings)
    pages = pages_of(donor)
    if sum(p['width']*p['height'] for p in pages.values()) > 16*1024**2:
        raise ValueError('Palette authoring exceeds 16 million texture pixels')
    images = {key: page_image(page) for key, page in pages.items()}
    assigned = {key: bytearray(image.width*image.height) for key, image in images.items()}
    for _, manifest in mappings:
        for entry in manifest['entries']:
            if entry.get('selected') is not True:
                continue
            key = entry['page']
            x, y, w, h = entry['destination']
            patch = render_sprite(entry, pages[key])
            # Source RGBA can differ even when donor quantization hides the
            # difference. Reject that conflict before training the new palette.
            old = images[key].load()
            new = patch.load()
            for row in range(h):
                for col in range(w):
                    index = (y+row)*images[key].width+x+col
                    if assigned[key][index] and old[x+col,y+row] != new[col,row]:
                        raise ValueError('Source RGBA mappings conflict')
                    assigned[key][index] = 1
            images[key].paste(patch, (x,y))
    return encode_images(donor,images,components['mapped_sprites'])


def encode_images(donor,images,mapped_sprites=0):
    """Encode complete RGBA pages while retaining native geometry/metadata."""
    pages=pages_of(donor)
    if set(images)!=set(pages) or any(images[k].mode!='RGBA' or images[k].size!=(p['width'],p['height']) for k,p in pages.items()):
        raise ValueError('Expected one matching RGBA image for every native texture')
    if sum(p['width']*p['height'] for p in pages.values())>16*1024**2:raise ValueError('Palette authoring exceeds16 million pixels')
    # Canonicalize below-threshold alpha before training, matching the existing
    # mapper's explicit transparency policy. Preserve other alpha values.
    for key, image in images.items():
        pixels = bytearray(image.tobytes())
        for offset in range(0,len(pixels),4):
            if pixels[offset+3] < 64:
                pixels[offset:offset+4] = bytes(4)
        images[key] = Image.frombytes('RGBA',image.size,bytes(pixels))
    pairs = anm_pages(donor, include_rgba=False)
    capacity = min(len(p['colors']) for p in pairs)
    if capacity < 2:
        raise ValueError('At least two palette entries required')
    training = Image.new('RGBA',(max(i.width for i in images.values()),
                                  sum(i.height for i in images.values())))
    top = 0
    for image in images.values():
        training.paste(image,(0,top)); top += image.height
    trained = training.quantize(colors=capacity-1,method=Image.Quantize.FASTOCTREE)
    raw_colors = trained.getpalette('RGBA')
    colors = [bytes(4)]
    for offset in range(0,len(raw_colors),4):
        color = bytes(raw_colors[offset:offset+4])
        if color[3] >= 64 and color not in colors:
            colors.append(color)
    if len(colors) < 2:
        raise ValueError('Palette training produced no visible colors')
    colors += [bytes(4)]*(capacity-len(colors))
    output = bytearray(donor)
    allowed = bytearray(len(donor))
    errors = []
    for key, page in pages.items():
        indices, error = quantize(images[key],colors)
        start = page['data_offset']
        if any(allowed[start:start+len(indices)]):
            raise ValueError('Texture payloads overlap; palette authoring requires independent pages')
        output[start:start+len(indices)] = indices
        allowed[start:start+len(indices)] = bytes([1])*len(indices)
        errors.append(dict(page=key,rgb_rmse=error))
    meta = parse_anm(donor)
    palette_offsets = set()
    for pair in pairs:
        header = pair['palette_header_offset']
        start = meta['payload_start']+struct.unpack_from('>I',donor,header+12)[0]
        if start in palette_offsets:
            continue
        count = len(pair['colors'])
        values = colors+[bytes(4)]*(count-len(colors))
        encoded = b''.join(bytes((c[3],c[0],c[1],c[2])) for c in values)
        if any(allowed[start:start+len(encoded)]):
            raise ValueError('Palette payload aliases a texture')
        output[start:start+len(encoded)] = encoded
        allowed[start:start+len(encoded)] = bytes([1])*len(encoded)
        palette_offsets.add(start)
    if output[:meta['payload_start']] != donor[:meta['payload_start']]:
        raise ValueError('Animation metadata or headers changed')
    if any(a!=b and not allowed[i] for i,(a,b) in enumerate(zip(donor,output))):
        raise ValueError('Unexpected changes outside texture/palette payloads')
    decoded = anm_pages(output, include_rgba=False)
    if any(p['colors'][:capacity]!=colors for p in decoded):
        raise ValueError('Authored native palette slots differ')
    packed = compress_lzs(bytes(output))
    if unlzs(packed) != output:
        raise ValueError('Authored palette compression roundtrip failed')
    return bytes(output), packed, dict(mode='source-color-appearance',
        donor_sha256=sha(donor),output_sha256=sha(output),expanded_bytes=len(output),
        packed_bytes=len(packed),mapped_sprites=mapped_sprites,
        palette_entries=capacity,visible_colors=sum(c[3]!=0 for c in colors),
        quantizer=dict(method='Pillow FASTOCTREE plus alpha-weighted nearest palette index',version=PILLOW_VERSION),
        palette_policy='Same authored source colors in every native recolor slot',
        unmapped_policy='Retain donor palette-zero artwork, re-quantized into authored palette',
        alpha_policy='Below64 transparent; other alpha values quantized',page_errors=errors,
        metadata='Byte-identical animation definitions and headers',gameplay_validated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--member',default='anm00030.lzs')
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = _no_symlinks(args.output.absolute())
    if output.exists(): parser.error('Output directory must be new')
    validate_name(args.member)
    config = json.loads(read(args.composition))
    if config.get('schema')!=1 or config.get('mode')!='texture-composition':
        parser.error('Expected schema1 texture-composition')
    mappings = []
    for name in config['mappings']:
        path = Path(name)
        if not path.is_absolute():path = args.composition.absolute().parent/path
        manifest = json.loads(read(path))
        if manifest['member'] != args.member:raise ValueError('Donor member mismatch')
        validate_name(manifest['common_member'])
        mappings.append((archive_member(args.archive,manifest['common_member']),manifest))
    expanded, packed, report = author(archive_member(args.archive,args.member),mappings)
    output.mkdir(parents=True)
    (output/args.member).write_bytes(packed)
    (output/'expanded.bin').write_bytes(expanded)
    retained = dict(config, mappings=[])
    for index,(_,manifest) in enumerate(mappings):
        name = f'mapping-{index}.json'
        (output/name).write_text(json.dumps(manifest,indent=2)+'\n')
        retained['mappings'].append(name)
    (output/'composition.json').write_text(json.dumps(retained,indent=2)+'\n')
    for page in anm_pages(expanded,include_rgba=False):
        (output/f"page-{page['texture']}-palette-{page['palette']}.png").write_bytes(
            indexed_png(page['width'],page['height'],page['indices'],page['colors']))
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
