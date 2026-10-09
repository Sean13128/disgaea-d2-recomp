"""Asset-free GUI service contracts: paths, job isolation, import validation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).parents[2]/'tools'
sys.path.insert(0,str(TOOLS))
try:
    import d2_sprite_workbench as studio
except ModuleNotFoundError:
    print('Sprite workbench tests require the existing RPG Pillow dependency')
    sys.exit(77)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='d2-sprite-workbench-test-')
        self.root=Path(self.temp.name)
        self.app=studio.Workbench(self.root/'work')

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.temp.cleanup()

    def test_source_layouts_and_archive_sibling_lookup(self):
        rpg=self.root/'rpg/android';(rpg/'masters').mkdir(parents=True)
        (rpg/'masters/character').write_bytes(b'master')
        self.assertEqual(studio.source_root(rpg.parent,'rpg'),rpg)
        d2=self.root/'game/PS3_GAME/USRDIR/Data';d2.mkdir(parents=True)
        (d2/'ANM_HI.dat').write_bytes(b'');(d2/'START.dat').write_bytes(b'')
        self.assertEqual(studio.source_root(self.root/'game','d2'),d2)
        self.assertEqual(studio.source_root(d2/'ANM_HI.dat','d2'),d2)
        with self.assertRaises(ValueError):studio.source_root(self.root,'d2')

    def test_jobs_serialize_and_cancel_waiting_work_without_mutations(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def first(job):
            entered.set();release.wait(3);calls.append('first');return {'done':True}
        first_id=self.app.submit('test','first',first)['job'];self.assertTrue(entered.wait(2))
        second_id=self.app.submit('test','second',lambda _:calls.append('second'))['job']
        self.app.cancelled.add(second_id);release.set();self.app.pool.shutdown(wait=True)
        self.assertEqual(calls,['first'])
        self.assertEqual(self.app.jobs[first_id]['status'],'complete')
        self.assertEqual(self.app.jobs[second_id]['status'],'cancelled')

    def test_failed_decode_is_visible_and_does_not_poison_next_job(self):
        def broken(_):raise ValueError('unsupported palette')
        a=self.app.submit('preview','broken',broken)['job']
        b=self.app.submit('preview','next',lambda _:dict(sprites=[]))['job']
        self.app.pool.shutdown(wait=True)
        self.assertEqual(self.app.jobs[a]['error'],'unsupported palette')
        self.assertEqual(self.app.jobs[b]['status'],'complete')

    def test_unknown_and_unsupported_targets_fail_before_import(self):
        self.app.sources={'rpg':{'path':str(self.root),'index':{'characters':[dict(id=54,name='Santa',available=True)],'stories':[]}},
                          'd2':{'path':str(self.root),'index':{'characters':[dict(id=410,name='Rozalin',supported=False)]}}}
        with self.assertRaisesRegex(ValueError,'not supported'):
            self.app.prepare_import(dict(rpg=54,d2=410,name='Santa'))
        with self.assertRaisesRegex(ValueError,'not found'):
            self.app.prepare_import(dict(rpg=55,d2=410))
        with self.assertRaises(ValueError):self.app.row('rpg',True)

    def test_selected_donor_must_match_profile_and_story_is_explicit(self):
        self.app.sources={'rpg':{'path':str(self.root),'index':{'characters':[dict(id=54,name='Santa',available=True)],'stories':[dict(id=7901,name='Santa story',available=True)]}},
                          'd2':{'path':str(self.root),'index':{'characters':[dict(id=10,name='Laharl',body=10,supported=True)]}}}
        with patch.object(studio,'profile_facts',return_value=dict(body=10,content=self.root)),patch.object(studio,'archive_member',side_effect=[b'selected',b'different']):
            with self.assertRaisesRegex(ValueError,'differs'):
                self.app.prepare_import(dict(rpg=54,d2=10,profile='new'))
        with patch.object(studio,'profile_facts',return_value=dict(body=10,content=self.root)),patch.object(studio,'archive_member',return_value=b'same'):
            selection=self.app.prepare_import(dict(rpg=54,d2=10,profile='new',story=7901))
            self.assertEqual(selection['story'],7901)
            with self.assertRaisesRegex(ValueError,'story illustration'):
                self.app.prepare_import(dict(rpg=54,d2=10,profile='new',story=54))

    def test_composed_idle_replaces_body_cape_fragments_and_keeps_parts(self):
        from PIL import Image
        whole=Image.new('RGBA',(16,24),(255,0,0,255))
        rows=[dict(name='cape',block='own',rectangle_index=1,animations=[6007],match='clear',pose=None,url='cape',width=16,height=8),
              dict(name='wait_back/wait01',block='own',rectangle_index=2,animations=[6007],match='exact',pose='wait_back/wait01',url='body',width=8,height=24),
              dict(name='front/attack_hand01',block='common',rectangle_index=3,animations=[1001],match='exact',pose='front/attack_hand01',url='hand',width=4,height=4),
              dict(name='front/stand',block='common',rectangle_index=4,animations=[1],match='exact',pose='front/stand',url='stand',width=12,height=24)]
        comp={(6007,1):dict(image=whole,pieces=2),(6007,2):dict(image=whole,pieces=2)}
        poses,parts=studio.separate_sprite_parts(rows,comp,self.app.image)
        self.assertEqual(len(poses),2)
        self.assertEqual(len(parts),3)
        self.assertTrue(poses[0]['composed'])
        self.assertEqual(poses[0]['pose'],'wait_back/wait01')
        self.assertEqual((poses[0]['width'],poses[0]['height']),(16,24))
        self.assertTrue(all(r['component'] for r in parts))
        self.assertNotIn('cape',[r['name'] for r in poses])

    def test_default_import_queue_extends_previous_result(self):
        from PIL import Image
        from types import SimpleNamespace
        latest={'current_profile':'new'};bases=[]
        selection=dict(rpg=9,d2=340,name='Fuka',story=None,profile='new',rpg_source=str(self.root),d2_name='Fuka')
        def fake_import(command,**kwargs):
            base=command[command.index('--profile')+1];bases.append(base)
            output=Path(command[command.index('--output')+1]);evidence=output/'costumes/340-fuka';evidence.mkdir(parents=True)
            (output/'stage.json').write_text('{}')
            report=dict(rpg_character=9,display_name='Fuka',body={'resource':905},selected=False,costume_id='fuka')
            (evidence/'added.json').write_text(json.dumps(report));Image.new('RGBA',(2,2)).save(evidence/'review.png')
            latest['current_profile']=str(output/'stage.json')
            return SimpleNamespace(returncode=0)
        with patch.object(self.app,'prepare_import',return_value=selection),patch.object(studio,'REPO',self.root),patch.object(studio,'local_config',side_effect=lambda:dict(latest)),patch.object(studio.subprocess,'run',side_effect=fake_import):
            one=self.app.import_costume({})['job'];two=self.app.import_costume({})['job'];self.app.pool.shutdown(wait=True)
        self.assertEqual(self.app.jobs[one]['status'],'complete')
        self.assertEqual(self.app.jobs[two]['status'],'complete')
        self.assertEqual(bases[0],'new')
        self.assertEqual(bases[1],self.app.jobs[one]['result']['profile'])

    def test_import_review_survives_restart_and_unknown_selection_is_rejected(self):
        job_id=self.app.submit('import','test import',lambda _:dict(profile='/private/example/stage.json'))['job']
        self.app.pool.shutdown(wait=True)
        reopened=studio.Workbench(self.app.workspace)
        try:
            self.assertEqual(reopened.jobs[job_id]['status'],'complete')
            self.assertEqual(reopened.jobs[job_id]['result']['profile'],'/private/example/stage.json')
            with self.assertRaisesRegex(ValueError,'completed import'):
                reopened.use_import('unknown')
        finally:reopened.pool.shutdown(wait=True)

    def test_launch_selects_exact_completed_profile_without_starting_real_game(self):
        (self.root/'profile').mkdir()
        result=dict(profile=str(self.root/'profile/stage.json'),class_id=340,costume_id='rpg-fuka')
        with patch.object(self.app,'use_import',return_value=result) as select,patch('d2_appearance_run.validate_profile'),patch.object(studio.subprocess,'Popen') as spawn:
            spawn.return_value.pid=123
            launched=self.app.play_import('completed-job')
            select.assert_called_once_with('completed-job')
            command=spawn.call_args.args[0]
            self.assertEqual(command[command.index('--stage')+1],result['profile'])
            self.assertEqual(launched['pid'],123)

    def test_color_profile_preserves_slots_and_copies_saves_without_selecting(self):
        from d2_appearance_colors import build, slots_for
        source=self.root/'private';source.mkdir()
        first=dict(class_id=10,selector=1,new_resource=900,visual_class_id=900,selection_mode='renderer-only',costume_id='santa',display_name='Santa')
        second=dict(first,new_resource=901,visual_class_id=901,costume_id='thunderlord')
        roots={key:str(source/name) for key,name in [('PS3_VFS_ROOT','content'),('PS3_HDD0_ROOT','hdd0'),('PS3_HDD1_ROOT','hdd1')]}
        for root in roots.values():Path(root).mkdir()
        save=source/'hdd0/save.bin';save.write_bytes(b'unmodified native save')
        data=dict(mode='isolated-runtime-experiment',runtime_environment=roots,appearances=[first],costumes=[first,second],color_slots=[dict(class_id=10,color=3,costume_id='santa')])
        stage=source/'stage.json';stage.write_text(json.dumps(data));before=stage.read_bytes()
        slots,_=slots_for(data);self.assertEqual([s['color'] for s in slots],[3,1])
        output=self.root/'colors';report=build(stage,output)
        self.assertEqual(stage.read_bytes(),before)
        self.assertEqual((output/'hdd0/save.bin').read_bytes(),save.read_bytes())
        (output/'hdd0/save.bin').write_bytes(b'changed private copy')
        self.assertEqual(save.read_bytes(),b'unmodified native save')
        self.assertEqual(report['slots'][0]['name'],'Santa')
        self.assertEqual(json.loads((output/'stage.json').read_text())['color_slots'],slots)
        data['costumes'] += [dict(first,new_resource=902+i,visual_class_id=902+i,costume_id='more-'+str(i)) for i in range(3)]
        with self.assertRaisesRegex(ValueError,'more than four'):slots_for(data)

    def test_color_build_job_is_persistent_and_launch_does_not_select_class(self):
        source=dict(id='source',kind='import',status='complete',result=dict(profile='/private/stage.json'))
        self.app.jobs['source']=source
        result=dict(profile='/private/colors/stage.json',slots=[])
        with patch('d2_appearance_colors.build',return_value=result) as build,patch.object(studio,'REPO',self.root):
            ident=self.app.color_profile('source')['job'];self.app.pool.shutdown(wait=True)
        self.assertEqual(self.app.jobs[ident]['status'],'complete')
        with patch('d2_appearance_choice.select') as select,patch('d2_appearance_add.remember') as remember:
            self.app.use_import(ident)
        select.assert_not_called();remember.assert_called_once_with(current_profile=result['profile'])
        reopened=studio.Workbench(self.app.workspace)
        try:self.assertEqual(reopened.jobs[ident]['result'],result)
        finally:reopened.pool.shutdown(wait=True)

    def test_export_recipe_saves_a_shareable_file_without_art_or_paths(self):
        profile=self.root/'private';(profile/'costumes/10-santa').mkdir(parents=True)
        santa=dict(class_id=10,selector=1,new_resource=900,visual_class_id=900,selection_mode='renderer-only',costume_id='santa',display_name='Dark Santa Laharl')
        (profile/'stage.json').write_text(json.dumps(dict(mode='isolated-runtime-experiment',appearances=[santa],costumes=[santa],
            color_slots=[dict(class_id=10,color=2,costume_id='santa')])))
        (profile/'costumes/10-santa/added.json').write_text(json.dumps(dict(class_id=10,character='Laharl',costume_id='santa',display_name='Dark Santa Laharl',rpg_character=54,
            profile=str(profile/'stage.json'),review=str(profile/'costumes/10-santa/review.png'),
            steps=[dict(step='body',resource=900),dict(step='face',crop=[24,13,120,109]),dict(step='illustration',crop=[1,2,30,40],source=str(self.root/'cache/char-54-story-7901/story/a.png'))])))
        (profile/'costumes/10-santa/review.png').write_bytes(b'private artwork')
        source=self.root/'android'
        for name in ['prefabs/characters/54','atlas/chara/story/79']+[f'atlas/chara/battle/{f}/{f.removeprefix("wait_")}54' for f in ('front','back','wait_front','wait_back')]:
            (source/name).parent.mkdir(parents=True,exist_ok=True);(source/name).write_bytes(name.encode())
        self.app.sources['rpg']=dict(path=str(source),index=dict(characters=[],stories=[dict(id=7901,name='Santa',img_base=79,available=True)]))
        self.app.recipes=self.root/'costume-recipes'
        self.app.jobs['done']=dict(id='done',kind='colors',status='complete',result=dict(profile=str(profile/'stage.json')))
        self.app.jobs['busy']=dict(id='busy',kind='import',status='running')
        with patch.object(studio.subprocess,'run') as opened:
            saved=self.app.export_recipe('done')
            opened.assert_not_called()
            again=self.app.export_recipe('done',True)
            self.assertEqual(opened.call_args.args[0],['/usr/bin/open','-R',again['path']])
        self.assertEqual((saved['file'],again['file'],saved['count'],saved['fingerprints'],saved['skipped']),
                         ('dark-santa-laharl.d2costume.json','dark-santa-laharl-2.d2costume.json',1,1,0))
        self.assertEqual(saved['costumes'],['Dark Santa Laharl → Laharl'])
        text=Path(saved['path']).read_text();recipe=json.loads(text)
        self.assertEqual(sorted(p.name for p in self.app.recipes.iterdir()),['dark-santa-laharl-2.d2costume.json','dark-santa-laharl.d2costume.json'])
        costume=recipe['costumes'][0]
        self.assertEqual((costume['rpg_character'],costume['story_character'],costume['color'],costume['face']['crop']),(54,7901,2,[24,13,120,109]))
        self.assertEqual(len(costume['sources']),6)
        for forbidden in (str(self.root),'review.png','private artwork','a.png'):self.assertNotIn(forbidden,text)
        for job in ('busy','missing'):
            with self.assertRaisesRegex(ValueError,'completed import'):self.app.export_recipe(job)
        (profile/'stage.json').unlink()
        with self.assertRaisesRegex(ValueError,'no longer exists'):self.app.export_recipe('done')

    def test_export_pack_with_art_goes_to_the_untracked_folder_and_never_overwrites(self):
        import d2_costume_pack as packs
        profile=self.root/'private';profile.mkdir()
        santa=dict(class_id=10,selector=1,new_resource=900,visual_class_id=900,selection_mode='renderer-only',costume_id='santa',display_name='Winter Pack')
        (profile/'stage.json').write_text(json.dumps(dict(mode='isolated-runtime-experiment',appearances=[santa],costumes=[santa])))
        self.app.packs=self.root/'costume-packs';self.app.recipes=self.root/'costume-recipes'
        self.app.jobs['done']=dict(id='done',kind='pack',status='complete',result=dict(profile=str(profile/'stage.json'),name='Friend file'))
        written=[]
        def fake(stage,path,name,replace,source):
            written.append((Path(stage),Path(path),name,replace));Path(path).parent.mkdir(exist_ok=True);Path(path).write_bytes(b'PK')
            return dict(pack=str(path),name='Winter Pack',bytes=2,costumes=['Dark Santa Laharl → Laharl'],with_recipe=1)
        with patch.object(packs,'export_pack',side_effect=fake),patch.object(studio.subprocess,'run') as opened:
            first=self.app.export_recipe('done',False,True);opened.assert_not_called()
            second=self.app.export_recipe('done',True,True)
            self.assertEqual(opened.call_args.args[0],['/usr/bin/open','-R',second['path']])
        self.assertEqual((first['file'],second['file'],first['art'],first['count'],first['bytes']),('winter-pack.d2costumepack','winter-pack-2.d2costumepack',True,1,2))
        self.assertEqual({p.parent for _,p,_,_ in written},{self.root/'costume-packs'})
        self.assertFalse(any(replace for *_,replace in written))
        self.assertFalse((self.root/'costume-recipes').exists())

    def test_import_file_queues_a_checked_pack_or_recipe_and_reports_failures(self):
        pack=self.root/'friend.d2costumepack';pack.write_bytes(b'PK\x03\x04')
        for bad in (None,'',str(self.root/'absent.d2costumepack'),str(self.root)):
            with self.assertRaisesRegex(ValueError,'Choose a'):self.app.import_file(bad)
        other=self.root/'notes.txt';other.write_text('x')
        with self.assertRaisesRegex(ValueError,'d2costumepack or'):self.app.import_file(str(other))
        report=dict(profile=str(self.root/'new/stage.json'),name='Friend pack',costumes=[dict(display_name='Yukata Valvatorez',character='Valvatorez')],
                    slots=[dict(class_id=230,color=1,costume_id='yukata',name='Yukata Valvatorez')],skipped=[dict(costume_id='x')],source='costume pack')
        commands=[]
        def fake(command,stdout=None,stderr=None,env=None,**kwargs):
            commands.append(command)
            if len(commands)==2:
                stderr.write('Pack member costumes/230-yukata/body.anm does not match its fingerprint');stderr.flush()
                return type('Done',(),dict(returncode=1))()
            stdout.write(json.dumps(report));stdout.flush()
            return type('Done',(),dict(returncode=0))()
        with patch.object(studio.subprocess,'run',side_effect=fake):
            first=self.app.import_file(str(pack));second=self.app.import_file(str(pack))
            self.app.pool.shutdown(wait=True)
        good,bad=self.app.jobs[first['job']],self.app.jobs[second['job']]
        self.assertEqual((good['kind'],good['status'],good['result']['costumes'],good['result']['skipped'],good['result']['file']),
                         ('pack','complete',['Yukata Valvatorez → Valvatorez'],1,'friend.d2costumepack'))
        self.assertEqual(commands[0][1:],[str(studio.REPO/'tools/d2_appearance_add.py'),'import',str(pack)])
        self.assertEqual((bad['status'],'fingerprint' in bad['error']),('failed',True))
        # The finished import survives a restart and can be selected for the next playtest.
        restarted=studio.Workbench(self.root/'work')
        try:
            self.assertEqual(restarted.jobs[first['job']]['result']['name'],'Friend pack')
            with patch('d2_appearance_add.remember') as remember,patch('d2_appearance_choice.select') as select:
                self.assertEqual(restarted.use_import(first['job'])['profile'],report['profile'])
                remember.assert_called_once_with(current_profile=report['profile']);select.assert_not_called()
        finally:restarted.pool.shutdown(wait=True)

    def test_source_scoped_extraction_cache(self):
        import d2_appearance_add as importer
        source=self.root/'source';output=self.root/'repo';(source/'masters').mkdir(parents=True)
        (source/'masters/character').write_bytes(b'master')
        paths=['prefabs/characters/54']+[f'atlas/chara/battle/{f}/{f.removeprefix("wait_")}54' for f in ('front','back','wait_front','wait_back')]
        for name in paths:
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'art')
        outputs=[]
        def fake_extract(command,**kwargs):
            path=Path(command[command.index('--output')+1]);path.mkdir();(path/'manifest.json').write_text('{}');outputs.append(path)
        with patch.object(importer,'REPO',output),patch.object(importer,'rpg_python',return_value='python'),patch.object(importer.subprocess,'run',side_effect=fake_extract):
            first=importer.extracted(source,54);self.assertEqual(first,importer.extracted(source,54));self.assertEqual(len(outputs),1)
            (source/paths[-1]).write_bytes(b'changed art')
            second=importer.extracted(source,54)
            self.assertNotEqual(first,second);self.assertEqual(len(outputs),2)
            self.assertTrue((first/'manifest.json').is_file())

if __name__=='__main__':unittest.main()
