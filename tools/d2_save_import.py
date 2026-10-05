#!/usr/bin/env python3
"""Import a retail NA Disgaea D2 save into the port's RPCS3/plain layout.

Run with .venv/bin/python. By default copy port/hdd0 to a unique directory
under port/runs, then add a free NPUB31321_NORMAL_xx slot. --into explicitly
selects another hdd0; existing slots are never replaced. Source is read only.

Format/algorithm references (read via gh):
https://github.com/SteffenL/pfdtool/blob/master/src/pfd.c (flatz)
https://github.com/bucanero/apollo-ps3/blob/master/source/pfd.c
https://github.com/bucanero/apollo-ps3/blob/master/source/pfd_util.c
The signature and entry keys use AES-CBC with the public syscon key. File
block i is AES_K(plain_i XOR AES_K(be64(i) || zero64)), NOT ordinary CBC/CTR.
This creates plaintext saves only; it does not resign saves for a console.
"""

import argparse
from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import re
import shutil
import struct
import tempfile

from Crypto.Cipher import AES
from Crypto.Util.strxor import strxor


ROOT = Path(__file__).resolve().parents[1]
# BLUS31313 EBOOT: func_00164C3C (load) copies 16 bytes from
# *(TOC 0x3fde60 - 0x46c0) + 0x40 = 0x396c98 to FileSet + 0x0c.
# func_00164D74 (save) uses the same data.
# v1.40: func_0016D700 (load), func_0016D7FC (save); TOC 0x47df98 -
# 0x43a8 points to the same secure-id structure (+0x40), again 0f x16.
SECURE_FILE_ID = bytes.fromhex("0f" * 16)
EXPECTED_SIZE = 1498152
SYSCON_KEY = bytes.fromhex("d413b89663e1fe9f75143d3bb4565274")
KEYGEN_KEY = bytes.fromhex("6b1acea246b745fd8f93763b920594cd53483b82")
SFO_KEY = bytes.fromhex("0c08000e090504040d010f000406020209060d03")
AUTH_ID = bytes.fromhex("1010000001000003")
ENTRY_SIZE = 272
MAX_FILE_SIZE = 64 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha1_hmac(key, data):
    return hmac.digest(key, data, "sha1")


def verify_hash(key, data, expected, label):
    require(hmac.compare_digest(sha1_hmac(key, data), expected),
            f"PFD hash mismatch: {label}")


def secure_hash_key(secure_id):
    require(len(secure_id) == 16, "secure file ID must be 16 bytes")
    inserts = {1: 11, 2: 15, 5: 14, 8: 10}
    source = iter(secure_id)
    return bytes(inserts[i] if i in inserts else next(source) for i in range(20))


