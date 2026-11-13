"""Native Blueprint regression checks in PIE, with no Python gameplay dependency."""
import unreal as u, json, math, traceback
from pathlib import Path
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()))
OUT=ROOT/'Saved/BossImplementation'
report=json.loads((OUT/'blueprint_build.json').read_text(encoding='utf8'))
bp=u.load_asset(report['asset'])
w=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
assert w,'Run PIE before this test'
a=u.GameplayStatics.get_all_actors_of_class(w,bp.generated_class())[0]
results=[]
def get(k):return a.get_editor_property(k)
def call(name,*args):return a.call_method(name,args)
def check(name,condition,details=None):
    results.append({'test':name,'pass':bool(condition),'details':str(details) if details is not None else None})
    if not condition:print('FAIL',name,details)
def tick(seconds):
    for _ in range(round(seconds/.05)):call('TickEncounter',.05)
def damage(i,hp=0.,qi=0.,impulse=0.):call('DamageFighter',i,float(hp),float(qi),float(impulse),True)
try:
    a.set_editor_property('AutoDemo',False);a.set_editor_property('DemoDamage',False);a.set_editor_property('SimulateResponses',False)
    a.set_editor_property('MoveTarget',False);a.set_editor_property('ShowHUD',False);a.set_editor_property('DrawCombatDebug',False)
    ids=list(get('MoveIDs'))
    for phase in (1,2,3,4):
        call('StartM'+str(phase))
        for f in get('Fighters'):f.set_actor_location(u.Vector(200,0,0),False,False)
        get('TargetActor').set_actor_location(u.Vector(0,0,0),False,False)
        call('TickEncounter',.01)
        eligible=[ids[i] for i in range(len(ids)) if call('CanMove',i)]
        expected=(lambda x:x.startswith('M1')) if phase==1 else (lambda x:x.startswith('M2')) if phase==2 else (lambda x:x.startswith(('M2','M3','R-'))) if phase==3 else (lambda x:x.startswith(('M2','M4')))
        check('phase_%d_admission'%phase,bool(eligible) and all(expected(x) for x in eligible),eligible)
        call('ChooseMove');ps=list(get('Probabilities'));positive=[x for x in ps if x>0];cap=1 if len(positive)==1 else .65 if len(positive)==2 else .45
        check('phase_%d_probabilities'%phase,abs(sum(ps)-1)<1e-6 and max(ps)<=cap+1e-6 and min(ps)>=0,{'sum':sum(ps),'max':max(ps),'n':len(positive)})
    call('StartM1');damage(0,qi=25);q=get('Qi')[0];tick(1)
    check('no_passive_qi_regen',abs(get('Qi')[0]-q)<1e-6,(q,get('Qi')[0]))
    call('StartM2');damage(0,qi=100);check('qi_break_not_ground',get('BrokenUntil')[0]>get('Clock') and get('GroundUntil')[0]<=get('Clock'))
    tick(.5);damage(0,impulse=100);check('ground_and_break_independent',get('BrokenUntil')[0]>get('Clock') and get('GroundUntil')[0]>get('Clock'))
    tick(3);check('ground_expires_before_break',get('GroundUntil')[0]<=get('Clock')<get('BrokenUntil')[0])
    tick(1);check('break_recovers',get('Qi')[0]==100 and get('BrokenStart')[0]<0)
    call('StartM1');call('StartMove',ids.index('M1-03'));damage(1,qi=100)
    check('participant_break_cancels_formation',get('ActionStage')==0)
    call('StartMove',ids.index('M1-03'));damage(1,hp=1,impulse=30)
    check('detached_nonparticipant_does_not_cancel',get('ActionStage')!=0)
    damage(2,qi=100);check('one_detachment_slot',get('DetachedIndex')==1)
    call('StartM1')
    for i in (1,2,3,4):damage(i,hp=9999)
    hp0=get('HP')[0];started=call('TryServices');call('CommitService')
    check('summon_to_three_cost_one_third',started and call('CountLivingDisciples')==3 and abs(hp0-get('HP')[0]-1000)<1e-6,list(get('HP')))
    call('StartM1');damage(0,hp=2000)
    for i in (1,2,3,4):damage(i,hp=9999)
    call('TryServices');check('summon_forbidden_at_exact_third',get('Service')!=1)
    call('StartM1');damage(0,hp=900);h0=list(get('HP'));call('TryServices');target=get('ServiceTarget');call('CommitService');h1=list(get('HP'))
    check('drain_conserves_hp',target>=1 and abs(sum(h0)-sum(h1))<1e-6 and h1[target]>=1,(h0,h1))
    for mid,length in [('M2-01-A',5),('M2-01-B',3),('M2-01-D',3),('M2-01-F',1),('M4-01',6)]:
        call('StartM4');call('StartMove',ids.index(mid));beats=list(get('Beats'))
        check(mid+'_pattern',len(beats)==length and beats[-1] in (14,15),beats)
    call('StartM2');call('StartMove',ids.index('M2-05-N'));call('ExecuteBeat')
    check('near_red_spray_no_blue',list(get('Beats'))==[29])
    edges={1:{2,3,5},2:{1,4,5},3:{4,2,5},4:{3,1,5},5:{1,2,4}}
    valid=True;lengths=set()
    for _ in range(80):
        call('StartM2');call('StartMove',ids.index('M2-01-C'));b=list(get('Beats'));prefix=b[:-3];lengths.add(len(prefix))
        valid &= 1<=len(prefix)<=4 and b[-3:]==[1,2,15] and all(y in edges[x] for x,y in zip(prefix,prefix[1:]))
    check('finite_pool_legal_edges',valid and lengths=={1,2,3,4},lengths)
    call('StartM3');call('KillRed');check('red_first_enrage',get('Phase')==4 and not get('Resolved'))
    call('StartM3');call('KillMaster');tick(2.1);check('master_first_suicide',get('Resolved') and get('HP')[7]==0)
    call('StartM2');call('ReportResponse','dedup',1,13);p=get('Pressure');call('ReportResponse','dedup',1,13)
    check('response_dedup',get('Pressure')==p and p==-12)
    for i in range(10):call('ReportResponse','cap'+str(i),0,13)
    check('pressure_two_second_positive_cap',get('Pressure')==48,get('Pressure'))
    call('StartM1');a.set_editor_property('AutoDemo',True);a.set_editor_property('DemoStageSeconds',10.)
    before=get('HitsExecuted');tick(45)
    check('full_demo_terminates',get('Resolved') and get('Phase')==4 and get('HitsExecuted')>before,{'phase':get('Phase'),'hits':get('HitsExecuted')-before})
    check('registered_page',len(get('StateIDs'))==349 and len(get('TransitionSources'))==756)
finally:
    a.set_editor_property('DemoStageSeconds',35.);a.set_editor_property('AutoDemo',True);a.set_editor_property('MoveTarget',True);a.set_editor_property('DrawCombatDebug',True);a.set_editor_property('ShowHUD',True)
    call('StartM1')
    data={'passed':sum(t['pass'] for t in results),'total':len(results),'checks':results,'asset':report['asset'],'runtime':'actual native Blueprint functions in PIE'}
    (OUT/'runtime_verification.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(data,ensure_ascii=False))
