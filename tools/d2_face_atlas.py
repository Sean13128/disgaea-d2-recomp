#!/usr/bin/env python3
"""Inspect compressed face TXFs or append one reviewed RPG face row offline.

This preserves donor cells. Appended rows require native lookup/routing support;
the fixed retail face tables do not discover them automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

from d2_asset_pack import compress_lzs
from d2_character_export import unlzs, _no_symlinks


def decode(packed):
    if len(packed)>64*1024**2 or packed[:4]!=b'txf\0':
        raise ValueError('Expected a bounded compressed txf stream')
    # Guest001840E0 receives file+4; the outer magic is outside its input.
    raw=unlzs(b'dat\0'+packed[4:])
    if len(raw)<16 or raw[0]!=0:
        raise ValueError('Only observed TXF format0 ARGB8888 is supported')
    width,height,depth=struct.unpack_from('>HHH',raw,4)
    size=struct.unpack_from('>I',raw,12)[0]
    if not 0<width<=4096 or not 0<height<=4096 or depth!=1 or size!=width*height*4 or len(raw)!=16+size:
        raise ValueError('TXF dimensions/depth/payload mismatch')
    return raw,width,height


def pack(raw):
    raw=bytes(raw)
    result=b'txf\0'+compress_lzs(raw)[4:]
    if decode(result)[0]!=raw:raise ValueError('TXF compression roundtrip mismatch')
    return result


def image(raw,width,height):
    from PIL import Image
    return Image.frombytes('RGBA',(width,height),raw[16:],'raw','ARGB')


def mark_row(packed,row,rgb=(255,0,255)):
    raw,width,height=decode(packed)
    if width!=384 or height%96 or type(row) is not int or not 0<=row<height//96:
        raise ValueError('Expected a valid row in a four-column96px face atlas')
    if not isinstance(rgb,(list,tuple)) or len(rgb)!=3 or any(type(c) is not int or not 0<=c<=255 for c in rgb):
        raise ValueError('Expected three RGB bytes')
    start=16+row*96*width*4;end=start+96*width*4
    output=bytearray(raw)
    for offset in range(start,end,4):output[offset+1:offset+4]=bytes(rgb)
    assert output[:start]==raw[:start] and output[end:]==raw[end:] and output[start:end:4]==raw[start:end:4]
    expanded=bytes(output)
    return expanded,pack(expanded),dict(row=row,rgb=list(rgb),width=width,height=height,
        source_sha256=hashlib.sha256(raw).hexdigest(),marked_sha256=hashlib.sha256(expanded).hexdigest(),
        preserved='TXF headers, all other rows and every alpha byte',visible_consumer_validated=False)


def append_row(packed,pose):
    from PIL import Image
    raw,width,height=decode(packed)
    if width!=384 or height%96 or height+96>4096:
        raise ValueError('Expected a four-column96px atlas with room for another row')
    if pose.mode!='RGBA' or not 0<pose.width<=4096 or not 0<pose.height<=4096:
        raise ValueError('Expected a bounded RGBA source pose')
    fitted=pose.copy();fitted.thumbnail((96,96),Image.Resampling.LANCZOS)
    row=Image.new('RGBA',(384,96))
    for column in range(4):
        row.paste(fitted,(column*96+(96-fitted.width)//2,(96-fitted.height)//2))
    header=bytearray(raw[:16]);struct.pack_into('>H',header,6,height+96)
    struct.pack_into('>I',header,12,width*(height+96)*4)
    rgba=row.tobytes();argb=bytearray(len(rgba))
    argb[0::4]=rgba[3::4];argb[1::4]=rgba[0::4]
    argb[2::4]=rgba[1::4];argb[3::4]=rgba[2::4]
    expanded=bytes(header)+raw[16:]+argb
    result=pack(expanded)
    return expanded,result,dict(row_index=height//96,cell_size=96,columns=4,
        donor_pixel_sha256=hashlib.sha256(raw[16:]).hexdigest(),
        preserved_donor_pixels=expanded[16:16+len(raw)-16]==raw[16:],
        source_pose_policy='One reviewed pose reused across the four color-variant cells',
        runtime_routing_validated=False,
        limits='Native unique1 lookup scans40 entries. Appended rows need scoped routing; default4096px texture bound permits only42 rows here.')


def allocate_cell(packed,pose,occupied=()):
    """Keep retail coordinates; allocate costumes in extra96px columns.

    UV routing can select these cells without extending the fixed retail ID
    table. This permits many costumes within the existing bounded texture.
    """
    from PIL import Image
    raw,width,height=decode(packed)
    if width<384 or width%96 or height%96 or pose.mode!='RGBA' or not 0<pose.width<=4096 or not 0<pose.height<=4096:
        raise ValueError('Expected a bounded96px unique face atlas and RGBA pose')
    if not isinstance(occupied,(list,tuple)) or len(occupied)>4096:
        raise ValueError('Expected a bounded occupied-cell list')
    occupied=list(occupied);used=set()
    for cell in occupied:
        if not isinstance(cell,(list,tuple)) or len(cell)!=2 or any(type(v) is not int for v in cell):
            raise ValueError('Invalid occupied face cell')
        x,y=cell
        if x<384 or x%96 or y<0 or y%96 or x+96>width or y+96>height or (x,y) in used:
            raise ValueError('Occupied face cell outside appended columns or duplicated')
        used.add((x,y))
    cell=next(((x,y) for x in range(384,width,96) for y in range(0,height,96) if (x,y) not in used),None)
    new_width=width
    if cell is None:
        if width+96>4096:raise ValueError('Face atlas column capacity exhausted')
        new_width+=96;cell=(width,0)
    pixels=bytearray(new_width*height*4)
    for row in range(height):
        begin=row*new_width*4;pixels[begin:begin+width*4]=raw[16+row*width*4:16+(row+1)*width*4]
    x,y=cell
    for row in range(y,y+96):
        begin=(row*new_width+x)*4
        if any(pixels[begin:begin+96*4]):raise ValueError('Unregistered artwork occupies the requested face cell')
    fitted=pose.copy();fitted.thumbnail((96,96),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(96,96));canvas.paste(fitted,((96-fitted.width)//2,(96-fitted.height)//2))
    rgba=canvas.tobytes();argb=bytearray(len(rgba))
    for dst,src in [(0,3),(1,0),(2,1),(3,2)]:argb[dst::4]=rgba[src::4]
    for row in range(96):
        begin=((y+row)*new_width+x)*4;pixels[begin:begin+96*4]=argb[row*96*4:(row+1)*96*4]
    # Original pixels, including previous costume cells, remain at exact XY.
    preserved=all(pixels[row*new_width*4:row*new_width*4+width*4]==raw[16+row*width*4:16+(row+1)*width*4] for row in range(height) if not y<=row<y+96)
    for row in range(y,y+96):
        for left,right in [(0,min(x,width)),(min(x+96,width),width)]:
            if pixels[(row*new_width+left)*4:(row*new_width+right)*4]!=raw[16+(row*width+left)*4:16+(row*width+right)*4]:preserved=False
    if not preserved:raise ValueError('Unrelated face pixels changed')
    header=bytearray(raw[:16]);struct.pack_into('>H',header,4,new_width)
    struct.pack_into('>I',header,12,len(pixels));expanded=bytes(header)+pixels
    return expanded,pack(expanded),dict(face_x=x,face_y=y,face_width=new_width,face_height=height,
        preserved_existing_cells=True,source_pose_policy='One reviewed pose for this cell; color variants reuse it',
        runtime_routing_validated=False,
        limits='Requires scoped costume UV routing. Original four columns and fixed retail lookup remain intact; dimensions bounded4096px.')


def build(donor,output,source=None,crop=None,allocate=False,occupied=()):
    donor=_no_symlinks(Path(donor).absolute());output=_no_symlinks(Path(output).absolute())
    if output.exists() or not output.parent.is_dir() or output in donor.parents:
        raise ValueError('Output must be a new directory outside the donor path')
    packed=donor.read_bytes();raw,width,height=decode(packed)
    report=dict(donor=str(donor),donor_sha256=hashlib.sha256(packed).hexdigest(),
                format='compressed txf / TXF0 ARGB8888',width=width,height=height,
                native_execution_validated=False)
    if source is not None:
        from PIL import Image
        source=_no_symlinks(Path(source).absolute())
        if output in source.parents:raise ValueError('Output overlaps source')
        source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
        with Image.open(source) as im:
            if im.width*im.height>16*1024**2:raise ValueError('Source image exceeds16M pixels')
            if crop is None or len(crop)!=4 or any(type(c) is not int for c in crop) or not 0<=crop[0]<crop[2]<=im.width or not 0<=crop[1]<crop[3]<=im.height:
                raise ValueError('Expected an explicit bounded source crop')
            pose=im.convert('RGBA').crop(crop)
        raw,packed,addition=allocate_cell(packed,pose,occupied) if allocate else append_row(packed,pose)
        width,height=struct.unpack_from('>HH',raw,4);report.update(addition)
        report.update(source=str(source),source_sha256=source_sha,crop=list(crop),output_width=width,output_height=height)
        if allocate:report['occupied_cells']=[list(cell) for cell in occupied]
    if donor.read_bytes()!=packed and source is None:
        raise ValueError('Donor changed during inspection')
    if hashlib.sha256(donor.read_bytes()).hexdigest()!=report['donor_sha256']:
        raise ValueError('Donor changed during conversion')
    if source is not None and hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha:
        raise ValueError('Source image changed during conversion')
    if shutil.disk_usage(output.parent).free<len(raw)*4+64*1024**2:
        raise ValueError('Insufficient artifact space')
    output.mkdir()
    try:
        (output/'expanded.txf').write_bytes(raw);(output/'atlas.lzs').write_bytes(packed)
        image(raw,width,height).save(output/'atlas.png')
        if source is not None:
            rect=(addition['face_x'],addition['face_y'],addition['face_x']+96,addition['face_y']+96) if allocate else (0,height-96,width,height)
            image(raw,width,height).crop(rect).save(output/('allocated-cell.png' if allocate else 'appended-row.png'))
        report.update(expanded_sha256=hashlib.sha256(raw).hexdigest(),packed_sha256=hashlib.sha256(packed).hexdigest())
        (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    except BaseException:
        shutil.rmtree(output);raise
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--crop',type=int,nargs=4)
    parser.add_argument('--allocate-cell',action='store_true',help='Use extra columns for scalable costume UV routing')
    parser.add_argument('--occupied-cells',type=Path,help='JSON list of previously allocated [x,y] cells; only with --allocate-cell')
    args=parser.parse_args()
    if (args.source is None)!=(args.crop is None):parser.error('--source and --crop must be supplied together')
    if args.allocate_cell and args.source is None:parser.error('--allocate-cell requires a source crop')
    if args.occupied_cells and not args.allocate_cell:parser.error('--occupied-cells requires --allocate-cell')
    occupied=[]
    if args.occupied_cells:
        path=_no_symlinks(args.occupied_cells.absolute())
        if path.stat().st_size>1024*1024:parser.error('Occupied-cell JSON exceeds1MiB')
        occupied=json.loads(path.read_text())
        if not isinstance(occupied,list) or len(occupied)>4096:parser.error('Expected a bounded occupied-cell list')
    print(json.dumps(build(args.donor,args.output,args.source,args.crop,args.allocate_cell,occupied),indent=2))
