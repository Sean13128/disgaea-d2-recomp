"""Persistent renderer choice keeps unrelated bindings and save files intact."""
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_choice import select, choice_lock


class ChoiceTests(unittest.TestCase):
    def test_roundtrip_preserves_other_bindings_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'stage.json';save=root/'save';save.write_bytes(b'original save')
            entries=[dict(class_id=i,selection_mode='renderer-only',visual_class_id=i+900) for i in (30,410)]
            data=dict(mode='isolated-runtime-experiment',appearances=entries,unrelated={'keep':123})
            path.write_text(json.dumps(data))
            select(path,False,30)
            actual=json.loads(path.read_text());self.assertFalse(actual['appearances'][0]['enabled'])
            self.assertEqual(actual['appearances'][1],entries[1]);self.assertEqual(actual['unrelated'],data['unrelated'])
            select(path,True,30);self.assertTrue(json.loads(path.read_text())['appearances'][0]['enabled'])
            self.assertEqual(save.read_bytes(),b'original save')
            self.assertEqual(list(root.glob('.appearance-choice-*')),[])

    def test_invalid_legacy_or_ambiguous_choice_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stage.json'
            for entries in [[dict(class_id=30,selection_mode='selector',visual_class_id=900)],
                            [dict(class_id=i,selection_mode='renderer-only',visual_class_id=900+i) for i in (30,410)]]:
                path.write_text(json.dumps(dict(mode='isolated-runtime-experiment',appearances=entries)))
                before=path.read_bytes()
                with self.assertRaises(ValueError):select(path,False)
                self.assertEqual(path.read_bytes(),before)

    def test_cli_obeys_shared_choice_lock_and_rejects_symlink_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'stage.json'
            data=dict(mode='isolated-runtime-experiment',class_id=30,selection_mode='renderer-only',visual_class_id=900)
            path.write_text(json.dumps(data))
            script="import sys;sys.path.insert(0,sys.argv[1]);from d2_appearance_choice import select;print('ready',flush=True);select(sys.argv[2],False)"
            with choice_lock(path):
                proc=subprocess.Popen([sys.executable,'-c',script,str(Path(__file__).parents[2]/'tools'),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    self.assertEqual(proc.stdout.readline().strip(),'ready')
                    with self.assertRaises(subprocess.TimeoutExpired):proc.wait(timeout=0.1)
                    self.assertEqual(json.loads(path.read_text()),data)
                except BaseException:proc.kill();proc.wait();raise
            proc.communicate(timeout=3);self.assertEqual(proc.returncode,0)
            self.assertFalse(json.loads(path.read_text())['enabled'])
            lock=root/'.appearance-choice.lock';lock.unlink();outside=root/'outside';outside.write_bytes(b'unchanged');lock.symlink_to(outside)
            with self.assertRaises(OSError):select(path,True)
            self.assertEqual(outside.read_bytes(),b'unchanged')


if __name__=='__main__':unittest.main()
