"""Bounded streamed sprite switches; no UnityPy or proprietary files."""
import copy
import math
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from d2_rpg_clip import sprite_timelines, streamed_frames


def frame(time,index=None,value=0):
    raw=struct.pack('<fI',time,0 if index is None else 1)
    if index is not None:raw+=struct.pack('<I4f',index,0,0,0,value)
    return list(struct.unpack('<'+str(len(raw)//4)+'I',raw))


def fixture():
    words=frame(-3.4e38,3,0)+frame(0.5,3,1)+frame(math.inf)
    return dict(m_MuscleClip=dict(m_StartTime=0,m_StopTime=1,m_Clip=dict(data=dict(
        m_StreamedClip=dict(data=words,curveCount=4),m_DenseClip=dict(m_CurveCount=0),
        m_ConstantClip=dict(data=[])))),m_ClipBindingConstant=dict(
        genericBindings=[dict(typeID=4,attribute=3,isPPtrCurve=0),dict(typeID=114,attribute=1,isPPtrCurve=1)],
        pptrCurveMapping=[dict(m_FileID=10,m_PathID=9007199254740993),dict(m_FileID=12,m_PathID=-9007199254740995)]))


class ClipTests(unittest.TestCase):
    def test_stream_switches_preserve_file_id_and_exact_64_bit_path(self):
        timeline=sprite_timelines(fixture())[0]
        self.assertEqual(timeline['curve_index'],3)
        self.assertEqual(timeline['switches'],[dict(time=0,file_id=10,path_id='9007199254740993'),
                                             dict(time=0.5,file_id=12,path_id='-9007199254740995')])

    def test_constant_sprite_and_invalid_pointer_or_binding_bank(self):
        clip=fixture();data=clip['m_MuscleClip']['m_Clip']['data']
        data['m_StreamedClip']=dict(data=[],curveCount=0);data['m_ConstantClip']['data']=[0,0,0,1]
        self.assertEqual(sprite_timelines(clip)[0]['switches'][0]['file_id'],12)
        for value in (2,0.5,math.nan):
            bad=copy.deepcopy(clip);bad['m_MuscleClip']['m_Clip']['data']['m_ConstantClip']['data'][3]=value
            with self.assertRaises(ValueError):sprite_timelines(bad)
        bad=copy.deepcopy(clip);bad['m_MuscleClip']['m_Clip']['data']['m_ConstantClip']['data'].append(0)
        with self.assertRaisesRegex(ValueError,'widths'):sprite_timelines(bad)

    def test_truncation_bad_count_index_and_times_are_rejected(self):
        cases=[([0],4),(frame(0,4,0),4),(frame(1)+frame(0),4),(frame(math.nan),4),([-1],4)]
        for words,count in cases:
            with self.assertRaises(ValueError):streamed_frames(words,count)


if __name__=='__main__':unittest.main()
