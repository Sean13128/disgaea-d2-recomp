#!/usr/bin/env python3
"""Synthetic PFD fixtures and importer regressions; no game dump writes.

.venv/bin/python codex/AC.save-import-test.py
Optional AC_PFDTOOL points at a scratch build of flatz's pfdtool for an
independent decrypt/encrypt cross-check. Fixtures never contain console keys.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from Crypto.Cipher import AES

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("d2_save_import", ROOT / "tools/d2_save_import.py")
save = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = save
spec.loader.exec_module(save)


def fixture(source, payload=None, version=4, capacity=5, metadata=None, icon=None):
    source.mkdir(parents=True)
    payload = payload if payload is not None else (bytes(range(256)) * 6000)[:save.EXPECTED_SIZE]
    sfo = {}
    save.set_sfo(sfo, "CATEGORY", 0x204, b"SD\0", 4)
    save.set_sfo(sfo, "SAVEDATA_DIRECTORY", 0x204, b"NPUB31321_NORMAL_04\0", 32)
    save.set_sfo(sfo, "*SAVEDATA.DAT", 0x404, struct.pack("<I", 1), 4)
    save.set_sfo(sfo, "ACCOUNT_ID", 4, b"0123456789abcdef", 16)
    save.set_sfo(sfo, "PARAMS", 4, bytes(range(256)) * 4, 1024)
    save.set_sfo(sfo, "TITLE", 0x204, b"Disgaea D2\0", 128)
    if metadata is not None:
        sfo = save.parse_sfo(metadata)
        save.set_sfo(sfo, "SAVEDATA_DIRECTORY", 0x204, b"NPUB31321_NORMAL_04\0", 32)
    sfo_data = save.encode_sfo(sfo)
    key = bytes(range(64))
    hash_key = save.secure_hash_key(save.SECURE_FILE_ID)
    encrypted = save.crypt_file(payload.ljust((len(payload)+15) & ~15, b"\0"), key, encrypt=True)
    files = {"PARAM.SFO": sfo_data, "SAVEDATA.DAT": encrypted,
             "ICON0.PNG": icon if icon is not None else b"synthetic icon"}
    reserved = 8
    raw_entries = []
    heads = [reserved] * capacity
    for name in ("PARAM.SFO", "SAVEDATA.DAT"):
        name_hash = 0
        for c in name.encode():
            name_hash = (31 * name_hash + c) & 0xffffffffffffffff
        bucket = name_hash % capacity
        entry = bytearray(272)
        struct.pack_into(">Q", entry, 0, heads[bucket])
        heads[bucket] = len(raw_entries)
        entry[8:8+len(name)] = name.encode()
        if name == "SAVEDATA.DAT":
            entry[80:144] = AES.new(save.SYSCON_KEY, AES.MODE_CBC, hash_key[:16]).encrypt(key)
            entry[144:164] = save.sha1_hmac(hash_key, encrypted)
            size = len(payload)
        else:
            entry[144:164] = save.sha1_hmac(save.SFO_KEY, sfo_data)
            entry[204:224] = save.sha1_hmac(save.AUTH_ID, sfo_data)
            size = len(sfo_data)
        struct.pack_into(">Q", entry, 264, size)
        raw_entries.append(entry)
    table = struct.pack(">QQQ", capacity, reserved, 2) + b"".join(struct.pack(">Q", x) for x in heads)
    original_hash_key = bytes(range(20))
    real_hash_key = save.sha1_hmac(save.KEYGEN_KEY, original_hash_key) if version == 4 else original_hash_key
    entry_sigs = b""
    for index in heads:
        chain = b""
        while index < reserved:
            entry = raw_entries[index]
            chain += entry[8:73] + entry[80:272]
            index = struct.unpack_from(">Q", entry)[0]
        entry_sigs += save.sha1_hmac(real_hash_key, chain)
    signature = (save.sha1_hmac(real_hash_key, entry_sigs)
                 + save.sha1_hmac(real_hash_key, table) + original_hash_key + bytes(4))
    header_iv = bytes(range(16))
    pfd = (struct.pack(">QQ", 0x50464442, version) + header_iv
           + AES.new(save.SYSCON_KEY, AES.MODE_CBC, header_iv).encrypt(signature)
           + table + b"".join(raw_entries) + bytes((reserved-2)*272) + entry_sigs)
    files["PARAM.PFD"] = pfd.ljust(32768, b"\0")
    for name, data in files.items():
        (source / name).write_bytes(data)
    return payload


def digests(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="AC-test-", dir="/Volumes/Data/ai-tmp/codex")
        self.root = Path(self.temp.name)
        self.source = self.root / "NPUB31321_NORMAL_04"
        self.payload = fixture(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_versions_and_collision_chain(self):
        for version in (3, 4):
            source = self.root / str(version)
            # Capacity 1 forces both entries into one linked-list bucket.
            fixture(source, version=version, capacity=1)
            files, _, _, checks = save.convert(source)
            self.assertEqual(files["SAVEDATA.DAT"], self.payload)
            self.assertEqual(len(files["SAVEDATA.DAT"]), 1498152)
            self.assertEqual(checks["pfd_version"], version)

    def test_free_slot_and_metadata(self):
        hdd0 = self.root / "hdd0"
        existing = hdd0 / "home/00000001/savedata/NPUB31321_NORMAL_00"
        existing.mkdir(parents=True)
        (existing / "sentinel").write_bytes(b"keep me")
        before = digests(self.source)
        result = save.import_save(self.source, hdd0)
        self.assertEqual(result["slot"], "NPUB31321_NORMAL_01")
        self.assertEqual(digests(self.source), before)
        self.assertEqual((existing / "sentinel").read_bytes(), b"keep me")
        output = existing.parent / result["slot"]
        self.assertEqual((output / "SAVEDATA.DAT").read_bytes(), self.payload)
        self.assertFalse((output / "PARAM.PFD").exists())
        self.assertEqual((output / "ICON0.PNG").read_bytes(), b"synthetic icon")
        sfo = save.parse_sfo((output / "PARAM.SFO").read_bytes())
        self.assertEqual(sfo["SAVEDATA_DIRECTORY"].value, b"NPUB31321_NORMAL_01\0")
        self.assertEqual(sfo["PARAMS"].value, bytes(range(256)) * 4)
        self.assertEqual(sfo["ACCOUNT_ID"].value, b"0123456789abcdef")
        self.assertEqual(sfo["*SAVEDATA.DAT"].value, b"\x01\0\0\0")

    def test_console_fixed_width_strings(self):
        sfo = save.parse_sfo((self.source / "PARAM.SFO").read_bytes())
        save.set_sfo(sfo, "SAVEDATA_DIRECTORY", 0x204, b"NPUB31321_NORMAL_04".ljust(32, b"\0"), 32)
        source = self.root / "fixed-width"
        fixture(source, metadata=save.encode_sfo(sfo))
        self.assertEqual(save.convert(source)[0]["SAVEDATA.DAT"], self.payload)

    def test_default_is_copy(self):
        # Use a temporary stand-in project to avoid testing against live saves.
        old_root = save.ROOT
        save.ROOT = self.root / "project"
        native = save.ROOT / "port/hdd0/home/00000001/savedata/NPUB31321_NORMAL_00"
        native.mkdir(parents=True)
        (native / "sentinel").write_bytes(b"original")
        try:
            before = digests(save.ROOT / "port/hdd0")
            result = save.import_save(self.source)
            self.assertEqual(result["slot"], "NPUB31321_NORMAL_01")
            self.assertEqual(digests(save.ROOT / "port/hdd0"), before)
            self.assertTrue(Path(result["hdd0"]).is_relative_to(save.ROOT / "port/runs"))
            self.assertEqual((Path(result["hdd0"]) / native.relative_to(save.ROOT / "port/hdd0") / "sentinel").read_bytes(), b"original")
        finally:
            save.ROOT = old_root

    def test_tampered_ciphertext(self):
        path = self.source / "SAVEDATA.DAT"
        data = bytearray(path.read_bytes()); data[12345] ^= 1; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "hash mismatch: SAVEDATA.DAT"):
            save.import_save(self.source, self.root / "target")
        self.assertFalse((self.root / "target").exists())

    def test_tampered_sfo(self):
        path = self.source / "PARAM.SFO"
        data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "hash mismatch: PARAM.SFO"):
            save.convert(self.source)

    def test_tampered_entry_or_table(self):
        path = self.source / "PARAM.PFD"
        original = path.read_bytes()
        for offset in (130, 120+5*8+80, 120+5*8+8*272):
            data = bytearray(original); data[offset] ^= 1; path.write_bytes(data)
            with self.assertRaises(ValueError):
                save.convert(self.source)

    def test_truncated_or_unpadded_files(self):
        data = (self.source / "PARAM.PFD").read_bytes()
        for length in (0, 32, 120, 2000):
            with self.assertRaises(ValueError):
                save.parse_pfd(data[:length])
        path = self.source / "SAVEDATA.DAT"
        path.write_bytes(path.read_bytes()[:-8])
        with self.assertRaisesRegex(ValueError, "protected size"):
            save.convert(self.source)

    def test_reject_dump_source_and_symlink_targets(self):
        with self.assertRaisesRegex(ValueError, "read-only game dump"):
            save.import_save(self.source, save.ROOT / "Disgaea D2 A Brighter Darkness - [BLUS31313]/scratch")
        with self.assertRaisesRegex(ValueError, "overlaps the import source"):
            save.import_save(self.source, self.source)
        target = self.root / "target"
        target.mkdir(); (target / "home").symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            save.import_save(self.source, target)

    def test_reject_source_symlink(self):
        path = self.source / "ICON0.PNG"
        path.unlink(); path.symlink_to(self.source / "PARAM.SFO")
        with self.assertRaisesRegex(ValueError, "unsafe file"):
            save.convert(self.source)

    def test_all_slots_full(self):
        target = self.root / "hdd0"
        base = target / "home/00000001/savedata"
        for i in range(100):
            (base / f"NPUB31321_NORMAL_{i:02d}").mkdir(parents=True)
        before = digests(target)
        with self.assertRaisesRegex(ValueError, "no free"):
            save.import_save(self.source, target)
        self.assertEqual(before, digests(target))
        self.assertEqual(len(list(base.iterdir())), 100)

    @unittest.skipUnless(os.getenv("AC_PFDTOOL"), "set AC_PFDTOOL for independent flatz C cross-check")
    def test_flatz_c_round_trip(self):
        binary = os.environ["AC_PFDTOOL"]
        (self.root / "global.conf").write_text(
            "[global]\nauthentication_id=" + save.AUTH_ID.hex() +
            "\nsyscon_manager_key=" + save.SYSCON_KEY.hex() +
            "\nkeygen_key=" + save.KEYGEN_KEY.hex() +
            "\nsavegame_param_sfo_key=" + save.SFO_KEY.hex() + "\n")
        (self.root / "games.conf").write_text("[BLUS31313]\nsecure_file_id:SAVEDATA.DAT=" + save.SECURE_FILE_ID.hex() + "\n")
        c_source = self.root / "c-reference"
        shutil.copytree(self.source, c_source)
        cipher_before = (c_source / "SAVEDATA.DAT").read_bytes()
        for action in ("--decrypt", "--encrypt"):
            process = subprocess.run([binary, "-p", "-g", "BLUS31313", action, str(c_source), "SAVEDATA.DAT"],
                                     cwd=self.root, capture_output=True, text=True, check=True)
            self.assertNotIn("Error", process.stdout + process.stderr)
            self.assertEqual((c_source / "SAVEDATA.DAT").read_bytes(),
                             self.payload if action == "--decrypt" else cipher_before)
        self.assertEqual(save.convert(c_source)[0]["SAVEDATA.DAT"], self.payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
