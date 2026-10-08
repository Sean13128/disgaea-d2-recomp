#!/usr/bin/env python3
"""Read-only local Disgaea D2 asset research exporter (stdlib only)."""
import struct
import zlib


def unlzs(data, limit=64 * 1024 * 1024):
    """NIS dat escape LZ: lifted 1.40 func_001840E0, wrapper +4."""
    if len(data) < 16 or data[:4] != b'dat\0':
        raise ValueError('invalid dat LZS header')
    expected, packed_size, marker = struct.unpack_from('<III', data, 4)
    if expected > limit or packed_size != len(data)-4 or marker > 255:
        raise ValueError('LZS header bounds mismatch')
    out=bytearray(); i=16
    while i < len(data):
        value=data[i]; i+=1
        if value != marker:
            out.append(value)
        else:
            if i >= len(data): raise ValueError('truncated LZS escape')
            distance=data[i]; i+=1
            if distance == marker:
                out.append(marker)
            else:
                if distance > marker: distance-=1
                if i >= len(data): raise ValueError('truncated LZS backreference')
                count=data[i]; i+=1
                if not 0 < distance <= len(out) or len(out)+count > expected:
                    raise ValueError('LZS backreference bounds')
                # Forward-overlap copies repeat the preceding distance-byte
                # pattern. Bounded slices reproduce memcpy's guest byte loop
                # without a Python call per expanded byte.
                pattern=out[-distance:]
                out.extend((pattern*(count//distance+1))[:count])
        if len(out) > expected: raise ValueError('LZS output overrun')
    if len(out) != expected: raise ValueError('LZS output length mismatch')
    return bytes(out)


def _png_chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def indexed_png(width, height, indices, palette):
    """8-bit PNG keeps the exact palette alpha, including partial alpha."""
    if not 0 < width <= 4096 or not 0 < height <= 4096 or len(indices) != width*height or not 1 <= len(palette) <= 256 or (indices and max(indices) >= len(palette)):
        raise ValueError('indexed PNG bounds')
    indices=bytes(indices)
    scan=b''.join(b'\0'+indices[y*width:(y+1)*width] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,3,0,0,0))
            + _png_chunk(b'PLTE',b''.join(c[:3] for c in palette)) + _png_chunk(b'tRNS',bytes(c[3] for c in palette))
            + _png_chunk(b'IDAT',zlib.compress(scan)) + _png_chunk(b'IEND',b''))


def anm_pages(data, include_rgba=True, palette_indices=None):
    """Bounded ANM indexed pages: header counts and relative TXF offsets.

    Layout is empirically validated against local ANM headers; the PPU
    loader delegates ANM conversion to jobs. Do not infer frame composition
    or which palette the runtime chooses from these research pages.
    """
    if len(data) < 32: raise ValueError('truncated ANM header')
    meta_end, payload_size, textures, palettes = struct.unpack_from('>4I',data)
    payload_start=meta_end+16
    table_start=payload_start-(textures+palettes)*16
    if not 1 <= textures <= 4096 or not 1 <= palettes <= 4096 or table_start < 32 or payload_start > len(data) or payload_start+payload_size != len(data):
        raise ValueError('ANM header/count/payload mismatch')
    selected = list(range(palettes)) if palette_indices is None else list(palette_indices)
    if not selected or len(set(selected)) != len(selected) or any(type(p) is not int or not 0 <= p < palettes for p in selected):
        raise ValueError('ANM palette selection bounds')
    if textures*len(selected) > 32768:
        raise ValueError('ANM page-pair limit; select fewer palettes')
    payload=memoryview(data)[payload_start:]
    colors=[]
    for p in range(palettes):
        off=table_start+(textures+p)*16; hdr=data[off:off+16]
        w,h,depth=struct.unpack_from('>HHH',hdr,4); start=struct.unpack_from('>I',hdr,12)[0]
        if hdr[0] != 0 or not 1 <= w*h <= 256 or depth != 1:
            raise NotImplementedError('unverified ANM palette header')
        if start+w*h*4 > len(payload): raise ValueError('ANM palette bounds')
        argb=payload[start:start+w*h*4]
        colors.append([bytes((c[1],c[2],c[3],c[0])) for c in struct.iter_unpack('4B',argb)])
    pages=[]; expanded=0
    for t in range(textures):
        off=table_start+t*16; hdr=data[off:off+16]
        width,height,depth=struct.unpack_from('>HHH',hdr,4); start=struct.unpack_from('>I',hdr,12)[0]
        if not 0 < width <= 4096 or not 0 < height <= 4096 or depth != 1:
            raise ValueError('ANM texture dimensions/depth bounds')
        if hdr[0] == 9:
            if start+width*height > len(payload): raise ValueError('ANM index payload bounds')
            indices=payload[start:start+width*height]
            histogram=collections.Counter(indices)
            if max(histogram,default=0) >= min(map(len,colors)):
                raise ValueError('ANM palette index bounds')
        for p in selected:
            palette=colors[p]
            page:dict=dict(texture=t,palette=p,width=width,height=height,texture_header_offset=off,palette_header_offset=table_start+(textures+p)*16,texture_header_hex=hdr.hex(),data_offset=payload_start+start)
            if hdr[0] != 9:
                page['decoder_status']='unsupported-texture-format-0x%02x' % hdr[0]
            else:
                if max(histogram,default=0) >= len(palette): raise ValueError('ANM palette index bounds')
                page.update(decoder_status='decoded-index8-argb8888',indices=indices,colors=palette,
                            transparent_pixels=sum(histogram[i] for i,c in enumerate(palette) if c[3]==0))
                if include_rgba:
                    expanded+=width*height*4
                    if expanded>256*1024*1024: raise ValueError('ANM RGBA materialization limit; use include_rgba=False')
                    page['rgba']=b''.join(palette[i] for i in indices)
            pages.append(page)
    assert len(pages)==textures*len(selected)
    return pages


def txf_png(data):
    """Decode proven TXF 0x0B to straight-alpha RGBA PNG."""
    if len(data) < 16:
        raise ValueError('truncated TXF header')
    if data[0] != 0x0B:
        raise NotImplementedError('unverified TXF format 0x%02x' % data[0])
    width, height = struct.unpack_from('>HH', data, 4)
    length = struct.unpack_from('>I', data, 12)[0]
    if not 0 < width <= 4096 or not 0 < height <= 4096 or length != width * height * 2 or len(data) != 16 + length:
        raise ValueError('TXF dimensions/payload mismatch')
    rgba = bytearray(width * height * 4)
    transparent = 0
    for i, (value,) in enumerate(struct.iter_unpack('>H', data[16:])):
        alpha = 255 if value & 0x8000 else 0
        transparent += alpha == 0
        rgba[i*4:i*4+4] = bytes(((value >> 10 & 31)*255//31, (value >> 5 & 31)*255//31, (value & 31)*255//31, alpha))
    scan = b''.join(b'\0' + rgba[y*width*4:(y+1)*width*4] for y in range(height))
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind+body))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b'')
    return png, dict(width=width, height=height, format='TXF 0x0B ARGB1555 BE', transparent_pixels=transparent)


