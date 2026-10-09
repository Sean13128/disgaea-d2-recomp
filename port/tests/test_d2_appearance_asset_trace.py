"""Resource loading is distinguished from binding and visible acceptance."""
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_appearance_asset_trace import summarize,inspect

LOG='''[sys overlay/metal] captured frame 240 overlay=0
[D2 appearance] request manager=01554708 resource=10030 caller=000ec098
[D2 appearance] file_read name=anm10030.lzs bytes=26389 destination=4573b780 result=1 caller=00181d28
[D2 appearance] manager=01554708 slot=1 resource=10030 state=4 refs=1
[D2 appearance] model_select model=00070000 library=8000 variant=0 caller=0001234
[D2 appearance] texture_bind model=00071000 group=0 flags=1 resource=10031 caller=0001234
[D2 appearance] texture_bind model=00070000 group=0 flags=1 resource=10030 caller=0001234
[D2 appearance] model_select model=00070000 library=10030 variant=8010 caller=0001234
[D2 appearance] model_select model=00071000 library=8010 variant=0 caller=0001234
'''
class AssetTraceTests(unittest.TestCase):
    def test_load_bind_and_tag_evidence_have_separate_scope(self):
        meta={'blocks':[{'resource_id':10030,'tables':{'tags':{'records':[[8010,0]]}}}]}
        report=summarize(LOG,10030,meta)
        self.assertTrue(report['requests_observed']);self.assertTrue(report['file_read_observed'])
        self.assertTrue(report['bank_states_observed']);self.assertTrue(report['texture_binding_observed'])
        self.assertTrue(report['library_selection_observed'])
        self.assertFalse(report['rendered_coverage_validated']);self.assertEqual(report['observed_models'],['00070000'])
        clips=[e for e in report['observations'] if e['kind']=='model_select']
        self.assertEqual(len(clips),1);self.assertTrue(clips[0]['variant_present_in_supplied_resource'])
        self.assertTrue(all(e['previous_capture_frame']==240 for e in report['observations']))
        loaded=summarize(LOG.split('[D2 appearance] texture_bind')[0],10030)
        self.assertTrue(loaded['requests_observed']);self.assertFalse(loaded['texture_binding_observed'])
    def test_unknown_resource_and_malformed_fields_do_not_claim_acceptance(self):
        self.assertEqual(summarize(LOG,31)['observations'],[])
        mapped=summarize('[D2 appearance] illustration unit=00020000 donor=10030 resource=10901 caller=00151fec',10901)
        self.assertTrue(mapped['illustration_routing_observed'])
        self.assertFalse(mapped['library_selection_observed'])
        face=summarize('[D2 appearance] face_cell unit=00020000 donor=30 resource=901 x=384 y=0 atlas=480x3840 caller=0015ae54',901)
        self.assertTrue(face['face_routing_observed']);self.assertFalse(face['library_selection_observed'])
        self.assertEqual(summarize('[D2 appearance] request resource=invalid',31)['observations'],[])
        for resource in (0,100000,True,'31'):
            with self.assertRaises(ValueError):summarize(LOG,resource)
    def test_compound_file_ids_do_not_become_animation_block_ids(self):
        meta={'blocks':[{'resource_id':30,'tables':{'tags':{'records':[[6001,0]]}}}]}
        report=summarize('[D2 appearance] request resource=40030\n[D2 appearance] model_select model=00100000 library=40030 variant=6001',40030,meta)
        self.assertTrue(report['requests_observed']);self.assertTrue(report['library_selection_observed'])
        self.assertEqual(report['container_resource_ids'],[30])
        self.assertFalse(report['metadata_resource_matches_filter']);self.assertIsNone(report['animation_tags'])
        self.assertIsNone(report['observations'][-1]['variant_present_in_supplied_resource'])
        self.assertEqual(summarize('[D2 appearance] request resource=99997',99997)['resource'],99997)

    def test_run_requires_recorded_or_explicit_filter(self):
        with tempfile.TemporaryDirectory(prefix='d2-asset-trace-',dir=os.path.realpath(tempfile.gettempdir())) as tmp:
            root=Path(tmp);(root/'runtime.log').write_text(LOG)
            with self.assertRaisesRegex(ValueError,'explicit resource'):inspect(root)
            self.assertIsNone(inspect(root,10030)['process_result'])
            (root/'result.json').write_text(json.dumps({'trace_resource':10030,'exit_code':0}))
            self.assertEqual(inspect(root)['resource'],10030)
            with self.assertRaises(ValueError):inspect(root,10030,member='anm10031.lzs')
            (root/'runtime.log').unlink();(root/'runtime.log').symlink_to(root/'result.json')
            with self.assertRaises(ValueError):inspect(root)
if __name__=='__main__':unittest.main()