def crypt_file(data, key, *, encrypt=False):
    """Public PFD block transform; callers handle zero padding/true length."""
    require(len(data) % 16 == 0, "protected file size is not a multiple of 16")
    aes = AES.new(key[:16], AES.MODE_ECB)
    counters = b"".join(struct.pack(">QQ", i, 0) for i in range(len(data) // 16))
    masks = aes.encrypt(counters)
    return aes.encrypt(strxor(data, masks)) if encrypt else strxor(aes.decrypt(data), masks)


def file_bytes(path, limit=MAX_FILE_SIZE):
    require(not path.is_symlink() and path.is_file(), f"missing/unsafe file: {path}")
    require(path.stat().st_size <= limit, f"file too large: {path}")
    data = path.read_bytes()
    require(len(data) <= limit, f"file too large: {path}")
    return data


@dataclass
class Entry:
    name: str
    next_index: int
    key: bytes
    hashes: tuple
    size: int
    hashed: bytes


def parse_pfd(data):
    require(120 <= len(data) <= 32768, "invalid PARAM.PFD length")
    magic, version = struct.unpack_from(">QQ", data)
    require(magic == 0x50464442 and version in (3, 4), "unsupported PFD magic/version")
    signature = AES.new(SYSCON_KEY, AES.MODE_CBC, data[16:32]).decrypt(data[32:96])
    hash_key = sha1_hmac(KEYGEN_KEY, signature[40:60]) if version == 4 else signature[40:60]
    capacity, reserved, used = struct.unpack_from(">QQQ", data, 96)
    require(0 < capacity <= 4096 and 0 < used <= reserved <= 120, "invalid PFD table counts")
    entry_start = 120 + capacity * 8
    sig_start = entry_start + reserved * ENTRY_SIZE
    end = sig_start + capacity * 20
    require(end <= len(data), "truncated PFD tables")
    verify_hash(hash_key, data[96:entry_start], signature[20:40], "top table")
    verify_hash(hash_key, data[sig_start:end], signature[:20], "bottom table")
    entries = []
    for i in range(used):
        raw = data[entry_start + i * ENTRY_SIZE:entry_start + (i + 1) * ENTRY_SIZE]
        name = raw[8:73].split(b"\0", 1)[0].decode("ascii")
        require(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) and name not in (".", ".."),
                "unsafe PFD filename")
        require(name not in {e.name for e in entries}, "duplicate PFD filename")
        entries.append(Entry(name, struct.unpack_from(">Q", raw)[0], raw[80:144],
                             tuple(raw[144+j*20:164+j*20] for j in range(4)),
                             struct.unpack_from(">Q", raw, 264)[0], raw[8:73] + raw[80:272]))
    seen = set()
    for bucket in range(capacity):
        index = struct.unpack_from(">Q", data, 120 + bucket * 8)[0]
        chain = bytearray()
        while index < reserved:
            require(index < used and index not in seen, "invalid/cyclic PFD entry chain")
            seen.add(index)
            entry = entries[index]
            name_hash = 0
            for c in entry.name.encode("ascii"):
                name_hash = (31 * name_hash + c) & 0xffffffffffffffff
            require(name_hash % capacity == bucket, "PFD entry in wrong hash bucket")
            chain.extend(entry.hashed)
            index = entry.next_index
        verify_hash(hash_key, chain, data[sig_start+bucket*20:sig_start+(bucket+1)*20],
                    f"entry bucket {bucket}")
    require(len(seen) == used, "unreachable PFD entries")
    return version, entries


@dataclass
class SfoEntry:
    fmt: int
    value: bytes
    allocation: bytes


def parse_sfo(data):
    require(len(data) >= 20, "truncated PARAM.SFO")
    magic, version, keys, values, count = struct.unpack_from("<4s4I", data)
    require(magic == b"\0PSF" and version == 0x101 and count <= 1024,
            "unsupported SFO header")
    require(20 + count * 16 <= keys <= values <= len(data), "invalid SFO table offsets")
    entries = {}
    for i in range(count):
        key_off, fmt, size, maximum, offset = struct.unpack_from("<HHIII", data, 20 + i * 16)
        require(size <= maximum and values + offset + maximum <= len(data), "invalid SFO value")
        start = keys + key_off
        require(keys <= start < values, "invalid SFO key offset")
        end = data.find(b"\0", start, values)
        require(end != -1, "unterminated SFO key")
        name = data[start:end].decode("ascii")
        require(name not in entries, "duplicate SFO key")
        allocation = data[values+offset:values+offset+maximum]
        entries[name] = SfoEntry(fmt, allocation[:size], allocation)
    return entries


def set_sfo(entries, name, fmt, value, maximum):
    maximum = max(maximum, len(entries[name].allocation) if name in entries else 0, len(value))
    entries[name] = SfoEntry(fmt, value, value.ljust(maximum, b"\0"))


def encode_sfo(entries):
    keys, values, index = bytearray(), bytearray(), bytearray()
    for name, entry in sorted(entries.items()):
        values.extend(b"\0" * (-len(values) % 4))
        index.extend(struct.pack("<HHIII", len(keys), entry.fmt, len(entry.value),
                                 len(entry.allocation), len(values)))
        keys.extend(name.encode("ascii") + b"\0")
        values.extend(entry.allocation)
    key_start = 20 + len(index)
    value_start = (key_start + len(keys) + 3) & ~3
    return (struct.pack("<4s4I", b"\0PSF", 0x101, key_start, value_start, len(entries))
            + index + keys + bytes(value_start - key_start - len(keys)) + values)


def convert(source):
    """Verify before changing SFO, return the complete plaintext flat save."""
    require(not source.is_symlink() and source.is_dir(), "source must be a real save directory")
    version, entries = parse_pfd(file_bytes(source / "PARAM.PFD", 32768))
    files = {p.name: file_bytes(p) for p in source.iterdir() if p.name != "PARAM.PFD"}
    require("PARAM.SFO" in files and "ICON0.PNG" in files, "missing PARAM.SFO/ICON0.PNG")
    sfo = parse_sfo(files["PARAM.SFO"])
    directory = sfo.get("SAVEDATA_DIRECTORY")
    require(directory is not None and re.fullmatch(rb"NPUB31321_NORMAL_\d{2}", directory.value.rstrip(b"\0")),
            "not a North-America D2 NORMAL save")
    category = sfo.get("CATEGORY")
    require(category is not None and category.value.rstrip(b"\0") == b"SD", "not savedata SFO")
    by_name = {entry.name: entry for entry in entries}
    require("SAVEDATA.DAT" in by_name, "SAVEDATA.DAT missing from PFD")
    require(by_name["SAVEDATA.DAT"].size == EXPECTED_SIZE, "unexpected D2 payload size in PFD")
    secure_names = {"SAVEDATA.DAT"}
    for name, field in sfo.items():
        if name.startswith("*") and field.fmt == 0x404 and field.value == b"\x01\0\0\0":
            secure_names.add(name[1:])
    require(secure_names <= by_name.keys(), "secure file missing from PFD")
    verified, skipped = [], []
    for entry in entries:
        require(entry.name in files, f"PFD file missing: {entry.name}")
        data = files[entry.name]
        if entry.name == "PARAM.SFO":
            require(len(data) == entry.size, "PARAM.SFO size differs from PFD")
            for i, key in ((0, SFO_KEY), (3, AUTH_ID)):
                verify_hash(key, data, entry.hashes[i], f"PARAM.SFO[{i}]")
                verified.append(f"PARAM.SFO[{i}]")
            skipped.extend(("PARAM.SFO console-ID hash", "PARAM.SFO disc-key hash"))
        elif entry.name in secure_names:
            require(0 < entry.size <= MAX_FILE_SIZE and len(data) == ((entry.size+15) & ~15),
                    f"protected size differs from PFD: {entry.name}")
            hash_key = secure_hash_key(SECURE_FILE_ID)
            verify_hash(hash_key, data, entry.hashes[0], entry.name)
            key = AES.new(SYSCON_KEY, AES.MODE_CBC, hash_key[:16]).decrypt(entry.key)
            files[entry.name] = crypt_file(data, key)[:entry.size]
            verified.append(entry.name)
        else:
            require(len(data) == entry.size, f"plain file size differs from PFD: {entry.name}")
            skipped.append(f"{entry.name} file hash (no secure ID)")
    return files, sfo, secure_names, {"pfd_version": version, "verified": verified, "skipped": skipped}


def import_save(source, into=None):
    files, sfo, secure_names, checks = convert(source)
    temporary_hdd = None
    if into is None:
        runs = ROOT / "port/runs"
        runs.mkdir(parents=True, exist_ok=True)
        temporary_hdd = Path(tempfile.mkdtemp(prefix="AC-import-", dir=runs))
        into = temporary_hdd / "hdd0"
        try:
            shutil.copytree(ROOT / "port/hdd0", into, symlinks=True)
        except BaseException:
            shutil.rmtree(temporary_hdd)
            raise
    into = into.absolute()
    # Do not allow an explicit target to reach the dump, source, or an external
    # savedata tree through symlinks. Existing saves are never removed/changed.
    try:
        dump = (ROOT / "Disgaea D2 A Brighter Darkness - [BLUS31313]").resolve()
        resolved = into.resolve()
        require(not resolved.is_relative_to(dump) and not dump.is_relative_to(resolved),
                "target overlaps the read-only game dump")
        source_path = source.resolve()
        require(not resolved.is_relative_to(source_path) and not source_path.is_relative_to(resolved),
                "target overlaps the import source")
        save_root = into / "home/00000001/savedata"
        require(not into.is_symlink() and save_root.resolve() == resolved / "home/00000001/savedata",
                "target savedata path contains a symlink")
        save_root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".AC-import-", dir=save_root))
        destination = None
        try:
            # mkdir exclusively reserves the free slot, including dangling links.
            for slot in range(100):
                candidate = save_root / f"NPUB31321_NORMAL_{slot:02d}"
                try:
                    candidate.mkdir()
                except FileExistsError:
                    continue
                destination = candidate
                break
            require(destination is not None, "no free NORMAL_00..99 slots")
            set_sfo(sfo, "SAVEDATA_DIRECTORY", 0x204, destination.name.encode() + b"\0", 32)
            for name in secure_names:
                set_sfo(sfo, "*" + name, 0x404, struct.pack("<I", 1), 4)
            files["PARAM.SFO"] = encode_sfo(sfo)
            for name, data in files.items():
                (stage / name).write_bytes(data)
            stage.replace(destination)  # only our own empty, reserved directory
        except BaseException:
            if destination is not None:
                destination.rmdir()
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    except BaseException:
        if temporary_hdd is not None:
            shutil.rmtree(temporary_hdd)
        raise
    checks.update(hdd0=str(into), slot=destination.name,
                  size=len(files["SAVEDATA.DAT"]),
                  sha256=hashlib.sha256(files["SAVEDATA.DAT"]).hexdigest())
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="console save directory containing PARAM.PFD")
    parser.add_argument("--into", type=Path, help="explicit target hdd0 (default: fresh COPY under port/runs)")
    args = parser.parse_args()
    try:
        result = import_save(args.source, args.into)
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        parser.exit(1, f"Import failed: {error}\n")
    print(f"PFD v{result['pfd_version']}: top/bottom/entry HMACs OK")
    print("File HMACs OK: " + ", ".join(result["verified"]))
    if result["skipped"]:
        print("Unavailable file checks: " + "; ".join(result["skipped"]))
    print(f"SAVEDATA.DAT: {result['size']} bytes; SHA256 {result['sha256']}")
    print(f"HDD0={result['hdd0']}\nSLOT={result['slot']}")


if __name__ == "__main__":
    main()
