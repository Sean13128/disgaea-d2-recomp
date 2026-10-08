"""Isolated runner guards and cache preservation; no game execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import d2_appearance_run as runner


class AppearanceRunTests(unittest.TestCase):
    def test_normal_startup_removes_warp_leader_and_movie_skip(self):
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        inherited={'D2_WARP_STAGE':'1','D2_WARP_TRACE':'1','D2_HUB_CHARACTER':'30',
                   'D2_WARP_DELAY_SECONDS':'65','D2_MOVIE_SKIP':'1','D2_APPEARANCE_TEST_SEQUENCE':'[]'}
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(runner.os.environ,inherited), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'normal-output',scene='normal')
        env=spawn.call_args.kwargs['env']
        for key in inherited:self.assertNotIn(key,env)
        self.assertEqual(result['scene'],'normal')
        self.assertEqual(env['PS3_HDD0_ROOT'],self.roots['PS3_HDD0_ROOT'])
        for option in [{'hub_character':30},{'battle_after':65},{'live_sequence':'65:original'}]:
            with self.assertRaises(ValueError):
                runner.run(self.stage,self.exe,self.elf,self.root/'invalid-normal',scene='normal',**option)
        self.assertFalse((self.root/'invalid-normal').exists())

    def test_hub_scene_removes_inherited_warp_and_retains_readonly_trace(self):
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(runner.os.environ,{'D2_WARP_STAGE':'999','D2_APPEARANCE_TEST_SEQUENCE':'bad inherited test','D2_APPEARANCE_PERSIST':'1','D2_APPEARANCE_PERSIST_PATH':'/unrelated/file','D2_WARP_DELAY_SECONDS':'85'}), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'hub-output',scene='hub')
        env=spawn.call_args.kwargs['env']
        self.assertNotIn('D2_WARP_STAGE',env)
        self.assertNotIn('D2_APPEARANCE_TEST_SEQUENCE',env)
        self.assertNotIn('D2_APPEARANCE_PERSIST',env)
        self.assertNotIn('D2_APPEARANCE_PERSIST_PATH',env)
        self.assertNotIn('D2_WARP_DELAY_SECONDS',env)
        self.assertEqual(env['D2_WARP_TRACE'],'1')
        self.assertEqual(result['scene'],'hub')
        self.assertEqual((self.root/'hdd0/save').read_bytes(),b'private save')
        with self.assertRaisesRegex(ValueError,'Scene'):
            runner.run(self.stage,self.exe,self.elf,self.root/'bad-scene',scene='unknown')
        self.assertFalse((self.root/'bad-scene').exists())
    def test_hub_character_requires_hub_and_explicit_valid_id(self):
        for scene,value in [('battle',30),('hub',0),('hub',32768),('hub',True)]:
            with self.assertRaisesRegex(ValueError,'Hub character'):
                runner.run(self.stage,self.exe,self.elf,self.root/'invalid-character',scene=scene,hub_character=value)
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(runner.os.environ,{'D2_HUB_CHARACTER':'410'}), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'hub-character',scene='hub',hub_character=30)
        self.assertEqual(spawn.call_args.kwargs['env']['D2_HUB_CHARACTER'],'30')
        self.assertEqual(result['hub_character'],30)
    def test_live_sequence_is_bounded_hub_only_and_explicit(self):
        for value in ('nan:first','60:first','2:first,1:original','1:../bad',','.join(f'{i}:first' for i in range(17))):
            with self.assertRaises(ValueError):runner.parse_live_sequence(value,60,'hub')
        with self.assertRaises(ValueError):runner.parse_live_sequence('1:first',60,'battle')
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(runner.os.environ,{'D2_APPEARANCE_TEST_SEQUENCE':'untrusted inherited'}), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'live-output',scene='hub',live_sequence='1:first,2:original',persist_choice=True)
        expected=[dict(second=1.0,token='first'),dict(second=2.0,token='')]
        self.assertEqual(json.loads(spawn.call_args.kwargs['env']['D2_APPEARANCE_TEST_SEQUENCE']),expected)
        self.assertEqual(result['live_sequence'],expected)
        plan=json.loads((self.root/'live-output/planned-input.json').read_text())
        self.assertEqual(plan['last_scripted_input'],14.0)
        self.assertTrue(result['persist_choice'])
        self.assertEqual(spawn.call_args.kwargs['env']['D2_APPEARANCE_PERSIST'],'1')
        self.assertEqual(spawn.call_args.kwargs['env']['D2_APPEARANCE_PERSIST_PATH'],str(self.stage))

    def test_delayed_battle_requires_hub_and_an_explicit_bounded_deadline(self):
        for scene,value in [('battle',65),('hub',0),('hub',80),('hub',True)]:
            with self.assertRaisesRegex(ValueError,'Delayed battle'):
                runner.run(self.stage,self.exe,self.elf,self.root/'bad-delay',scene=scene,battle_after=value)
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'delayed-battle',scene='hub',hub_character=30,battle_after=65)
        env=spawn.call_args.kwargs['env']
        self.assertEqual(env['D2_WARP_STAGE'],'1');self.assertEqual(env['D2_WARP_DELAY_SECONDS'],'65')
        self.assertEqual(env['D2_HUB_CHARACTER'],'30');self.assertEqual(result['battle_after'],65)

    def test_trace_override_is_bounded_and_does_not_change_binding(self):
        for value in (0,-1,100000,True,'10030'):
            with self.assertRaisesRegex(ValueError,'Trace resource'):
                runner.run(self.stage,self.exe,self.elf,self.root/'invalid-trace',trace_resource=value)
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        before=self.stage.read_bytes()
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.dict(runner.os.environ,{'D2_APPEARANCE_TRACE':'999'}), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'portrait-trace',trace_resource=10030)
        self.assertEqual(spawn.call_args.kwargs['env']['D2_APPEARANCE_TRACE'],'10030')
        self.assertEqual(result['trace_resource'],10030)
        self.assertEqual(result['runner_sha256'],hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.root/'portrait-trace/process.json').read_text())['runner_sha256'],result['runner_sha256'])
        self.assertEqual(self.stage.read_bytes(),before)
        self.assertEqual(json.loads((self.root/'portrait-trace/stage-snapshot.json').read_text())['new_resource'],900)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='d2-run-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.roots={k:str(self.root/n) for k,n in [('PS3_VFS_ROOT','content'),
            ('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]}
        for path in self.roots.values():Path(path).mkdir()
        (self.root/'hdd1/cache').write_bytes(b'previous cache')
        (self.root/'hdd0/save').write_bytes(b'private save')
        self.stage=self.root/'stage.json'
        self.stage.write_text(json.dumps(dict(mode='isolated-runtime-experiment',new_resource=900,
            runtime_environment=self.roots,save_patch=dict(slot='private-slot'))))
        self.elf=self.root/'elf';self.elf.write_bytes(b'fixture ELF')
        self.exe=self.root/'exe';self.exe.write_bytes(b'fixture executable')

    def test_fresh_cache_preserves_old_bytes_and_private_roots(self):
        proc=MagicMock(pid=12345);proc.wait.return_value=0
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.object(runner.subprocess,'Popen',return_value=proc) as spawn:
            result=runner.run(self.stage,self.exe,self.elf,self.root/'output',fresh_cache=True)
        self.assertTrue(result['fresh_cache'])
        self.assertEqual((self.root/'output/cache-before-run/cache').read_bytes(),b'previous cache')
        self.assertEqual(list((self.root/'hdd1').iterdir()),[])
        self.assertEqual((self.root/'hdd0/save').read_bytes(),b'private save')
        env=spawn.call_args.kwargs['env']
        self.assertEqual(env['PS3_HDD1_ROOT'],self.roots['PS3_HDD1_ROOT'])
        self.assertEqual(env['PS3_SAVEDATA_DIR'],'private-slot')
        snapshot=self.root/'output/stage-snapshot.json'
        self.assertEqual(env['D2_APPEARANCE_MANIFEST'],str(snapshot))
        original=snapshot.read_bytes();self.stage.write_text('{}')
        self.assertEqual(snapshot.read_bytes(),original)
        self.assertEqual(result['manifest_sha256'],hashlib.sha256(original).hexdigest())
        self.assertFalse(result['gameplay_validated'])
        self.assertEqual(result['trace_resource'],900)
        self.assertEqual(env['D2_APPEARANCE_TRACE'],'900')

    def test_wrong_elf_or_root_cannot_move_the_cache(self):
        with self.assertRaises(ValueError):runner.run(self.stage,self.exe,self.elf,self.root/'output',fresh_cache=True)
        data=json.loads(self.stage.read_text());data['runtime_environment']['PS3_HDD1_ROOT']=str(self.root/'hdd0')
        self.stage.write_text(json.dumps(data))
        with self.assertRaises(ValueError):runner.run(self.stage,self.exe,self.elf,self.root/'output',fresh_cache=True)
        self.assertEqual((self.root/'hdd1/cache').read_bytes(),b'previous cache')
        self.assertFalse((self.root/'output').exists())

    def test_capture_budget_and_nested_cache_output_fail_before_mutation(self):
        with patch.object(runner,'ELF_140_SHA256',hashlib.sha256(self.elf.read_bytes()).hexdigest()), \
             patch.object(runner.shutil,'disk_usage',return_value=MagicMock(free=3*1024**3)):
            with self.assertRaisesRegex(ValueError,'capture budget'):
                runner.run(self.stage,self.exe,self.elf,self.root/'too-large',duration=600,frame_every=1,fresh_cache=True)
            with self.assertRaisesRegex(ValueError,'overlaps'):
                runner.run(self.stage,self.exe,self.elf,self.root/'hdd1/output',fresh_cache=True)
        self.assertEqual((self.root/'hdd1/cache').read_bytes(),b'previous cache')
        self.assertFalse((self.root/'too-large').exists())
        self.assertFalse((self.root/'hdd1/output').exists())


if __name__=='__main__':unittest.main()
