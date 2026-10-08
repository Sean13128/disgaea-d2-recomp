"""Normal-play profile/input isolation and shared lock guards; no game execution."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import d2_appearance_run as validation
import d2_appearance_play as launcher
import test_d2_appearance_run as fixtures


class PlayTests(unittest.TestCase):
    def setUp(self):
        fixtures.AppearanceRunTests.setUp(self)
        data=json.loads(self.stage.read_text());data.update(selection_mode='renderer-only',visual_class_id=900)
        self.stage.write_text(json.dumps(data))

    def test_normal_play_keeps_inputs_and_preserves_private_files(self):
        proc=MagicMock(pid=123);proc.wait.return_value=0
        dirty=dict(D2_WARP_DELAY_SECONDS='85',D2_APPEARANCE_TEST_SEQUENCE='1:original',D2_WARP_STAGE='1',D2_WARP_TRACE='1',D2_HUB_CHARACTER='30',PAD_NO_KEYBOARD='1',PAD_SCRIPT='bad',SDL_AUDIODRIVER='dummy',
                   PS3RECOMP_METAL_FRAME_DUMP='/unwanted/frames')
        with patch.object(validation,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(os.environ,dirty),patch.object(launcher.subprocess,'Popen',return_value=proc) as spawn:
            result=launcher.play(self.stage,self.exe,self.elf,self.root/'play')
        env=spawn.call_args.kwargs['env']
        for key in dirty:self.assertNotIn(key,env)
        self.assertEqual(env['PS3_HDD0_ROOT'],self.roots['PS3_HDD0_ROOT'])
        self.assertEqual(env['D2_APPEARANCE_MANIFEST'],str(self.root/'play/stage-snapshot.json'))
        self.assertEqual(env['D2_APPEARANCE_PERSIST'],'1')
        self.assertEqual(env['D2_APPEARANCE_PERSIST_PATH'],str(self.stage))
        self.assertEqual(env['D2_SETTINGS_PATH'],str(self.root/'appearance-settings.json'))
        self.assertEqual((self.root/'hdd0/save').read_bytes(),b'private save')
        self.assertEqual((self.root/'hdd1/cache').read_bytes(),b'previous cache')
        self.assertFalse(result['gameplay_validated'])
        proc.wait.assert_called_once_with(timeout=None)

    def test_session_only_overrides_inherited_persistence(self):
        proc=MagicMock(pid=123);proc.wait.return_value=0
        with patch.object(validation,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(os.environ,{'D2_APPEARANCE_PERSIST':'1','D2_APPEARANCE_PERSIST_PATH':'/unrelated/file'}), \
             patch.object(launcher.subprocess,'Popen',return_value=proc) as spawn:
            launcher.play(self.stage,self.exe,self.elf,self.root/'session-play',session_only=True)
        self.assertEqual(spawn.call_args.kwargs['env']['D2_APPEARANCE_PERSIST'],'0')
        self.assertEqual(spawn.call_args.kwargs['env']['D2_APPEARANCE_PERSIST_PATH'],str(self.stage))

    def test_profile_lock_blocks_both_launchers_and_releases(self):
        with patch.object(validation,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()):
            with validation.profile_lock(self.stage):
                for call in (launcher.play,validation.run):
                    with self.assertRaisesRegex(ValueError,'already in use'):
                        call(self.stage,self.exe,self.elf,self.root/'blocked')
            self.assertFalse((self.root/'blocked').exists())
            with validation.profile_lock(self.stage):pass

    def test_child_retains_lock_after_launcher_descriptor_closes(self):
        with validation.profile_lock(self.stage) as descriptor:
            child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'],pass_fds=(descriptor,))
        try:
            with self.assertRaisesRegex(ValueError,'already in use'):
                with validation.profile_lock(self.stage):pass
        finally:
            child.terminate();child.wait(timeout=5)
        with validation.profile_lock(self.stage):pass

    def test_bad_profile_or_output_cannot_launch(self):
        with self.assertRaises(ValueError):launcher.play(self.stage,self.exe,self.elf,self.root/'output')
        with patch.object(validation,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()):
            with self.assertRaises(ValueError):launcher.play(self.stage,self.exe,self.elf,self.root/'hdd1/run')
        self.assertFalse((self.root/'hdd1/run').exists())
        data=json.loads(self.stage.read_text());data['selection_mode']='selector';self.stage.write_text(json.dumps(data))
        with patch.object(validation,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(ValueError,'renderer-only'):
                launcher.play(self.stage,self.exe,self.elf,self.root/'legacy')
        self.assertFalse((self.root/'legacy').exists())


if __name__=='__main__':unittest.main()