def nispack(stream, size):
    """Read bounded BE NISPACK table, never use names as filesystem paths."""
    stream.seek(0)
    header = stream.read(16)
    if len(header) != 16 or header[:8] != b'NISPACK\0':
        raise ValueError('invalid NISPACK header')
    count = struct.unpack_from('>I', header, 12)[0]
    if count > 100000 or 16 + count * 44 > size:
        raise ValueError('archive table exceeds bounds')
    table = stream.read(count * 44)
    if len(table) != count * 44:
        raise ValueError('truncated archive table')
    rows = []
    for index in range(count):
        entry = table[index * 44:(index + 1) * 44]
        offset, length, unknown = struct.unpack_from('>III', entry, 32)
        if offset < 16 + count * 44 or offset + length > size:
            raise ValueError('archive member exceeds bounds')
        rows.append(dict(index=index, name=entry[:32].split(b'\0')[0].decode('ascii', 'replace'), name_hex=entry[:32].hex(), offset=offset, size=length, unknown_be32=unknown))
    return rows


def characters(data):
    """char.dat: BE16 count, 4-byte header, 0x2A4 records (both lifts)."""
    if len(data) < 4:
        raise ValueError('truncated character header')
    count = struct.unpack_from('>H', data)[0]
    if count > 10000 or len(data) != 4 + count * 0x2A4:
        raise ValueError('character count/stride mismatch')
    rows = []
    for row in range(count):
        offset = 4 + row * 0x2A4
        raw = data[offset:offset + 0x2A4]
        texts = [raw[start:start + 52].split(b'\0')[0] for start in (0x1FC, 0x230)]
        decoded = []
        statuses = []
        for text in texts:
            try:
                decoded.append(text.decode('utf-8'))
                statuses.append('utf-8')
            except UnicodeDecodeError:
                decoded.append(text.decode('utf-8', 'replace'))
                statuses.append('invalid-utf-8; original bytes retained')
        rows.append(dict(row=row, record_offset=offset, id=struct.unpack_from('>H', raw, 0x194)[0], name=decoded[0], name_230=decoded[1], text_status=statuses, body_animation_ids=list(struct.unpack_from('>HH',raw,0x1BC)), raw_hex=raw.hex(), raw_be16=list(struct.unpack('>338H', raw))))
    return rows


