#!/usr/bin/env python3
"""Independent Crypto fixtures for SDK EDAT modes used by D2; corruptions fail."""
import os, ctypes, hashlib, hmac, pathlib, struct, subprocess, tempfile
from Crypto.Cipher import AES
from Crypto.Hash import CMAC
ROOT = pathlib.Path(__file__).resolve().parents[2]
KEY = bytes(range(16))
OMAC2 = bytes.fromhex('6ba52976efda16ef3c339fb2971e256b')
OMAC3 = bytes.fromhex('9b515feacf75064981aa604d91a54e97')
WRAP = [bytes.fromhex('be959ca8308defa2e5e180c63712a9ae'), bytes.fromhex('4ca9c14b01c95309969bec68aa0bc081')]
ZERO = bytes(16)
def cmac(k, b):
    c = CMAC.new(k, ciphermod=AES); c.update(b); return c.digest()
def xor(a, b): return bytes(x ^ y for x, y in zip(a, b))
def unwrap(k, v): return AES.new(WRAP[v == 4], AES.MODE_CBC, ZERO).decrypt(k)
def fixture(path, flags, version=3):
    payload = b'D2 flag test'
    hdr = bytearray(0x100)
    struct.pack_into('>4sIII', hdr, 0, b'NPD\0', version, 3, 0)
    hdr[16:64] = b'UP1063-NPUB31321_00-ADTEST0000000000'.ljust(48, b'\0')
    hdr[64:80] = bytes(range(16, 32))
    hdr[80:96] = cmac(OMAC3, hdr[16:64] + path.name.encode())
    hdr[96:112] = cmac(xor(KEY, OMAC2), hdr[:96])
    struct.pack_into('>IIQ', hdr, 128, flags, 0x4000, len(payload))
    block_key = AES.new(KEY, AES.MODE_ECB).encrypt(hdr[96:108] + bytes(4))
    hash_key = AES.new(KEY, AES.MODE_ECB).encrypt(block_key) if flags & 0x10 else block_key
    if flags & 8:
        block_key = unwrap(block_key, version); hash_key = unwrap(hash_key, version)
    padded = payload.ljust(16, b'\0')
    encrypted = padded if flags & 2 else AES.new(block_key, AES.MODE_CBC, hdr[64:80]).encrypt(padded)
    if not flags & 0x10: digest = cmac(hash_key, encrypted)
    else: digest = hmac.new(hash_key + bytes(4) if flags & 0x20 else hash_key, encrypted, hashlib.sha1).digest()
    if flags & 0x20:
        second = digest[16:20] + bytes(12)
        metadata = xor(digest[:16], second) + second
    else: metadata = digest[:16]
    header_key = unwrap(KEY, version) if flags & 8 else KEY
    hdr[144:160] = cmac(header_key, metadata)
    hdr[160:176] = cmac(header_key, hdr[:160])
    raw = bytes(hdr) + metadata + encrypted
    path.write_bytes(raw)
    return raw, payload
with tempfile.TemporaryDirectory(prefix='AD-edat.', dir=os.environ.get('D2_TEST_TMPDIR')) as scratch:
    scratch = pathlib.Path(scratch)
    libpath = scratch/'edat.dylib'
    subprocess.run(['clang', '-shared', '-fPIC', str(pathlib.Path(os.environ['PS3RECOMP_DIR'])/'libs/filesystem/edat.c'), '-o', str(libpath)], check=True)
    lib = ctypes.CDLL(str(libpath))
    key = (ctypes.c_ubyte*16).from_buffer_copy(KEY)
    assert lib.edat_selftest() == 0
    checks = 0
    for version in (3, 4):
        for flags in (0, 2, 0x0c, 0x1c, 0x3c, 0x3e):
            path = scratch/f'flag-v{version}-{flags:x}.edat'; out = scratch/'plain'
            raw, payload = fixture(path, flags, version)
            decrypt = lambda: lib.edat_decrypt_file_key(str(path).encode(), str(out).encode(), key)
            assert decrypt() == 0 and out.read_bytes() == payload
            checks += 1
            for offset in (80, 96, 160, 256, len(raw)-1):
                bad = bytearray(raw); bad[offset] ^= 1; path.write_bytes(bad)
                assert decrypt() != 0
                checks += 1
            path.write_bytes(raw)
            wrong = (ctypes.c_ubyte*16)()
            assert lib.edat_decrypt_file_key(str(path).encode(), str(out).encode(), wrong) != 0
            checks += 1
    print(f'PASS: {checks} EDAT checks (v3/v4, CMAC/HMAC16/HMAC20, CBC/plaintext, corruption/wrong key)')
