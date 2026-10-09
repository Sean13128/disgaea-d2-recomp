"""Private controller input validation and audit; no native gameplay claim."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).parents[2]/'tools'))
from d2_appearance_input import press

class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='d2-input-',dir=os.path.realpath(tempfile.gettempdir()));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'process.json').write_text(json.dumps(dict(pid=os.getpid(),started=time.time()-1)))
        (self.root/'stage-snapshot.json').write_text(json.dumps(dict(mode='isolated-runtime-experiment')))
        (self.root/'pad.txt').write_text('')
        (self.root/'planned-input.json').write_text(json.dumps(dict(last_scripted_input=0)))
    def test_press_is_bounded_logged_and_never_overwrites_pending_input(self):
        event=press(self.root,0x4000)
        self.assertEqual((self.root/'pad.txt').read_text(),'0x4000 4\n')
        self.assertEqual(json.loads((self.root/'input-presses.jsonl').read_text()),event)
        with self.assertRaisesRegex(ValueError,'not consumed'):press(self.root,0x40)
        self.assertEqual((self.root/'pad.txt').read_text(),'0x4000 4\n')
        for mask,polls in ((True,4),(0,4),(65536,4),(64,0),(64,31)):
            with self.assertRaises(ValueError):press(self.root,mask,polls)
    def test_future_script_and_bad_audit_do_not_queue(self):
        (self.root/'planned-input.json').write_text(json.dumps(dict(last_scripted_input=60)))
        with self.assertRaisesRegex(ValueError,'still scheduled'):press(self.root,64)
        self.assertEqual((self.root/'pad.txt').read_text(),'')
        (self.root/'planned-input.json').write_text(json.dumps(dict(last_scripted_input=0)))
        outside=self.root/'outside';outside.write_text('unchanged');(self.root/'input-presses.jsonl').symlink_to(outside)
        with self.assertRaises(ValueError):press(self.root,64)
        self.assertEqual(outside.read_text(),'unchanged');self.assertEqual((self.root/'pad.txt').read_text(),'')

    def test_terminal_dead_process_and_symlink_do_not_queue(self):
        (self.root/'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'terminal'):press(self.root,64)
        (self.root/'result.json').unlink()
        (self.root/'process.json').write_text(json.dumps(dict(pid=2147483647,started=time.time()-1)))
        with self.assertRaisesRegex(ValueError,'no longer live'):press(self.root,64)
        self.assertEqual((self.root/'pad.txt').read_text(),'')
        (self.root/'process.json').write_text(json.dumps(dict(pid=os.getpid(),started=time.time()-1)))
        pad=self.root/'pad.txt';pad.unlink();other=self.root/'other';other.write_bytes(b'unchanged');pad.symlink_to(other)
        with self.assertRaises(ValueError):press(self.root,64)
        self.assertEqual(other.read_bytes(),b'unchanged')
if __name__=='__main__':unittest.main()