def character_mappings(rows, assets):
    """Map proven +1BC/+1BE fields; never substitute row or class ID.

    Record +1BC/+1BE consumer: 1.40 func_00109E44, via class-record
    getter, selector*2 +1B0 +C. Runtime selection/special cases remain
    distinct from this exhaustive asset-candidate map.
    """
    import collections
    index=collections.defaultdict(list)
    for asset in assets:
        index[asset['name']].append(asset)
    links=[]
    for row in rows:
        matches=[]; missing=[]
        for value in dict.fromkeys(row['body_animation_ids']):
            if value==0: continue
            found=index.get('anm%05d.lzs' % value,[])
            if not found: missing.append(value)
            for asset in found:
                matches.append(dict(asset_key=asset['key'],body_animation_id=value,pages=asset.get('pages',[]),confidence='source-backed-field-and-exact-filename',reason='BE16 record +0x1BC/+0x1BE consumed by 1.40 func_00109E44; exact anm%05d.lzs stem. Asset exists; active archive precedence, selector, special-case overrides and palette selection are not asserted.'))
        links.append(dict(character_key=row.get('key','row:%d'%row['row']),id=row['id'],name=row['name'],matches=matches,missing_body_animation_ids=missing))
    return links


# Export plumbing deliberately uses generated indices/content hashes, never
# member names as paths. Sources are opened O_RDONLY and O_NOFOLLOW.
import collections
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sys


MAX_MEMBER_BYTES = 64 * 1024 * 1024
SOURCE_REFS = {
    'archive': 'port/src/d2_items.cpp:131-160, NISPACK header/table and TXF 0x0B BE ARGB1555',
    'character_id': '1.00 func_0033FBB8; 1.40 func_0034F8D8: +0x194 lookup, +0x2A4 stride',
    'character_text': '1.40 func_0010E77C: copies +0x1FC and +0x230 to runtime +0x650/+0x684',
    'body_animation_ids': '1.40 func_00109E44: class-record getter, selector*2 +0x1B0 +0xC; anm%05d.lzs format at TOC -0x5E50 consumed by func_000B96BC',
    'lzs': '1.40 func_001840E0 and func_00161F34; dat wrapper passes pointer+4; LE original/packed lengths, escape marker, overlapping backrefs',
    'anm': 'Empirical local archive schema: first 4 BE32 values, contiguous 16-byte texture/palette headers ending at meta_end+16, relative pixel/palette offsets. Exact header counts and payload bounds checked. PPU funcs_00163C70/00165004/001643E8 delegate ANM conversion to jobs; no lifted ANM/frame decoder equivalence claimed.',
    'palette': 'Local ANM palette header format 0, dimensions/offsets and byte data: BE ARGB8888; TXF format 0 maps to linear A8R8G8B8 in 1.40 func_002E2CF4. Indexed format 9 has one byte/pixel and exact 256-entry palettes in local resources; this container interpretation is empirical, not fully lifted conversion proof.'
}


def _no_symlinks(path):
    path=Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('symlink path refused: '+str(path))
    return path


def _source_open(path):
    path=_no_symlinks(path)
    if path.suffix.lower()=='.edat' or any(p.lower() in ('flag','savedata','saves') for p in path.parts):
        raise ValueError('credential/flag/save source refused')
    fd=os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
    return os.fdopen(fd,'rb')


def _sha_file(path):
    h=hashlib.sha256()
    with _source_open(path) as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def discover_sources(repo):
    """Only the approved Data directories; never descend into flag/save trees."""
    repo=_no_symlinks(repo)
    disc=repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data'
    roots=[disc] if disc.is_dir() else []
    for base in (repo/'port/hdd0/game',repo/'dlc'):
        if base.is_dir():
            roots.extend(p for p in sorted(base.glob('*/USRDIR/Data')) if p.is_dir())
    archives=[]; loose=[]; directory_inventory=[]
    for root in roots:
        root=_no_symlinks(root)
        found=[]; excluded=[]
        for p in sorted(root.iterdir()):
            if p.name.lower()=='flag':
                excluded.append(dict(name=p.name,status='excluded-directory; not traversed'));continue
            if p.is_symlink():raise ValueError('source Data symlink refused: '+str(p))
            if p.is_dir():
                excluded.append(dict(name=p.name,status='directory not traversed'));continue
            if p.suffix.lower()=='.edat':
                excluded.append(dict(name=p.name,status='excluded-EDAT; not opened'));continue
            if re.fullmatch(r'(?:START|ANM_HI)(?:_\d+)?\.dat',p.name):
                archives.append(p);found.append(p.name)
            elif root!=disc and p.is_file():
                loose.append(p);found.append(p.name)
        directory_inventory.append(dict(path=str(root),included=found,excluded=excluded))
    return dict(archives=list(dict.fromkeys(archives)),loose=list(dict.fromkeys(loose)),roots=roots,directories=directory_inventory)


