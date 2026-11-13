import unreal as u,json
from pathlib import Path
root=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()));out=root/'Saved/BossImplementation'
bp=u.load_asset(json.loads((out/'blueprint_build.json').read_text())['asset'])
w=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world();a=u.GameplayStatics.get_all_actors_of_class(w,bp.generated_class())[0]
def call(n,*args):return a.call_method(n,args)
def get(n):return a.get_editor_property(n)
checks=[]
def check(n,c,v=None):checks.append({'test':n,'pass':bool(c),'details':str(v)})
a.set_editor_property('AutoDemo',False);a.set_editor_property('DrawCombatDebug',False)
try:
    call('StartM2');ids=list(get('MoveIDs'));mi=ids.index('M2-01-C');before=list(get('LearnS'))
    call('StartMove',mi);key=get('ChoiceKeys')[0]
    call('ReportResponse','learn-1',0,mi);call('RecordRoot')
    check('learning_frozen_during_fight',list(get('LearnS'))==before and get('LearnF')[mi]==0)
    check('branch_evidence_written',get('PendingN')[key]==1 and get('PendingN')[mi]==1)
    n=get('PendingN')[mi];call('RecordRoot');check('root_evidence_once',get('PendingN')[mi]==n)
    call('CommitLearning');check('failed_response_increases_weight',call('LearningMultiplier',mi)>1)
    check('branch_learning_independent',call('LearningMultiplier',key)>1 and call('LearningMultiplier',37)==1)
    call('StartM2');call('ChooseLength',33);ps=list(get('LengthProbs'))
    check('learned_length_distribution_capped',abs(sum(ps)-1)<1e-6 and max(ps)<=.55,ps)
    old=list(get('LearnF'));call('StartMove',mi);call('ReportResponse','aborted',0,mi);call('RecordRoot');call('ResetBattle')
    check('reset_discards_pending_learning',list(get('LearnF'))==old and sum(get('PendingN'))==0)
    call('StartM1');qidx=ids.index('M1-04');call('StartMove',qidx);before=get('HitsExecuted');call('ExecuteBeat')
    check('surround_formation_all_seven_emit',get('HitsExecuted')-before==7)
    call('StartM1');call('StartMove',ids.index('M1-09'));b=get('HitsExecuted')
    for _ in range(3):call('ExecuteBeat')
    check('three_formation_beats_seven_actor_hits',get('HitsExecuted')-b==7)
    call('StartM1');call('StartMove',ids.index('M1-07'));check('last_disciple_blue_master_wave',list(get('Beats'))==[8,4,4,4,4,4,14] and list(get('BeatActors'))==[0,1,2,3,4,5,6])
    check('named_animation_interfaces_loaded',len(get('StateAnimations'))==349 and all(x is None for x in get('StateAnimations')))
finally:
    # These checks intentionally changed only this PIE instance's memory; discard it by ending PIE.
    a.set_editor_property('AutoDemo',True);a.set_editor_property('DrawCombatDebug',True);call('StartM1')
    result={'passed':sum(x['pass'] for x in checks),'total':len(checks),'checks':checks}
    (out/'learning_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result))