class _Output:
    def __init__(self,path,limit):
        self.path=_no_symlinks(path);self.limit=limit;self.bytes=0;self.files={}
        if self.path.exists():raise ValueError('output already exists')
        if not self.path.parent.is_dir():raise ValueError('output parent must exist')
        self.path.mkdir()
    def write(self,relative,data):
        parts=Path(relative).parts
        if Path(relative).is_absolute() or not parts or any(p in ('..','.') for p in parts):raise ValueError('unsafe output path')
        target=_no_symlinks(self.path/relative)
        if target.exists():
            if relative in self.files and self.files[relative]['sha256']==hashlib.sha256(data).hexdigest():return relative
            raise ValueError('output file already exists: '+relative)
        if self.bytes+len(data)>self.limit:raise OSError('output byte budget exceeded; export not complete, no silent truncation')
        target.parent.mkdir(parents=True,exist_ok=True);_no_symlinks(target.parent)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as f:f.write(data)
        self.files[relative]=dict(size=len(data),sha256=hashlib.sha256(data).hexdigest());self.bytes+=len(data)
        return relative
    def blob(self,kind,data,suffix='bin'):
        return self.write(kind+'/'+hashlib.sha256(data).hexdigest()+'.'+suffix,data)
    def json(self,name,obj):
        return self.write(name,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def _source_excerpts(repo,out):
    refs=[]
    if repo is None:return refs
    repo=Path(repo)
    wanted={'recomp':{'func_0033FBB8'},'recomp-140':{'func_0034F8D8','func_0010E77C','func_00109E44','func_001840E0','func_00161F34','func_000B96BC','func_002E2CF4'}}
    for version,names in wanted.items():
        for file in sorted((repo/'port/src'/version).glob('ppu_recomp_*.cpp')):
            with _source_open(file) as f:text=f.read().decode('utf-8')
            for name in sorted(names):
                match=re.search(r'void '+name+r'\(ppu_context\* ctx\) \{[\s\S]*?(?=\nvoid func_|\Z)',text)
                if match:
                    excerpt=match.group();line=text[:match.start()].count('\n')+1
                    saved=out.write('source_refs/'+version+'-'+name+'.cpp',excerpt.encode('utf-8'))
                    refs.append(dict(path=str(file),function=name,line_start=line,line_end=line+excerpt.count('\n'),excerpt=saved,excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest()))
    return refs


def export_archives(archives,output,repo=None,loose=(),source_roots=(),directory_inventory=(),max_output_bytes=5*1024**3):
    """Exhaustive inventory/raw preservation plus bounded, explicit decoders."""
    archives=[_no_symlinks(p) for p in archives];loose=[_no_symlinks(p) for p in loose];target=_no_symlinks(output)
    if not archives:raise ValueError('no source archives found')
    for source in (*archives,*loose,*map(Path,source_roots)):
        if target==source or target in source.parents or source in target.parents:raise ValueError('output/source overlap')
    if target.exists():raise ValueError('output already exists')
    # Preflight all tables before creating any output. No writes to sources.
    inventory=[]
    for i,path in enumerate(archives):
        with _source_open(path) as f:
            size=os.fstat(f.fileno()).st_size;members=nispack(f,size)
        inventory.append(dict(key='a%03d'%i,path=str(path),size=size,sha256_before=_sha_file(path),header_count=len(members),members=members))
    loose_before={str(p):_sha_file(p) for p in loose}
    out=_Output(target,max_output_bytes)
    rows=[];assets=[];tables=[];loose_inventory=[]
    for archive in inventory:
        print('Processing',archive['key'],Path(archive['path']).name,'members',len(archive['members']),flush=True)
        with _source_open(archive['path']) as f:
            for member in archive['members']:
                member['key']=archive['key']+'/m%05d'%member['index']
                f.seek(member['offset']);remaining=member['size'];digest=hashlib.sha256()
                if remaining>MAX_MEMBER_BYTES:
                    # Hash exhaustively but do not allocate unbounded resources.
                    while remaining:
                        block=f.read(min(remaining,1024*1024))
                        if not block:raise ValueError('source truncated during export')
                        digest.update(block);remaining-=len(block)
                    member.update(sha256=digest.hexdigest(),decoder_status='resource-bound-exceeded; raw remains in source archive, not copied',raw=None)
                    continue
                data=f.read(remaining)
                if len(data)!=remaining:raise ValueError('source truncated during export')
                digest.update(data);member['sha256']=digest.hexdigest();member['raw']=out.blob('raw',data)
                member['decoder_status']='raw-retained; semantic format not decoded'
                if member['name']=='char.dat':
                    parsed=characters(data)
                    for row in parsed:
                        row.update(key=member['key']+'/r%05d'%row['row'],archive_key=archive['key'],member_key=member['key'],archive_path=archive['path'],member_name=member['name'],source_offset=member['offset']+row['record_offset'])
                        raw=bytes.fromhex(row['raw_hex']);row['raw_record']=out.blob('records',raw);row['raw_sha256']=hashlib.sha256(raw).hexdigest()
                    rows.extend(parsed);member['decoder_status']='decoded-character-records'
                    tables.append(dict(member_key=member['key'],archive_path=archive['path'],header_hex=data[:4].hex(),header_count=struct.unpack_from('>H',data)[0],parsed_count=len(parsed),record_stride=0x2A4))
                suffix=Path(member['name']).suffix.lower()
                if suffix in ('.txf','.lzs','.pak','.ffm','.obf'):
                    asset=dict(key=member['key'],archive_key=archive['key'],name=member['name'],source_path=archive['path'],source_offset=member['offset'],size=member['size'],sha256=member['sha256'],raw=member['raw'],pages=[])
                    try:
                        if suffix=='.txf':
                            png,meta=txf_png(data);meta.update(png=out.blob('png',png,'png'),decoder_status='decoded-TXF-0x0B',confidence='source-backed-format')
                            asset['pages']=[meta];asset['decoder_status']='decoded-TXF-0x0B'
                        elif suffix=='.lzs' and data[:4]==b'dat\0':
                            raw=unlzs(data);asset['expanded_size']=len(raw);asset['expanded_sha256']=hashlib.sha256(raw).hexdigest()
                            pages=anm_pages(raw,include_rgba=False)
                            meta_end=struct.unpack_from('>I',raw)[0]+16
                            asset['anm_header_be32']=list(struct.unpack_from('>8I',raw));asset['anm_metadata_raw']=out.blob('anm_metadata',raw[:meta_end]);asset['header_texture_count']=struct.unpack_from('>I',raw,8)[0];asset['header_palette_count']=struct.unpack_from('>I',raw,12)[0]
                            asset['validated_page_pairs']=len(pages)
                            for page in pages:
                                if page['decoder_status']=='decoded-index8-argb8888':
                                    png=indexed_png(page['width'],page['height'],page.pop('indices'),page.pop('colors'))
                                    page['png']=out.blob('png',png,'png');page['confidence']='empirically-validated-ANM-container; exact header counts/bounds, palette bytes preserved; runtime palette/frame composition unknown'
                            asset['pages']=pages
                            asset['decoder_status']='ANM-page-pairs-processed'
                        else:asset['decoder_status']='raw-retained; unsupported-resource-container'
                    except (ValueError,NotImplementedError) as exc:
                        # Decoder failures retain source/raw and never masquerade as success.
                        asset['decoder_status']='raw-retained; decoder-rejected-or-unsupported'
                        asset['decoder_reason']=str(exc)
                    member['decoder_status']=asset['decoder_status'];assets.append(asset)
        out.json('progress/'+archive['key']+'.json',dict(archive=archive['path'],members=len(archive['members']),character_records_so_far=len(rows),assets_so_far=len(assets),output_bytes_so_far=out.bytes))
    for path in loose:
        with _source_open(path) as f:
            size=os.fstat(f.fileno()).st_size
            if size>MAX_MEMBER_BYTES:raise ValueError('loose resource exceeds bound')
            data=f.read()
        loose_inventory.append(dict(path=str(path),size=size,sha256_before=loose_before[str(path)],raw=out.blob('raw',data),decoder_status='raw-retained; loose DLC/update resource'))
    for archive in inventory:
        archive['sha256_after']=_sha_file(archive['path']);archive['unchanged']=archive['sha256_before']==archive['sha256_after']
        if not archive['unchanged']:raise ValueError('source hash changed during export: '+archive['path'])
    for entry in loose_inventory:
        entry['sha256_after']=_sha_file(entry['path'])
        if entry['sha256_before']!=entry['sha256_after']:raise ValueError('loose source changed')
    maps=character_mappings(rows,[{**a,'pages':[{k:v for k,v in p.items() if k in ('png','texture','palette','width','height','decoder_status')} for p in a['pages']]} for a in assets])
    refs=_source_excerpts(repo,out)
    out.json('archive_inventory.json',inventory);out.json('loose_resource_inventory.json',loose_inventory)
    out.json('character_tables.json',tables);out.json('characters.json',rows);out.json('artwork.json',assets);out.json('character_artwork_mappings.json',maps)
    out.json('schema_and_source_refs.json',dict(source_refs=SOURCE_REFS,excerpts=refs,character_schema=dict(header_size=4,header_count='BE16 +0',header_unknown='BE16 +2 retained',stride=676,id='BE16 +0x194; NOT row index',name='UTF-8 NUL-terminated region +0x1FC length52',name_230='UTF-8 NUL-terminated region +0x230 length52; title-like text, not asserted as full semantics',body_animation_ids='BE16 +0x1BC,+0x1BE, selector-dependent runtime consumer',unknown='all remaining bytes preserved as raw_hex, raw_be16 and exact record binary'),archive_precedence='all variants retained separately; no guessed merged active table'))
    csvbuf=io.StringIO(newline='');writer=csv.writer(csvbuf)
    writer.writerow(['key','archive_path','row','id','name','name_230','body_animation_id_0','body_animation_id_1','record_offset','source_offset','raw_record','raw_sha256']+['raw_be16_%03X'%i for i in range(0,676,2)])
    for r in rows:writer.writerow([r['key'],r['archive_path'],r['row'],r['id'],r['name'],r['name_230'],*r['body_animation_ids'],r['record_offset'],r['source_offset'],r['raw_record'],r['raw_sha256'],*r['raw_be16']])
    out.write('characters.csv',csvbuf.getvalue().encode('utf-8'))
    status_counts=dict(collections.Counter(a['decoder_status'] for a in assets))
    counts=dict(archives=len(inventory),archive_members=sum(a['header_count'] for a in inventory),character_tables=len(tables),character_records=len(rows),unique_character_ids=len({r['id'] for r in rows}),artwork_resources=len(assets),decoded_page_references=sum('png' in p for a in assets for p in a['pages']),unique_png_files=sum(n.startswith('png/') for n in out.files),mapped_character_records=sum(bool(m['matches']) for m in maps),unmapped_character_records=sum(not m['matches'] for m in maps),raw_member_copies=sum(m.get('raw') is not None for a in inventory for m in a['members']),loose_resources=len(loose_inventory))
    summary=dict(counts=counts,artwork_decoder_status_counts=status_counts,source_roots=list(map(str,source_roots)),directories=list(directory_inventory),source_refs=SOURCE_REFS,bounds=dict(max_member_bytes=MAX_MEMBER_BYTES,max_expanded_lzs_bytes=64*1024*1024,max_texture_dimension=4096,max_ANM_textures=4096,max_ANM_palettes=256,max_ANM_page_pairs=32768,max_output_bytes=max_output_bytes),gaps=['Unknown character fields intentionally unlabeled; exact bytes retained.','No runtime active-archive/DLC entitlement/selector/palette selection inferred. All local variants retained.','PNG exports are texture pages, not reconstructed animation frames or assembled portraits. Palette combinations are research candidates, not runtime-selected colors.','ANM table/palette layout is empirically validated against local headers and payloads, not a lifted SPU/job decoder equivalence proof.','Other TXF formats, non-dat LZS, PAK/OBF/FFM containers and ancillary data tables are retained raw with explicit status; no guessed decoders.','Resources beyond limits are explicitly reported, not silently truncated. No flags, EDAT contents, saves, or runtime memory opened.'])
    out.json('summary.json',summary)
    gallery=['<!doctype html><meta charset="utf-8"><title>Disgaea D2 Character Research</title><style>body{font:16px system-ui;background:#171923;color:#eee;padding:24px}a{color:#a8caff}img{max-width:320px;max-height:320px;background:repeating-conic-gradient(#333 0% 25%,#555 0% 50%) 0/16px 16px}details{margin:16px 0}small{color:#bbc}</style><h1>Disgaea D2 Character Research</h1><p>All source variants, no guessed active merge. PNGs are transparent texture pages; palette selection and animation/frame composition remain unknown. See summary.json and schema_and_source_refs.json.</p><input placeholder="Filter names / IDs" oninput="for(const e of document.querySelectorAll(\'details\'))e.hidden=!e.dataset.search.includes(this.value.toLowerCase())">']
    for m in maps:
        gallery.append('<details data-search="'+html.escape((str(m['id'])+' '+m['name']).lower(),quote=True)+'"><summary>'+html.escape(str(m['id'])+' — '+m['name']+' ['+m['character_key']+']')+'</summary>')
        if not m['matches']:gallery.append('<p>No exact source-field artwork match; see mapping JSON.</p>')
        for match in m['matches']:
            gallery.append('<p>'+html.escape(match['asset_key']+' animation ID '+str(match['body_animation_id']))+'</p>')
            for p in match['pages']:
                if 'png' in p:gallery.append('<a href="'+p['png']+'"><img loading="lazy" src="'+p['png']+'" alt="texture '+str(p.get('texture',0))+' palette '+str(p.get('palette',0))+'"></a>')
        gallery.append('</details>')
    out.write('index.html','\n'.join(gallery).encode('utf-8'))
    out.write('README.txt',('Open index.html for a local character/artwork browser. No network is required.\nAll source archives/members, offsets/sizes/SHA256, full character variants, exact raw records, PNG page/palette mappings and unsupported raw resources are preserved.\nUse python3 -B tools/d2_character_export.py --verify "'+str(target)+'" to recheck file/source hashes, header/record/page counts and PNG integrity.\nSee summary.json for explicit bounds and remaining gaps. These are proprietary local assets: do not upload.\n').encode())
    manifest=dict(version=1,status='complete',counts=counts,output_bytes_excluding_manifest=out.bytes,artwork_decoder_status_counts=status_counts,files=dict(out.files),source_hashes=[dict(path=a['path'],before=a['sha256_before'],after=a['sha256_after']) for a in inventory]+[dict(path=a['path'],before=a['sha256_before'],after=a['sha256_after']) for a in loose_inventory])
    # Manifest intentionally does not hash itself.
    out.json('manifest.json',manifest)
    return manifest


def _verify_png(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('PNG signature')
    i=8;packed=bytearray();width=height=color=None;ended=False;palette=None
    while i<len(data):
        if i+12>len(data):raise ValueError('PNG chunk bounds')
        n=struct.unpack_from('>I',data,i)[0];kind=data[i+4:i+8];end=i+12+n
        if end>len(data) or zlib.crc32(data[i+4:i+8+n])!=struct.unpack_from('>I',data,i+8+n)[0]:raise ValueError('PNG CRC/bounds')
        body=data[i+8:i+8+n]
        if kind==b'IHDR':
            width,height,depth,color,comp,filt,inter=struct.unpack('>IIBBBBB',body)
            if depth!=8 or color not in (3,6) or comp or filt or inter or not 0<width<=4096 or not 0<height<=4096:raise ValueError('PNG header')
        if kind==b'PLTE':palette=body
        if kind==b'IDAT':packed.extend(body)
        if kind==b'IEND':ended=True
        i=end
    if not ended or width is None:raise ValueError('PNG missing chunks')
    channels=1 if color==3 else 4;expected=height*(1+width*channels)
    dec=zlib.decompressobj();scan=dec.decompress(packed,expected+1)
    if len(scan)!=expected or not dec.eof or dec.unused_data:raise ValueError('PNG pixel size')
    if any(scan[y*(1+width*channels)]!=0 for y in range(height)):raise ValueError('PNG scan filter')
    if color==3 and (palette is None or len(palette)%3):raise ValueError('PNG palette')
    return dict(width=width,height=height,color_type=color)


def verify_indexed_pixels(png,width,height,indices,palette):
    """Compare PNG indices, RGB palette and alpha against decoded source data."""
    meta=_verify_png(png)
    if meta!=dict(width=width,height=height,color_type=3):raise ValueError('source/PNG dimension or color mismatch')
    pos=8;packed=bytearray();rgb=alpha=None
    while pos<len(png):
        size=struct.unpack_from('>I',png,pos)[0];kind=png[pos+4:pos+8];body=png[pos+8:pos+8+size]
        if kind==b'PLTE':rgb=body
        elif kind==b'tRNS':alpha=body
        elif kind==b'IDAT':packed.extend(body)
        pos+=12+size
    if rgb!=b''.join(c[:3] for c in palette) or alpha!=bytes(c[3] for c in palette):raise ValueError('source/PNG palette or alpha mismatch')
    expected=height*(width+1)
    dec=zlib.decompressobj();scan=dec.decompress(packed,expected+1)
    if len(scan)!=expected or not dec.eof:raise ValueError('PNG bounded scan size')
    for y in range(height):
        if scan[y*(width+1)+1:(y+1)*(width+1)]!=indices[y*width:(y+1)*width]:raise ValueError('source/PNG index mismatch')
    return True


def verify_export(output,check_sources=True,check_pixels=False):
    root=_no_symlinks(output)
    def load(name):
        with _source_open(root/name) as f:return json.load(f)
    manifest=load('manifest.json')
    if manifest['status']!='complete':raise ValueError('incomplete manifest')
    actual=set()
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            p=Path(directory)/name
            if p.is_symlink():raise ValueError('output symlink refused')
        actual.update(str((Path(directory)/name).relative_to(root)) for name in files)
    if actual != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('output files do not exactly match manifest')
    png_count=0
    for name,meta in manifest['files'].items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('manifest path traversal')
        p=_no_symlinks(root/name)
        if p.stat().st_size!=meta['size'] or _sha_file(p)!=meta['sha256']:raise ValueError('output checksum mismatch: '+name)
        if name.startswith('png/'):
            with _source_open(p) as f:_verify_png(f.read())
            png_count+=1
    inventory=load('archive_inventory.json');rows=load('characters.json');tables=load('character_tables.json');assets=load('artwork.json');maps=load('character_artwork_mappings.json')
    members=[m for a in inventory for m in a['members']]
    if any(a['header_count']!=len(a['members']) for a in inventory):raise ValueError('archive count mismatch')
    if any(t['header_count']!=t['parsed_count'] for t in tables) or sum(t['header_count'] for t in tables)!=len(rows):raise ValueError('character table count mismatch')
    for row in rows:
        raw=bytes.fromhex(row['raw_hex'])
        if len(raw)!=676 or hashlib.sha256(raw).hexdigest()!=row['raw_sha256'] or manifest['files'][row['raw_record']]['sha256']!=row['raw_sha256']:raise ValueError('raw record mismatch')
        if struct.unpack_from('>H',raw,0x194)[0]!=row['id']:raise ValueError('record ID mismatch')
    for asset in assets:
        if 'validated_page_pairs' in asset:
            expected=asset['header_texture_count']*asset['header_palette_count']
            if len(asset['pages'])!=expected or asset['validated_page_pairs']!=expected:raise ValueError('ANM page count mismatch')
        if any(p.get('png') not in manifest['files'] for p in asset['pages'] if 'png' in p):raise ValueError('missing artwork PNG')
    by_key={a['key']:a for a in assets}
    if len(maps)!=len(rows):raise ValueError('mapping count mismatch')
    for m,row in zip(maps,rows):
        if m['character_key']!=row['key'] or m['id']!=row['id']:raise ValueError('mapping ID mismatch')
        if any(x['asset_key'] not in by_key or x['body_animation_id'] not in row['body_animation_ids'] for x in m['matches']):raise ValueError('mapping target mismatch')
    with _source_open(root/'characters.csv') as f:
        with io.TextIOWrapper(f,encoding='utf-8') as text:
            csv_count=sum(1 for _ in csv.DictReader(text))
    computed=dict(archives=len(inventory),archive_members=len(members),character_tables=len(tables),character_records=len(rows),unique_character_ids=len({r['id'] for r in rows}),artwork_resources=len(assets),decoded_page_references=sum('png' in p for a in assets for p in a['pages']),unique_png_files=png_count,mapped_character_records=sum(bool(m['matches']) for m in maps),unmapped_character_records=sum(not m['matches'] for m in maps),raw_member_copies=sum(m.get('raw') is not None for m in members),loose_resources=len(load('loose_resource_inventory.json')))
    if computed!=manifest['counts'] or csv_count!=len(rows):raise ValueError('declared/CSV totals mismatch')
    for member in members:
        if member.get('raw') and manifest['files'][member['raw']]['sha256']!=member['sha256']:raise ValueError('raw member hash mismatch')
    pixel_references=0
    if check_pixels:
        verified_pairs=set()
        for asset in assets:
            shown=[p for p in asset['pages'] if 'png' in p]
            if not shown:continue
            pair_keys=[(asset['sha256'],p.get('texture'),p.get('palette'),p['png']) for p in shown]
            if not all(k in verified_pairs for k in pair_keys):
                if asset['size']>MAX_MEMBER_BYTES:raise ValueError('source pixel resource bound')
                with _source_open(asset['source_path']) as source:
                    source.seek(asset['source_offset']);data=source.read(asset['size'])
                if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('source artwork member mismatch')
                if asset['decoder_status']=='decoded-TXF-0x0B':
                    png,_=txf_png(data)
                    with _source_open(root/shown[0]['png']) as image:
                        if png!=image.read():raise ValueError('source TXF PNG pixels mismatch')
                else:
                    source_pages=anm_pages(unlzs(data),include_rgba=False)
                    for p in source_pages:
                        if p['decoder_status']!='decoded-index8-argb8888':continue
                        shown_page=next((s for s in shown if s['texture']==p['texture'] and s['palette']==p['palette']),None)
                        if shown_page is None:raise ValueError('missing decoded source texture/palette PNG')
                        key=(asset['sha256'],p['texture'],p['palette'],shown_page['png'])
                        if key not in verified_pairs:
                            with _source_open(root/shown_page['png']) as image:
                                verify_indexed_pixels(image.read(),p['width'],p['height'],p['indices'],p['colors'])
                            verified_pairs.add(key)
                verified_pairs.update(pair_keys)
            pixel_references+=len(shown)
        if pixel_references!=computed['decoded_page_references']:raise ValueError('source pixel reference count mismatch')
    if check_sources:
        for source in manifest['source_hashes']:
            if source['before']!=source['after'] or _sha_file(source['path'])!=source['before']:raise ValueError('source hash mismatch: '+source['path'])
    total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    return dict(status='verified',counts=computed,verified_output_files=len(manifest['files']),verified_PNGs=png_count,source_hashes_checked=len(manifest['source_hashes']) if check_sources else 0,output_bytes_including_manifest=total,CSV_rows=csv_count,verified_source_pixel_references=pixel_references if check_pixels else None)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--pixels',action='store_true',help='Verify exported PNG pixels against source artwork')
    parser.add_argument('--max-output-bytes',type=int,default=5*1024**3)
    args=parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_export(args.verify,check_pixels=args.pixels),indent=2));return 0
    if args.output is None:parser.error('--output is required (must be new; no automatic overwrite)')
    sources=discover_sources(args.repo)
    export_archives(sources['archives'],args.output,repo=args.repo,loose=sources['loose'],source_roots=sources['roots'],directory_inventory=sources['directories'],max_output_bytes=args.max_output_bytes)
    verified=verify_export(args.output,check_pixels=args.pixels)
    print(json.dumps(verified,indent=2));return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,NotImplementedError) as exc:
        print('Export/verification failed (no success claimed): '+str(exc),file=sys.stderr);sys.exit(1)
