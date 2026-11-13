"""Generate native runtime Blueprints; Python is only used for authoring assets."""
import sys,json,math,traceback
from pathlib import Path
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()))
sys.path.insert(0,str(ROOT/'Tools/BossLab'));sys.path.insert(0,str(ROOT/'Research/Step2/Engineering'))
import bp_dsl,importlib
importlib.reload(bp_dsl)
from bp_dsl import *
from catalog import MOVES
BASE='/Game/BossLab'
RUNTIME_NAME='BP_BossEncounter_Final'
MOVELIST=list(MOVES.values());INDEX={m.id:i for i,m in enumerate(MOVELIST)}
REPORT=ROOT/'Saved/BossImplementation';REPORT.mkdir(parents=True,exist_ok=True)
GDATA=json.loads((ROOT/'Research/Step3/fsm_graph.json').read_text(encoding='utf8'))

def fresh(path,parent):
    bp=u.load_asset(path)
    if not bp:
        factory=u.BlueprintFactory();factory.set_editor_property('parent_class',parent)
        return u.AssetToolsHelpers.get_asset_tools().create_asset(path.rsplit('/',1)[1],path.rsplit('/',1)[0],u.Blueprint,factory)
    u.get_editor_subsystem(u.AssetEditorSubsystem).close_all_editors_for_asset(bp)
    for gr in list(L.list_graphs(bp)):
        if gr.get_name()=='EventGraph':
            e=u.BlueprintGraphEditor.get_graph_editor(gr);e.remove_nodes(e.list_all_nodes())
            for c in e.list_comment_nodes():e.remove_comment_node(c)
        elif gr.get_name()!='UserConstructionScript':L.remove_graph(bp,gr)
    e=u.BlueprintGraphEditor.get_graph_editor_by_name(bp,'EventGraph')
    if not e:e=u.BlueprintGraphEditor.create_and_edit_function_graph(bp,'BuilderTemporary')
    for name in L.list_member_variable_names(bp,False):e.remove_member_variable(name)
    return bp

def own(g,name,**args):return g.fn(name,**args).find_result_pin()
def vec(g,x,y,z):return g.p(M+'MakeVector',X=x,Y=y,Z=z)
def loc(g,idx):return g.p('/Script/Engine.Actor.K2_GetActorLocation',self=g.arr('Fighters',idx))
def distance(g,idx):return g.p(M+'Vector_Distance',V1=loc(g,idx),V2=g.get('TargetLocation'))
def setstate(g,name):g.set('ActiveState',name)
def arrplus(g,name,idx,amount):g.put(name,idx,g.add(g.arr(name,idx),amount))
def inc(g,name,amount=1):g.set(name,g.add(g.get(name),amount))
def valid(g,obj):return g.p(K+'IsValid',Object=obj)

def build():
    save=fresh(BASE+'/Blueprints/BP_BossLearningSave',u.SaveGame)
    for n in ('Success','Failure'):variable(save,n,'double[]')
    variable(save,'Version','int',2);compile_bp(save);u.EditorAssetLibrary.save_loaded_asset(save)
    # Rebuilding thousands of nodes in-place can invalidate native editor references.
    # Generate an isolated asset on repeated runs; scene_build reads the report path.
    runtime_path=BASE+'/Blueprints/'+RUNTIME_NAME
    if u.EditorAssetLibrary.does_asset_exist(runtime_path):
        runtime_path,_=u.AssetToolsHelpers.get_asset_tools().create_unique_asset_name(runtime_path,'_Rebuild')
    bp=fresh(runtime_path,u.Actor)
    scalars={'Clock':('double',0),'Delta':('double',0),'Phase':('int',1),'Epoch':('int',0),
             'Pressure':('double',0),'ActionStage':('int',0),'StageUntil':('double',0),'ActionStarted':('double',0),
             'DecisionAt':('double',2),'CurrentMove':('int',-1),'ActorIndex':('int',0),'BeatIndex':('int',0),
             'LastOffense':('double',-3),'PreviousMove':('int',-1),'BeforePrevious':('int',-1),'DangerStreak':('int',0),
             'LastResult':('int',0),'Observed':('bool',False),'BranchVisited':('bool',False),
             'ActiveState':('string','B_ENTRY'),'DetachedIndex':('int',-1),'SupportCount':('int',0),
             'SupportWindow':('double',0),'SupportAt':('double',0),'SupportReady':('double',0),
             'DrainReady':('double',0),'SummonReady':('double',0),'HealReady':('double',0),'ServiceTarget':('int',-1),
             'Service':('int',0),'TargetHP':('double',10000),'TargetQi':('double',100),
             'StageStart':('double',0),'RedEntered':('bool',False),'Resolved':('bool',False),
             'HitsExecuted':('int',0),'AttacksStarted':('int',0),'FrameCounter':('int',0),
             'RootSuccess':('double',0),'RootSamples':('int',0),'PrefixLength':('int',0),
             'PendingRootCommitted':('bool',False),'DemoDamageAt':('double',4),'WaveReady':('double',0),
             'SaveObject':(u.SaveGame,''),'DefaultIdle':(u.AnimationAsset,''),'DefaultRun':(u.AnimationAsset,''),
             'DefaultJump':(u.AnimationAsset,''),'DefaultDeath':(u.AnimationAsset,''),
             'CameraActor':(u.Actor,''),'TargetActor':(u.Actor,''),'TargetLocation':('vector','(X=0,Y=0,Z=0)'),
             'LastTarget':('vector','(X=0,Y=0,Z=0)'), 'MoveWeight':('double',0),'BestScore':('double',0),
             'TargetResponseUntil':('double',0),'BattleIndex':('int',0),'OpenerPending':('bool',True),
             'PauseEncounter':('bool',False),'LastImpact':('double',-10.),'LastImpactDanger':('bool',False),
             'TransitionCount':('int',0),'PreviousState':('string',''),'LastTransitionGuard':('string',''),
             'SuicideUntil':('double',-1.),'SimulationEvent':('int',0)}
    for n,(t,d) in scalars.items():variable(bp,n,t,d,editable=n in ('TargetActor','CameraActor'))
    options={'AutoDemo':('bool',True),'MoveTarget':('bool',True),'SimulateResponses':('bool',False),
             'DemoDamage':('bool',False),'LoopDemo':('bool',False),'MasterDiesFirst':('bool',False),
             'DemoStageSeconds':('double',35),'TargetMoveRadius':('double',420),
             'TargetMoveSpeed':('double',.18),'ResponseSkill':('double',.65),
             'StartingPhase':('int',1),'DrawCombatDebug':('bool',True),'ShowHUD':('bool',True),
             'UsePlaceholderAnimations':('bool',True),'EnableLearningSave':('bool',False),
             'LearningSlot':('string','BossLab_RealPlayer_v2'),'MaxAttackRange':('double',2000),
             'GuardAngle':('double',60),'DodgeCooldown':('double',2.5),'BrokenDamageMultiplier':('double',1.25)}
    for n,(t,d) in options.items():variable(bp,n,t,d,'BossLab|Test Settings',True)
    arrays={'MoveIDs':'string[]','BaseWeights':'double[]','PressureSlopes':'double[]','Ranges':'double[]','Ideals':'double[]','Widths':'double[]',
            'Cooldowns':'double[]','Windups':'double[]','Recoveries':'double[]','Owners':'int[]','MinPhase':'int[]','MaxPhase':'int[]','RequiredDisciples':'int[]','Danger':'bool[]',
            'CooldownUntil':'double[]','Weights':'double[]','Probabilities':'double[]','Ages':'double[]','History':'int[]','FrozenProb':'bool[]',
            'LearnS':'double[]','LearnF':'double[]','PendingS':'double[]','PendingN':'double[]','BranchS':'double[]','BranchF':'double[]','ChoiceKeys':'int[]',
            'LengthWeights':'double[]','LengthProbs':'double[]','LengthFrozen':'bool[]','StateAnimations':L.get_array_type(typ(u.AnimationAsset)),
            'HP':'double[]','MaxHP':'double[]','Qi':'double[]','BrokenUntil':'double[]','BrokenStart':'double[]','GroundUntil':'double[]','KnockLock':'double[]',
            'ImpactAccum':'double[]','ImpactAt':'double[]','GuardReady':'double[]','DodgeReady':'double[]','ActorState':'string[]',
            'Fighters':L.get_array_type(typ(u.SkeletalMeshActor)),'Meshes':L.get_array_type(typ(u.SkeletalMeshComponent)),
            'Swords':L.get_array_type(typ(u.Actor)),'LastBeatCodes':'int[]','PoseStart':'double[]','MoveRootStates':'string[]',
            'Participants':'int[]','Beats':'int[]','BeatActors':'int[]','ActorBusyUntil':'double[]','AttackPoseUntil':'double[]','Destinations':'vector[]',
            'HomePositions':'vector[]','AnimationModeCache':'int[]','MoveAnimations':L.get_array_type(typ(u.AnimationAsset)),
            'FallbackAttacks':L.get_array_type(typ(u.AnimationAsset)),
            'PressureTimes':'double[]','PressureDeltas':'double[]','SeenEventIDs':'string[]',
            'StateIDs':'string[]','TransitionSources':'string[]','TransitionTargets':'string[]','TransitionGuards':'string[]',
            'TransitionKinds':'string[]','TransitionPriorities':'int[]','StateVisitCounts':'int[]'}
    for n,t in arrays.items():
        if isinstance(t,u.EdGraphPinType):
            e=u.BlueprintGraphEditor.get_graph_editor_by_name(bp,'EventGraph');assert e.add_member_variable(n,t,'')
        else:variable(bp,n,t)
        if n in ('Fighters','Meshes','Swords','MoveAnimations','FallbackAttacks','HomePositions'):
            L.set_blueprint_variable_instance_editable(bp,n,True);L.set_blueprint_variable_category(bp,n,'BossLab|Bindings')
    # The exact animation interfaces approved in step 3 stay empty. Generic fallbacks are separate.
    for item in json.loads((ROOT/'Research/Step3/asset_bindings.json').read_text(encoding='utf8'))['resources']:
        if item['name'].startswith('AN_'):variable(bp,item['name'],u.AnimationAsset,'','BossLab|Unbound Animation Interfaces',True)
    funcs={}
    specs={
        'DefineState':({'StateID':'string','DisplayName':'string','Hierarchy':'string'},'string',True),
        'RegisterTransition':({'FromState':'string','ToState':'string','Guard':'string','Kind':'string','Priority':'int'},None,False),
        'EnterState':({'StateID':'string'},None,False),
        'InitEncounter':({},None,False),'TickEncounter':({'Seconds':'double'},None,False),
        'CountReadyDisciples':({},'int',False),'CountLivingDisciples':({},'int',False),
        'CanMove':({'MoveIndex':'int'},'bool',False),'LearningMultiplier':({'MoveIndex':'int'},'double',True),
        'ComputeWeight':({'MoveIndex':'int'},'double',False),'ChooseMove':({},'int',False),
        'StartMove':({'MoveIndex':'int'},None,False),'AppendBeat':({'Code':'int','Who':'int'},None,False),
        'BuildCombo':({},None,False),'EmitBeat':({'Code':'int','Who':'int'},None,False),
        'ExecuteBeat':({},None,False),'TickAction':({},None,False),'FinishAction':({},None,False),
        'MoveActors':({},None,False),'PlayPose':({'Who':'int','Mode':'int'},None,False),
        'SetGoal':({'Who':'int','Goal':'vector'},None,False),'TickResources':({},None,False),
        'DamageFighter':({'Who':'int','HPDamage':'double','QiDamage':'double','Impulse':'double','BypassGuard':'bool'},None,False),
        'PhaseCheck':({},None,False),'SetPhase':({'NewPhase':'int'},None,False),
        'TryServices':({},'bool',False),'CommitService':({},None,False),
        'ReportResponse':({'EventID':'string','Outcome':'int','MoveIndex':'int'},None,False),
        'RecordRoot':({},None,False),'CommitLearning':({},None,False),'LoadLearning':({},None,False),
        'TickDemo':({},None,False),'DrawHUD':({},None,False),'TryWave':({},None,False),
        'Telegraph':({},None,False),'ReadControls':({},None,False),'NotifyThreat':({'Who':'int'},None,False),
        'EnterBeatState':({},None,False),
        'ChooseLength':({'Offset':'int'},'int',False),
        'StartM1':({},None,False),'StartM2':({},None,False),'StartM3':({},None,False),'StartM4':({},None,False),
        'KillRed':({},None,False),'KillMaster':({},None,False),'BreakMaster':({},None,False),'DropMaster':({},None,False),
        'BreakDisciple':({},None,False),'ResetBattle':({},None,False)}
    for name,(ins,out,pure) in specs.items():funcs[name]=Graph(bp,name,ins,out,pure)
    compile_bp(bp)
    build_registry_functions(funcs)
    build_count_functions(funcs)
    build_selection(funcs)
    build_combo_functions(funcs)
    build_action_functions(funcs)
    build_resource_functions(funcs)
    build_health_and_phase(funcs)
    build_learning(funcs,save)
    build_presentation(funcs)
    build_controls(funcs)
    build_lifecycle(funcs)
    compile_bp(bp)
    fill_defaults(bp)
    build_single_page(bp)
    compile_bp(bp)
    u.EditorAssetLibrary.save_loaded_asset(bp,only_if_is_dirty=False)
    report={'asset':bp.get_path_name(),'compiled':True,'runtime':'native Blueprint bytecode; no Python during Play',
            'functions':len(funcs),'graph_nodes':sum(len(u.BlueprintGraphEditor.get_graph_editor(g).list_all_nodes()) for g in L.list_graphs(bp)),
            'states':len(GDATA['nodes']),'transitions':len(GDATA['edges']),'moves':len(MOVELIST)}
    (REPORT/'blueprint_build.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))

def build_registry_functions(fs):
    g=fs['DefineState'];g.return_(g.get('StateID'))
    g=fs['RegisterTransition']
    for a,k in [('TransitionSources','FromState'),('TransitionTargets','ToState'),('TransitionGuards','Guard'),('TransitionKinds','Kind'),('TransitionPriorities','Priority')]:g.append(a,g.get(k))
    g=fs['EnterState'];g.set('PreviousState',g.get('ActiveState'));g.set('ActiveState',g.get('StateID'));inc(g,'TransitionCount')
    idx=g.p(A+'Array_Find',TargetArray=g.get('StateIDs'),ItemToFind=g.get('StateID'))
    g.if_(g.ge(idx,0),lambda:g.put('StateVisitCounts',idx,g.add(g.arr('StateVisitCounts',idx),1)))

def build_count_functions(fs):
    for name,ready in [('CountReadyDisciples',True),('CountLivingDisciples',False)]:
        g=fs[name];g.declare('N','int',0);g.set('N',0)
        def one(i):
            cond=g.gt(g.arr('HP',i),0.)
            if ready:cond=g.both(cond,g.both(g.le(g.arr('BrokenUntil',i),g.get('Clock')),g.not_(g.eq(i,g.get('DetachedIndex')))))
            g.if_(cond,lambda:g.set('N',g.add(g.get('N'),1)))
        g.loop(6,one,1);g.return_(g.get('N'))

def build_selection(fs):
    g=fs['CanMove'];i=g.get('MoveIndex');g.declare('OK','bool',False);g.declare('Who','int',0)
    g.set('Who',g.select(g.eq(g.arr('Owners',i),1),7,0))
    owner=g.arr('Owners',i);who=g.get('Who')
    cond=g.both(g.ge(g.get('Phase'),g.arr('MinPhase',i)),g.le(g.get('Phase'),g.arr('MaxPhase',i)))
    cond=g.both(cond,g.ge(g.get('Clock'),g.arr('CooldownUntil',i)))
    cond=g.both(cond,g.le(distance(g,who),g.arr('Ranges',i)))
    cond=g.both(cond,g.gt(g.arr('HP',who),0.))
    ready=g.both(g.le(g.arr('BrokenUntil',who),g.get('Clock')),g.le(g.arr('GroundUntil',who),g.get('Clock')))
    cond=g.both(cond,ready);g.set('OK',cond)
    def group_basic():
        g.set('OK',False)
        def candidate(j):
            available=g.both(g.gt(g.arr('HP',j),0.),g.both(g.le(g.arr('BrokenUntil',j),g.get('Clock')),g.le(distance(g,j),g.arr('Ranges',i))))
            g.if_(available,lambda:g.set('OK',True))
        g.loop(6,candidate)
        g.set('OK',g.both(g.get('OK'),g.both(g.eq(g.get('Phase'),1),g.ge(g.get('Clock'),g.arr('CooldownUntil',i)))))
    g.if_(g.eq(owner,3),group_basic)
    g.if_(g.gt(g.arr('RequiredDisciples',i),0),lambda:g.set('OK',g.both(g.get('OK'),g.ge(own(g,'CountReadyDisciples'),g.arr('RequiredDisciples',i)))))
    g.if_(g.eq(owner,2),lambda:g.set('OK',g.both(g.get('OK'),g.both(g.gt(g.arr('HP',7),0),g.le(g.arr('BrokenUntil',7),g.get('Clock'))))))
    g.if_(g.eq(i,INDEX['M1-01-Q']),lambda:g.set('OK',False))
    g.if_(g.eq(i,INDEX['M2-05-F']),lambda:g.set('OK',g.both(g.get('OK'),g.gt(distance(g,0),450.))))
    g.if_(g.both(g.eq(i,g.get('PreviousMove')),g.eq(i,g.get('BeforePrevious'))),lambda:g.set('OK',False))
    g.if_(g.both(g.ge(g.get('DangerStreak'),2),g.arr('Danger',i)),lambda:g.set('OK',False))
    g.return_(g.get('OK'))
    g=fs['LearningMultiplier'];i=g.get('MoveIndex');n=g.add(g.arr('LearnS',i),g.arr('LearnF',i))
    r=g.div(g.add(2.,g.arr('LearnS',i)),g.add(4.,n));c=g.div(n,g.add(n,8.))
    g.return_(g.p(M+'Exp',A=g.mul(1.2,g.mul(c,g.sub(1.,g.mul(2.,r))))))
    g=fs['ComputeWeight'];i=g.get('MoveIndex');g.declare('W','double',0);g.declare('Count','int',0);g.set('W',0.);g.set('Count',0)
    def weight():
        who=g.select(g.eq(g.arr('Owners',i),1),7,0)
        d=distance(g,who);sigma=g.div(g.sub(d,g.arr('Ideals',i)),g.arr('Widths',i))
        dist=g.add(.25,g.mul(.75,g.p(M+'Exp',A=g.mul(-.5,g.mul(sigma,sigma)))))
        g.loop(g.sub(g.length('History'),1),lambda j:g.if_(g.eq(g.arr('History',j),i),lambda:g.set('Count',g.add(g.get('Count'),1))))
        rep=g.mul(g.p(M+'Power',Base=.7,Exp=g.get('Count')),g.select(g.eq(i,g.get('PreviousMove')),.25,1.))
        age=g.add(1.,g.mul(.04,g.min(g.arr('Ages',i),10.)))
        pressure=g.p(M+'Exp',A=g.mul(g.arr('PressureSlopes',i),g.div(g.get('Pressure'),100.)))
        context=g.select(g.both(g.lt(g.get('TargetQi'),25.),g.arr('Danger',i)),1.15,1.)
        g.set('W',g.mul(g.arr('BaseWeights',i),g.mul(pressure,g.mul(g.pure('LearningMultiplier',MoveIndex=i),g.mul(dist,g.mul(rep,g.mul(age,context)))))))
    g.if_(own(g,'CanMove',MoveIndex=i),weight);g.return_(g.get('W'))
    g=fs['ChooseMove'];
    for n,t,d in [('Sum','double',0),('N','int',0),('Remain','double',1),('FreeSum','double',0),('Cap','double',.45),('Draw','double',0),('Pick','int',-1),('Cum','double',0)]:g.declare(n,t,d)
    g.set('Sum',0.);g.set('N',0);g.set('Pick',-1)
    def scan(i):
        w=own(g,'ComputeWeight',MoveIndex=i);g.put('Weights',i,w);g.if_(g.gt(w,0.),lambda:(g.set('Sum',g.add(g.get('Sum'),w)),g.set('N',g.add(g.get('N'),1))))
    g.loop(32,scan)
    def draw():
        g.set('Cap',g.select(g.eq(g.get('N'),1),1.,g.select(g.eq(g.get('N'),2),.65,.45)))
        g.set('Remain',1.)
        def init(i):
            p=g.add(g.mul(.88,g.div(g.arr('Weights',i),g.get('Sum'))),g.div(.12,g.get('N')))
            g.put('Probabilities',i,g.select(g.gt(g.arr('Weights',i),0.),p,0.));g.put('FrozenProb',i,False)
        g.loop(32,init)
        def water(_):
            g.set('FreeSum',0.)
            g.loop(32,lambda i:g.if_(g.not_(g.arr('FrozenProb',i)),lambda:g.set('FreeSum',g.add(g.get('FreeSum'),g.arr('Probabilities',i)))))
            def redistribute(i):
                def free():
                    g.put('Probabilities',i,g.mul(g.get('Remain'),g.div(g.arr('Probabilities',i),g.max(g.get('FreeSum'),.000001))))
                g.if_(g.not_(g.arr('FrozenProb',i)),free)
            g.loop(32,redistribute)
            def cap(i):
                g.if_(g.both(g.not_(g.arr('FrozenProb',i)),g.gt(g.arr('Probabilities',i),g.get('Cap'))),
                      lambda:(g.put('Probabilities',i,g.get('Cap')),g.put('FrozenProb',i,True),g.set('Remain',g.sub(g.get('Remain'),g.get('Cap')))))
            g.loop(32,cap)
        g.loop(32,water)
        g.set('Draw',g.rand());g.set('Cum',0.)
        def pick(i):
            g.set('Cum',g.add(g.get('Cum'),g.arr('Probabilities',i)))
            g.if_(g.both(g.lt(g.get('Pick'),0),g.lt(g.get('Draw'),g.get('Cum'))),lambda:g.set('Pick',i))
        g.loop(32,pick)
    g.if_(g.gt(g.get('N'),0),draw);g.return_(g.get('Pick'))

def build_combo_functions(fs):
    g=fs['ChooseLength']
    for n,t,d in [('Sum','double',0.),('Free','double',0.),('Remain','double',1.),('Draw','double',0.),('Cum','double',0.),('Pick','int',4)]:g.declare(n,t,d)
    g.set('Sum',0.);g.set('Remain',1.);g.set('Pick',4);g.set('Draw',g.rand())
    def weight(i):
        w=g.mul(g.p(M+'Exp',A=g.mul(.4,g.mul(g.div(g.get('Pressure'),100.),g.sub(g.add(i,1.),2.5)))),g.pure('LearningMultiplier',MoveIndex=g.add(g.get('Offset'),i)))
        g.put('LengthWeights',i,w);g.set('Sum',g.add(g.get('Sum'),g.arr('LengthWeights',i)))
    g.loop(3,weight)
    g.loop(3,lambda i:(g.put('LengthProbs',i,g.add(.03,g.mul(.88,g.div(g.arr('LengthWeights',i),g.get('Sum'))))),g.put('LengthFrozen',i,False)))
    def water(_):
        g.set('Free',0.)
        g.loop(3,lambda i:g.if_(g.not_(g.arr('LengthFrozen',i)),lambda:g.set('Free',g.add(g.get('Free'),g.arr('LengthProbs',i)))))
        g.loop(3,lambda i:g.if_(g.not_(g.arr('LengthFrozen',i)),lambda:g.put('LengthProbs',i,g.mul(g.get('Remain'),g.div(g.arr('LengthProbs',i),g.max(g.get('Free'),.000001))))))
        g.loop(3,lambda i:g.if_(g.both(g.not_(g.arr('LengthFrozen',i)),g.gt(g.arr('LengthProbs',i),.55)),lambda:(g.put('LengthProbs',i,.55),g.put('LengthFrozen',i,True),g.set('Remain',g.sub(g.get('Remain'),.55)))))
    g.loop(3,water);g.set('Cum',0.)
    def pick(i):
        g.set('Cum',g.add(g.get('Cum'),g.arr('LengthProbs',i)))
        g.if_(g.both(g.eq(g.get('Pick'),4),g.lt(g.get('Draw'),g.get('Cum'))),lambda:g.set('Pick',g.add(i,1)))
    g.loop(2,pick);g.append('ChoiceKeys',g.sub(g.add(g.get('Offset'),g.get('Pick')),1));g.return_(g.get('Pick'))
    g=fs['AppendBeat'];g.append('Beats',g.get('Code'));g.append('BeatActors',g.get('Who'))
    g=fs['BuildCombo'];g.clear('Beats');g.clear('BeatActors');g.clear('ChoiceKeys');i=g.get('CurrentMove');who=g.get('ActorIndex')
    codes={'L':1,'R':2,'U':3,'D':4,'T':5,'J':6,'K':7,'Q':8,'SPRAY':9,'B:T':15,'B:D':14,'B:J':16,'R:T':25,'R:Q':28,'R:SPRAY':29,'R:BACK':24,'K:BIND':35,'K:D':34,'B:DUET':18,'R:M':28,'R:R':28}
    for idx,m in enumerate(MOVELIST):
        def sequence(m=m):
            if m.id in ('M2-01-C','M2-01-E'):
                # Four-way length weighting, sampled once; prefix never exceeds four.
                g.set('PrefixLength',own(g,'ChooseLength',Offset=33 if m.id.endswith('C') else 37))
                g.declare('PrevAtom'+str(idx),'int',0);g.set('PrevAtom'+str(idx),g.randint(1,5))
                g.declare('NextAtom'+str(idx),'int',0)
                def pre(_):
                    g.fn('AppendBeat',Code=g.get('PrevAtom'+str(idx)),Who=who)
                    g.set('NextAtom'+str(idx),g.randint(0,2))
                    g.declare('Previous'+str(idx),'int',0) if 'Previous'+str(idx) not in g.local else None
                    g.set('Previous'+str(idx),g.get('PrevAtom'+str(idx)))
                    for old,choices in {1:(2,3,5),2:(1,4,5),3:(4,2,5),4:(3,1,5),5:(1,2,4)}.items():
                        g.if_(g.eq(g.get('Previous'+str(idx)),old),lambda choices=choices:g.set('PrevAtom'+str(idx),g.select(g.eq(g.get('NextAtom'+str(idx)),0),choices[0],g.select(g.eq(g.get('NextAtom'+str(idx)),1),choices[1],choices[2]))))
                g.loop(g.sub(g.get('PrefixLength'),1),pre)
                if m.id.endswith('C'):
                    for c in (1,2,15):g.fn('AppendBeat',Code=c,Who=0)
            elif m.id=='M1-04':g.fn('AppendBeat',Code=25,Who=-5)
            elif m.id=='M1-07':
                g.fn('AppendBeat',Code=8,Who=0)
                def disc(j):g.fn('AppendBeat',Code=g.select(g.eq(j,g.sub(g.length('Participants'),1)),14,4),Who=g.arr('Participants',j))
                g.loop(g.sub(g.length('Participants'),1),disc)
            elif m.id=='M1-09':
                # Negative actor codes are coordinated groups, not independent root actions.
                for c,a in ((6,-2),(6,-3),(8,-4)):g.fn('AppendBeat',Code=c,Who=a)
            elif m.id=='M3-01':g.fn('AppendBeat',Code=18,Who=-1)
            elif m.id=='M3-02':
                g.fn('AppendBeat',Code=28,Who=0);g.fn('AppendBeat',Code=28,Who=7)
            else:
                for a in m.atoms:g.fn('AppendBeat',Code=codes[a],Who=who)
        g.if_(g.eq(i,idx),sequence)

def build_action_functions(fs):
    g=fs['EnterBeatState'];ids={n['id'] for n in GDATA['nodes']}
    for idx,m in enumerate(MOVELIST):
        prefix=m.id.replace('-','_')
        def enter(idx=idx,m=m,prefix=prefix):
            g.fn('EnterState',StateID=GDATA['move_roots'][m.id])
            for n in range(1,9):
                sid=prefix+'_B'+str(n)
                if sid in ids:g.if_(g.eq(g.get('BeatIndex'),n-1),lambda sid=sid:g.fn('EnterState',StateID=sid))
            if m.id in ('M2-01-C','M2-01-E'):
                def normal():
                    for code,atom in enumerate(('L','R','U','D','T'),1):
                        sid=prefix+'_P_'+atom
                        if sid in ids:g.if_(g.eq(g.arr('Beats',g.get('BeatIndex')),code),lambda sid=sid:g.fn('EnterState',StateID=sid))
                g.if_(g.lt(g.get('BeatIndex'),g.get('PrefixLength')),normal)
                if m.id.endswith('C'):
                    for off,suffix in [(0,'S_L'),(1,'S_R'),(2,'BLUE')]:g.if_(g.eq(g.get('BeatIndex'),g.add(g.get('PrefixLength'),off)),lambda suffix=suffix:g.fn('EnterState',StateID=prefix+'_'+suffix))
        g.if_(g.eq(g.get('CurrentMove'),idx),enter)
    g=fs['StartMove'];i=g.get('MoveIndex');g.set('CurrentMove',i);g.set('ActionStarted',g.get('Clock'));g.set('LastOffense',g.get('Clock'))
    g.set('BeatIndex',0);g.set('BranchVisited',False);g.set('Observed',False);g.set('RootSuccess',0.);g.set('RootSamples',0);g.set('PendingRootCommitted',False)
    g.set('ActorIndex',g.select(g.eq(g.arr('Owners',i),1),7,0));g.clear('Participants')
    g.loop(6,lambda j:g.if_(g.both(g.gt(g.arr('HP',j),0.),g.both(g.le(g.arr('BrokenUntil',j),g.get('Clock')),g.not_(g.eq(j,g.get('DetachedIndex'))))),lambda:g.append('Participants',j)),1)
    def choose_disc():
        g.declare('Candidates','int[]','');g.clear('Candidates')
        g.loop(6,lambda j:g.if_(g.both(g.gt(g.arr('HP',j),0.),g.both(g.le(g.arr('BrokenUntil',j),g.get('Clock')),g.le(distance(g,j),g.arr('Ranges',i)))),lambda:g.append('Candidates',j)))
        g.if_(g.gt(g.length('Candidates'),0),lambda:g.set('ActorIndex',g.arr('Candidates',g.randint(0,g.sub(g.length('Candidates'),1)))))
        g.if_(g.both(g.ge(g.get('SupportAt'),g.get('Clock')),g.gt(g.get('SupportCount'),0)),lambda:g.set('SupportCount',0))
    g.if_(g.eq(g.arr('Owners',i),3),choose_disc)
    g.set('BeforePrevious',g.get('PreviousMove'));g.set('PreviousMove',i)
    g.set('DangerStreak',g.select(g.arr('Danger',i),g.add(g.get('DangerStreak'),1),0))
    g.append('History',i);g.if_(g.gt(g.length('History'),4),lambda:g.do(A+'Array_Remove',TargetArray=g.get('History'),IndexToRemove=0))
    g.loop(32,lambda j:g.if_(g.gt(g.arr('Weights',j),0.),lambda:g.put('Ages',j,g.min(10.,g.add(g.arr('Ages',j),1.)))))
    g.put('Ages',i,0.);g.put('CooldownUntil',i,g.add(g.get('Clock'),g.arr('Cooldowns',i)))
    for key in ('M2-05-N','M2-05-F'):
        g.if_(g.eq(i,INDEX[key]),lambda:g.put('CooldownUntil',INDEX['M2-05-N' if key.endswith('F') else 'M2-05-F'],g.add(g.get('Clock'),8.)))
    inc(g,'AttacksStarted');g.fn('BuildCombo');g.set('ActionStage',2)
    g.set('StageUntil',g.add(g.get('Clock'),g.arr('Windups',i)))
    def formation():
        g.declare('Spread','double',0.);g.set('Spread',0.)
        g.loop(g.sub(g.length('Participants'),1),lambda j:g.set('Spread',g.max(g.get('Spread'),g.p(M+'Vector_Distance',V1=loc(g,0),V2=loc(g,g.arr('Participants',j))))))
        g.loop(g.sub(g.length('Participants'),1),lambda j:g.loop(g.sub(g.length('Participants'),1),lambda k:g.set('Spread',g.max(g.get('Spread'),g.p(M+'Vector_Distance',V1=loc(g,g.arr('Participants',j)),V2=loc(g,g.arr('Participants',k)))))))
        g.set('ActionStage',1);g.set('StageUntil',g.add(g.get('Clock'),g.select(g.le(g.get('Spread'),700.),.6,1.3)))
        g.if_(g.le(g.get('Spread'),700.),lambda:g.fn('EnterState',StateID='F_SPIN'),lambda:g.fn('EnterState',StateID='F_RISE'))
        def form_goal(j):
            a=g.arr('Participants',j);angle=g.div(g.mul(j,6.283185),g.max(1.,g.length('Participants')))
            goal=g.add(g.get('TargetLocation'),vec(g,g.mul(g.p(M+'Cos',A=angle),470.),g.mul(g.p(M+'Sin',A=angle),470.),g.select(g.le(g.get('Spread'),700.),160.,650.)))
            g.fn('SetGoal',Who=a,Goal=goal);g.fn('PlayPose',Who=a,Mode=2)
        g.loop(g.sub(g.length('Participants'),1),form_goal)
        g.if_(g.eq(i,INDEX['M1-03']),lambda:g.set('StageUntil',g.add(g.get('StageUntil'),g.mul(.22,g.sub(g.length('Participants'),1)))))
    g.if_(g.gt(g.arr('RequiredDisciples',i),0),formation,lambda:g.fn('EnterState',StateID=g.arr('MoveRootStates',i)))
    g.put('ActorBusyUntil',g.get('ActorIndex'),g.add(g.get('Clock'),12.))
    g.fn('PlayPose',Who=g.get('ActorIndex'),Mode=0)
    g.if_(g.eq(i,INDEX['M2-04']),lambda:g.fn('SetGoal',Who=0,Goal=g.add(g.get('TargetLocation'),g.mul(g.p(M+'Normal',A=g.sub(loc(g,0),g.get('TargetLocation')),Tolerance=.0001),1150.))))
    # Master must approach before committing close-range template; admission range remains enforced.
    g=fs['TickAction'];g.declare('Code','int',0)
    def regroup_done():
        g.loop(g.sub(g.length('Participants'),1),lambda j:g.fn('SetGoal',Who=g.arr('Participants',j),Goal=g.arr('HomePositions',g.arr('Participants',j))))
        g.set('ActionStage',2);g.set('StageUntil',g.add(g.get('Clock'),g.arr('Windups',g.get('CurrentMove'))));g.fn('EnterState',StateID=g.arr('MoveRootStates',g.get('CurrentMove')))
    g.if_(g.both(g.eq(g.get('ActionStage'),1),g.ge(g.get('Clock'),g.get('StageUntil'))),regroup_done)
    def beat_time():
        g.fn('ExecuteBeat')
    g.if_(g.both(g.both(g.ge(g.get('ActionStage'),2),g.le(g.get('ActionStage'),3)),g.ge(g.get('Clock'),g.get('StageUntil'))),beat_time)
    g.if_(g.both(g.eq(g.get('ActionStage'),4),g.ge(g.get('Clock'),g.get('StageUntil'))),lambda:g.fn('FinishAction'))
    g.if_(g.both(g.eq(g.get('ActionStage'),5),g.ge(g.get('Clock'),g.get('StageUntil'))),lambda:g.fn('CommitService'))
    g.if_(g.both(g.eq(g.get('ActionStage'),6),g.ge(g.get('Clock'),g.get('StageUntil'))),lambda:g.fn('FinishAction'))
    g=fs['ExecuteBeat'];g.declare('Code','int',0);g.declare('Who','int',0);g.declare('Gap','double',.5);g.declare('BranchKey','int',42)
    g.set('Code',g.arr('Beats',g.get('BeatIndex')));g.set('Who',g.arr('BeatActors',g.get('BeatIndex')))
    def emit():
        def normal():g.fn('EmitBeat',Code=g.get('Code'),Who=g.get('Who'))
        def grouped():
            g.if_(g.eq(g.get('Who'),-1),lambda:(g.fn('EmitBeat',Code=g.get('Code'),Who=0),g.fn('EmitBeat',Code=g.get('Code'),Who=7)))
            g.if_(g.eq(g.get('Who'),-5),lambda:(g.fn('EmitBeat',Code=25,Who=0),g.loop(g.sub(g.length('Participants'),1),lambda j:g.fn('EmitBeat',Code=25,Who=g.arr('Participants',j)))))
            for code,pair in [(-2,(1,2)),(-3,(3,4)),(-4,(5,6))]:
                def actors(pair=pair,code=code):
                    for actor in pair:g.fn('EmitBeat',Code=g.get('Code'),Who=actor)
                    if code==-4:g.fn('EmitBeat',Code=8,Who=0)
                g.if_(g.eq(g.get('Who'),code),actors)
        g.if_(g.ge(g.get('Who'),0),normal,grouped)
    g.fn('EnterBeatState');emit();g.set('LastImpact',g.get('Clock'));g.set('LastImpactDanger',g.ge(g.get('Code'),10));inc(g,'BeatIndex');g.set('Gap',.5)
    # Optional early-stop / observe only after second ordinary beat; never after a blue.
    def stop_node():
        g.set('BranchVisited',True)
        for off,suffix in enumerate('ABCD'):g.if_(g.eq(g.get('CurrentMove'),INDEX['M2-01-'+suffix]),lambda off=off,suffix=suffix:(g.set('BranchKey',42+off),g.fn('EnterState',StateID='M2_01_'+suffix+'_STOP_GATE')))
        stop=g.clamp(g.mul(g.add(g.sub(.12,g.mul(.06,g.div(g.get('Pressure'),100.))),g.select(g.both(g.ge(g.get('LastResult'),1),g.le(g.get('LastResult'),3)),.18,0.)),g.pure('LearningMultiplier',MoveIndex=g.get('BranchKey'))),.06,.36)
        def stop_now():g.set('BeatIndex',g.length('Beats'));g.append('ChoiceKeys',g.get('BranchKey'))
        def observe():
            g.if_(g.lt(g.rand(),g.clamp(g.mul(g.add(.12,g.mul(.08,g.div(g.get('Pressure'),100.))),g.pure('LearningMultiplier',MoveIndex=g.add(g.get('BranchKey'),4))),.04,.20)),
                  lambda:(g.set('Gap',.85),g.set('Observed',True),g.append('ChoiceKeys',g.add(g.get('BranchKey'),4))))
        g.if_(g.lt(g.rand(),stop),stop_now,observe)
    is_series=g.either(g.either(g.eq(g.get('CurrentMove'),INDEX['M2-01-A']),g.eq(g.get('CurrentMove'),INDEX['M2-01-B'])),g.either(g.eq(g.get('CurrentMove'),INDEX['M2-01-C']),g.eq(g.get('CurrentMove'),INDEX['M2-01-D'])))
    g.if_(g.both(g.both(is_series,g.eq(g.get('BeatIndex'),2)),g.not_(g.get('BranchVisited'))),stop_node)
    def spray_branch():
        g.set('BranchVisited',True);g.fn('EnterState',StateID='M2_05_F_BRANCH')
        impact=g.select(g.eq(g.get('LastResult'),1),-.55,g.select(g.eq(g.get('LastResult'),0),.45,g.select(g.eq(g.get('LastResult'),2),-.45,g.select(g.eq(g.get('LastResult'),3),-.35,g.select(g.eq(g.get('LastResult'),4),.1,0.)))))
        logit=g.add(g.add(g.add(-.15,g.mul(.65,g.div(g.get('Pressure'),100.))),impact),g.p(M+'Loge',A=g.pure('LearningMultiplier',MoveIndex=41)))
        p=g.clamp(g.div(1.,g.add(1.,g.p(M+'Exp',A=g.mul(-1.,logit)))),.15,.8)
        g.if_(g.both(g.lt(g.rand(),p),g.le(distance(g,0),1100.)),lambda:(g.fn('AppendBeat',Code=15,Who=0),g.append('ChoiceKeys',41)))
    g.if_(g.both(g.eq(g.get('CurrentMove'),INDEX['M2-05-F']),g.eq(g.get('BeatIndex'),1)),spray_branch)
    def next_beat():
        g.set('ActionStage',3);g.set('StageUntil',g.add(g.get('Clock'),g.add(g.get('Gap'),g.select(g.ge(g.arr('Beats',g.get('BeatIndex')),10),.35,0.))))
    def recover():
        g.set('ActionStage',4);g.set('StageUntil',g.add(g.get('Clock'),g.add(.18,g.arr('Recoveries',g.get('CurrentMove')))));g.fn('RecordRoot')
    g.if_(g.lt(g.get('BeatIndex'),g.length('Beats')),next_beat,recover)
    g=fs['FinishAction'];g.fn('RecordRoot');g.set('ActionStage',0);g.set('Service',0);g.set('DecisionAt',g.add(g.get('Clock'),.2))
    def return_home(j):
        angle=g.mul(j,.8976);goal=g.add(g.get('TargetLocation'),vec(g,g.mul(360.,g.p(M+'Cos',A=angle)),g.mul(360.,g.p(M+'Sin',A=angle)),0.))
        g.fn('SetGoal',Who=j,Goal=goal)
    g.loop(7,return_home)
    g.loop(7,lambda j:g.put('ActorBusyUntil',j,0.));g.fn('EnterState',StateID='S_COMPLETE')
    g=fs['TryWave']
    cond=g.both(g.eq(g.get('Phase'),1),g.both(g.ge(g.get('Clock'),g.get('WaveReady')),g.both(g.gt(g.get('ActorIndex'),0),g.eq(g.arr('RequiredDisciples',g.get('CurrentMove')),0))))
    cond=g.both(cond,g.both(g.ge(g.sub(g.get('Clock'),g.get('LastImpact')),g.select(g.get('LastImpactDanger'),.65,.35)),g.ge(g.sub(g.get('StageUntil'),g.get('Clock')),.35)))
    def wave():
        g.set('WaveReady',g.add(g.get('Clock'),4.))
        g.if_(g.lt(g.rand(),g.clamp(g.add(.18,g.mul(.1,g.div(g.get('Pressure'),100.))),.08,.28)),lambda:(g.fn('EmitBeat',Code=8,Who=0),g.set('LastImpact',g.get('Clock')),g.set('LastImpactDanger',False)))
    g.if_(cond,wave)

def build_resource_functions(fs):
    g=fs['DamageFighter'];i=g.get('Who');g.declare('Damage','double',0);g.declare('QDamage','double',0)
    def damage():
        broken=g.gt(g.arr('BrokenUntil',i),g.get('Clock'))
        g.set('Damage',g.mul(g.max(0.,g.get('HPDamage')),g.select(broken,g.get('BrokenDamageMultiplier'),1.)))
        g.set('QDamage',g.max(0.,g.get('QiDamage')))
        def guard():
            g.set('Damage',0.);g.set('QDamage',g.mul(g.get('QDamage'),2.));g.put('ActorState',i,'V_GUARD');g.fn('EnterState',StateID='V_GUARD');g.fn('PlayPose',Who=i,Mode=0);g.put('AttackPoseUntil',i,g.add(g.get('Clock'),.3))
        facing=g.p(M+'Dot_VectorVector',A=g.p('/Script/Engine.Actor.GetActorForwardVector',self=g.arr('Fighters',i)),B=g.p(M+'Normal',A=g.sub(g.get('TargetLocation'),loc(g,i)),Tolerance=.0001))
        angle_ok=g.ge(facing,g.p(M+'DegCos',A=g.get('GuardAngle')))
        g.if_(g.both(angle_ok,g.both(g.not_(g.get('BypassGuard')),g.both(g.not_(broken),g.gt(g.arr('Qi',i),0.)))),guard)
        g.put('HP',i,g.max(0.,g.sub(g.arr('HP',i),g.get('Damage'))))
        def qi_hit():
            g.put('Qi',i,g.max(0.,g.sub(g.arr('Qi',i),g.get('QDamage'))))
            def newbreak():
                g.put('BrokenStart',i,g.get('Clock'));g.put('BrokenUntil',i,g.add(g.get('Clock'),g.select(g.eq(i,0),4.,g.select(g.eq(i,7),3.5,3.))))
                g.put('ActorState',i,'Q_BREAK_START');g.fn('EnterState',StateID='Q_BREAK_START')
                g.if_(g.both(g.both(g.gt(i,0),g.lt(i,7)),g.lt(g.get('DetachedIndex'),0)),lambda:g.set('DetachedIndex',i))
            g.if_(g.le(g.arr('Qi',i),0.),newbreak)
        g.if_(g.not_(broken),qi_hit)
        def impulse():
            g.if_(g.gt(g.sub(g.get('Clock'),g.arr('ImpactAt',i)),2.),lambda:g.put('ImpactAccum',i,0.))
            g.put('ImpactAt',i,g.get('Clock'));arrplus(g,'ImpactAccum',i,g.get('Impulse'))
            g.if_(g.both(g.ge(g.arr('ImpactAccum',i),100.),g.ge(g.get('Clock'),g.arr('KnockLock',i))),
                  lambda:(g.put('GroundUntil',i,g.add(g.get('Clock'),2.8)),g.put('KnockLock',i,g.add(g.get('Clock'),5.8)),g.put('ImpactAccum',i,0.),g.fn('EnterState',StateID='Q_GROUND')))
        g.if_(g.both(g.eq(i,0),g.ge(g.get('Phase'),2)),impulse)
        interrupted=g.either(g.either(g.le(g.arr('HP',i),0.),g.gt(g.arr('GroundUntil',i),g.get('Clock'))),g.either(g.gt(g.arr('BrokenUntil',i),g.get('Clock')),g.both(g.ge(g.get('Impulse'),25.),g.gt(g.get('Damage'),0.))))
        def interrupt():
            participating=g.p(A+'Array_Contains',TargetArray=g.get('Participants'),ItemToFind=i)
            same=g.eq(i,g.get('ActorIndex'))
            def attack_interrupt():
                duet=g.eq(g.arr('Owners',g.get('CurrentMove')),2)
                affected=g.either(same,g.either(g.both(participating,g.gt(g.arr('RequiredDisciples',g.get('CurrentMove')),0)),g.both(duet,g.either(g.eq(i,0),g.eq(i,7)))))
                g.if_(affected,lambda:(g.fn('EnterState',StateID='F_BREAK'),g.fn('FinishAction'),g.set('DecisionAt',g.add(g.get('Clock'),.8))))
            g.if_(g.both(g.gt(g.get('ActionStage'),0),g.ge(g.get('CurrentMove'),0)),attack_interrupt)
            g.if_(g.both(g.eq(g.get('ActionStage'),5),g.either(g.eq(i,0),g.both(g.eq(g.get('Service'),3),g.eq(i,7)))),lambda:g.fn('FinishAction'))
        g.if_(interrupted,interrupt)
        def support():
            g.if_(g.gt(g.sub(g.get('Clock'),g.get('SupportWindow')),3.),lambda:(g.set('SupportCount',0),g.set('SupportWindow',g.get('Clock'))))
            inc(g,'SupportCount')
            g.if_(g.both(g.ge(g.get('SupportCount'),3),g.ge(g.get('Clock'),g.get('SupportReady'))),lambda:(g.set('SupportAt',g.add(g.get('Clock'),2.)),g.set('SupportReady',g.add(g.get('Clock'),4.))))
        g.if_(g.both(g.eq(g.get('Phase'),1),g.both(g.eq(i,g.get('DetachedIndex')),g.gt(g.get('HPDamage'),0.))),support)
        g.fn('PhaseCheck')
    g.if_(g.both(g.not_(g.get('Resolved')),g.both(g.ge(i,0),g.le(i,7))),lambda:g.if_(g.gt(g.arr('HP',i),0.),damage))
    g=fs['TickResources']
    def actor(i):
        def broken():
            dur=g.sub(g.arr('BrokenUntil',i),g.arr('BrokenStart',i));qi=g.mul(100.,g.clamp(g.div(g.sub(g.get('Clock'),g.arr('BrokenStart',i)),g.max(dur,.001)),0.,1.))
            g.put('Qi',i,qi)
            g.if_(g.both(g.eq(i,0),g.ge(g.get('Phase'),2)),lambda:g.put('ActorState',i,'Q_HANG'),lambda:g.put('ActorState',i,'Q_BROKEN_FREE'))
            g.if_(g.ge(g.get('Clock'),g.arr('BrokenUntil',i)),lambda:(g.put('Qi',i,100.),g.put('BrokenStart',i,-1.),g.put('ActorState',i,'Q_READY'),g.if_(g.eq(i,g.get('DetachedIndex')),lambda:g.set('DetachedIndex',-1))))
        g.if_(g.ge(g.arr('BrokenStart',i),0.),broken)
        g.if_(g.gt(g.arr('GroundUntil',i),g.get('Clock')),lambda:g.put('ActorState',i,'Q_GROUND'))
    g.loop(7,actor)

def build_health_and_phase(fs):
    g=fs['TryServices'];g.declare('Started','bool',False);g.declare('Target','int',-1);g.declare('BestHP','double',1.)
    g.set('Started',False);g.set('Target',-1);g.set('BestHP',1.)
    def m1():
        summon=g.both(g.lt(own(g,'CountLivingDisciples'),3),g.both(g.gt(g.arr('HP',0),1000.),g.ge(g.get('Clock'),g.get('SummonReady'))))
        def start_summon():
            g.set('Service',1);g.set('SummonReady',g.add(g.get('Clock'),18.));g.set('StageUntil',g.add(g.get('Clock'),1.));g.set('Started',True);g.fn('EnterState',StateID='H_SUMMON_W')
        def drain():
            g.loop(6,lambda j:g.if_(g.gt(g.arr('HP',j),g.get('BestHP')),lambda:(g.set('BestHP',g.arr('HP',j)),g.set('Target',j))),1)
            ok=g.both(g.lt(g.arr('HP',0),2250.),g.both(g.ge(g.get('Clock'),g.get('DrainReady')),g.ge(g.get('Target'),1)))
            def start():
                g.set('Service',2);g.set('ServiceTarget',g.get('Target'));g.set('DrainReady',g.add(g.get('Clock'),12.));g.set('StageUntil',g.add(g.get('Clock'),.9));g.set('Started',True);g.fn('EnterState',StateID='H_DRAIN_W')
            g.if_(ok,start)
        g.if_(summon,start_summon,drain)
    g.if_(g.both(g.eq(g.get('Phase'),1),g.le(g.arr('BrokenUntil',0),g.get('Clock'))),m1)
    redheal=g.both(g.eq(g.get('Phase'),3),g.both(g.lt(g.arr('HP',0),1600.),g.both(g.gt(g.arr('HP',7),450.),g.ge(g.get('Clock'),g.get('HealReady')))))
    def heal():
        g.set('Service',3);g.set('HealReady',g.add(g.get('Clock'),20.));g.set('StageUntil',g.add(g.get('Clock'),1.2));g.set('Started',True);g.fn('EnterState',StateID='U_HEAL_W')
    g.if_(g.both(redheal,g.le(g.arr('BrokenUntil',7),g.get('Clock'))),heal)
    g.if_(g.get('Started'),lambda:(g.set('ActionStage',5),g.set('ActorIndex',g.select(g.eq(g.get('Service'),3),7,0)),g.set('CurrentMove',-1),g.set('PendingRootCommitted',True)))
    g.return_(g.get('Started'))
    g=fs['CommitService'];g.declare('Amount','double',0.);g.declare('Need','int',0);g.declare('Born','int',0)
    def summon():
        g.set('Need',g.sub(3,own(g,'CountLivingDisciples')));g.set('Born',0)
        def commit():
            g.put('HP',0,g.sub(g.arr('HP',0),1000.))
            def birth(j):
                g.if_(g.both(g.le(g.arr('HP',j),0.),g.lt(g.get('Born'),g.get('Need'))),lambda:(g.put('HP',j,g.min(350.,g.div(800.,g.get('Need')))),g.put('Qi',j,100.),g.put('BrokenStart',j,-1.),g.put('BrokenUntil',j,0.),g.set('Born',g.add(g.get('Born'),1))))
            g.loop(6,birth,1);g.set('DrainReady',g.max(g.get('DrainReady'),g.add(g.get('Clock'),3.)));g.fn('EnterState',StateID='H_SUMMON_PAY')
        g.if_(g.both(g.gt(g.get('Need'),0),g.gt(g.arr('HP',0),1000.)),commit)
    g.if_(g.both(g.eq(g.get('Service'),1),g.eq(g.get('Phase'),1)),summon)
    def drain():
        t=g.get('ServiceTarget');g.set('Amount',g.max(0.,g.min(450.,g.min(g.sub(3000.,g.arr('HP',0)),g.sub(g.arr('HP',t),1.)))))
        g.put('HP',t,g.sub(g.arr('HP',t),g.get('Amount')));arrplus(g,'HP',0,g.get('Amount'));g.fn('EnterState',StateID='H_DRAIN_PAY')
    g.if_(g.both(g.eq(g.get('Service'),2),g.both(g.eq(g.get('Phase'),1),g.gt(g.arr('HP',0),0.))),drain)
    def heal():
        g.set('Amount',g.max(0.,g.min(300.,g.min(g.sub(4000.,g.arr('HP',0)),g.sub(g.arr('HP',7),1.)))))
        g.put('HP',7,g.sub(g.arr('HP',7),g.get('Amount')));arrplus(g,'HP',0,g.get('Amount'));g.fn('EnterState',StateID='U_HEAL_PAY')
    g.if_(g.both(g.eq(g.get('Service'),3),g.both(g.eq(g.get('Phase'),3),g.both(g.gt(g.arr('HP',0),0.),g.gt(g.arr('HP',7),0.)))),heal)
    g.set('ActionStage',6);g.set('StageUntil',g.add(g.get('Clock'),.6))
    g=fs['SetPhase'];p=g.get('NewPhase');g.set('Phase',p);inc(g,'Epoch');g.set('StageStart',g.get('Clock'));g.fn('FinishAction');g.clear('History');g.set('DangerStreak',0);g.set('DetachedIndex',-1)
    g.if_(g.eq(p,2),lambda:(g.put('HP',0,4000.),g.put('MaxHP',0,4000.),g.put('Qi',0,100.),g.put('BrokenStart',0,-1.),g.put('BrokenUntil',0,0.),g.loop(6,lambda j:g.put('HP',j,0.),1)))
    g.if_(g.eq(p,3),lambda:(g.set('RedEntered',True),g.put('HP',7,g.max(g.arr('HP',7),1800.))))
    g.if_(g.eq(p,4),lambda:(g.set('RedEntered',True),g.put('HP',7,0.)))
    for phase in (1,2,3,4):g.if_(g.eq(p,phase),lambda phase=phase:g.fn('EnterState',StateID='B_M'+str(phase)))
    g=fs['PhaseCheck']
    def active():
        g.if_(g.both(g.eq(g.get('Phase'),1),g.le(g.arr('HP',0),0.)),lambda:g.fn('SetPhase',NewPhase=2))
        g.if_(g.both(g.eq(g.get('Phase'),2),g.le(g.arr('HP',0),2000.)),lambda:g.fn('SetPhase',NewPhase=3))
        def master_dead():
            g.fn('FinishAction')
            g.if_(g.both(g.eq(g.get('Phase'),3),g.gt(g.arr('HP',7),0.)),lambda:(g.fn('EnterState',StateID='B_SUICIDE'),g.set('SuicideUntil',g.add(g.get('Clock'),2.)),g.fn('PlayPose',Who=7,Mode=4),g.put('AttackPoseUntil',7,g.add(g.get('Clock'),2.))))
            g.set('Resolved',True);g.fn('CommitLearning')
        g.if_(g.both(g.ge(g.get('Phase'),2),g.le(g.arr('HP',0),0.)),master_dead,
              lambda:g.if_(g.both(g.eq(g.get('Phase'),3),g.le(g.arr('HP',7),0.)),lambda:g.fn('SetPhase',NewPhase=4)))
    g.if_(g.not_(g.get('Resolved')),active)
    for phase in (1,2,3,4):
        g=fs['StartM'+str(phase)];g.fn('InitEncounter');
        if phase>1:g.fn('SetPhase',NewPhase=2)
        if phase>2:g.fn('SetPhase',NewPhase=phase)
        g.e.set_is_call_in_editor_function(True)
    for name,who,hp,qi,imp in [('KillRed',7,99999.,0.,0.),('KillMaster',0,99999.,0.,0.),('BreakMaster',0,0.,100.,0.),('DropMaster',0,0.,0.,100.),('BreakDisciple',1,0.,100.,0.)]:
        g=fs[name];g.fn('DamageFighter',Who=who,HPDamage=hp,QiDamage=qi,Impulse=imp,BypassGuard=True);g.e.set_is_call_in_editor_function(True)
    g=fs['ResetBattle'];g.fn('InitEncounter');g.e.set_is_call_in_editor_function(True)

def build_learning(fs,save):
    g=fs['ReportResponse'];g.declare('W','double',0);g.declare('Used','double',0);g.declare('DeltaP','double',0);g.declare('Score','double',0)
    def report():
        g.append('SeenEventIDs',g.get('EventID'));g.set('W',0.);g.set('Score',0.)
        # 0 hit,1 perfect parry,2 perfect dodge,3 ordinary dodge,4 block,5 player attack hit,6 miss,7 break,8 grab.
        for outcome,w in [(0,30),(1,-12),(2,-8),(3,-5),(4,2),(5,-1),(6,3),(7,40),(8,45)]:g.if_(g.eq(g.get('Outcome'),outcome),lambda w=w:g.set('W',float(w)))
        g.if_(g.both(g.ge(g.get('Outcome'),1),g.le(g.get('Outcome'),3)),lambda:g.set('Score',1.))
        g.if_(g.eq(g.get('Outcome'),4),lambda:g.set('Score',.65))
        g.set('Used',0.)
        def used(j):
            same=g.gt(g.mul(g.arr('PressureDeltas',j),g.get('W')),0.)
            g.if_(g.both(g.gt(g.arr('PressureTimes',j),g.sub(g.get('Clock'),2.)),same),lambda:g.set('Used',g.add(g.get('Used'),g.p(M+'Abs',A=g.arr('PressureDeltas',j)))))
        g.loop(g.sub(g.length('PressureTimes'),1),used)
        budget=g.select(g.gt(g.get('W'),0.),60.,30.)
        delta=g.mul(g.select(g.gt(g.get('W'),0.),1.,-1.),g.min(g.p(M+'Abs',A=g.get('W')),g.max(0.,g.sub(budget,g.get('Used')))))
        g.set('DeltaP',delta);g.set('Pressure',g.clamp(g.add(g.get('Pressure'),g.get('DeltaP')),-100.,100.));g.append('PressureTimes',g.get('Clock'));g.append('PressureDeltas',g.get('DeltaP'))
        # Bound rolling-storage length; semantically old samples no longer affect the 2s window.
        g.if_(g.gt(g.length('PressureTimes'),256),lambda:(g.do(A+'Array_Remove',TargetArray=g.get('PressureTimes'),IndexToRemove=0),g.do(A+'Array_Remove',TargetArray=g.get('PressureDeltas'),IndexToRemove=0)))
        g.if_(g.both(g.ge(g.get('MoveIndex'),0),g.le(g.get('Outcome'),4)),lambda:(inc(g,'RootSuccess',g.get('Score')),inc(g,'RootSamples')))
        g.set('LastResult',g.get('Outcome'))
    contains=g.p(A+'Array_Contains',TargetArray=g.get('SeenEventIDs'),ItemToFind=g.get('EventID'))
    g.if_(g.not_(contains),report)
    g=fs['RecordRoot']
    def record():
        i=g.get('CurrentMove');arrplus(g,'PendingS',i,g.div(g.get('RootSuccess'),g.get('RootSamples')));arrplus(g,'PendingN',i,1.)
        g.loop(g.sub(g.length('ChoiceKeys'),1),lambda j:(arrplus(g,'PendingS',g.arr('ChoiceKeys',j),g.div(g.get('RootSuccess'),g.get('RootSamples'))),arrplus(g,'PendingN',g.arr('ChoiceKeys',j),1.)))
        g.set('PendingRootCommitted',True)
    g.if_(g.both(g.not_(g.get('PendingRootCommitted')),g.both(g.ge(g.get('CurrentMove'),0),g.gt(g.get('RootSamples'),0))),record)
    g=fs['CommitLearning']
    def learn(i):
        scale=g.min(1.,g.div(6.,g.max(1.,g.arr('PendingN',i))))
        g.put('LearnS',i,g.add(g.mul(.9,g.arr('LearnS',i)),g.mul(scale,g.arr('PendingS',i))))
        g.put('LearnF',i,g.add(g.mul(.9,g.arr('LearnF',i)),g.mul(scale,g.sub(g.arr('PendingN',i),g.arr('PendingS',i)))))
        n=g.add(g.arr('LearnS',i),g.arr('LearnF',i));compression=g.min(1.,g.div(40.,g.max(1.,n)))
        # Store compression once, avoiding changed array values in pure re-evaluation.
        g.set('BestScore',compression);g.put('LearnS',i,g.mul(g.arr('LearnS',i),g.get('BestScore')));g.put('LearnF',i,g.mul(g.arr('LearnF',i),g.get('BestScore')))
    g.loop(49,learn)
    # Dynamic save class cast via CastTo... not needed: setter target typed from generated class below.
    def save_it():
        created=g.do('/Script/Engine.GameplayStatics.CreateSaveGameObject',SaveGameClass=save.generated_class().get_path_name()).find_result_pin()
        g.set('SaveObject',created)
        # SetArrayPropertyByName supports wildcard via dedicated property methods? use typed dynamic cast node.
        castname=next(str(x) for x in g.e.list_available_nodes([]) if str(x).endswith('|CastToBP_BossLearningSave'))
        cast=g.place(g.e.create_node_from_name(castname,u.Vector2D(0,0),[]))
        if cast:
            val(cast.find_input_pin('Object'),g.get('SaveObject'));link(g.tail,cast.find_execute_pin());g.tail=cast.find_then_pin()
            obj=next(p for p in cast.list_output_pins() if str(p.get_pin_name()).startswith('As'))
            for name,arr in [('Success','LearnS'),('Failure','LearnF')]:
                n=g.place(g.e.add_set_member_variable_node(name,save.generated_class().get_path_name()));val(n.find_self_pin(),obj);val(n.find_input_pin(name),g.get(arr));link(g.tail,n.find_execute_pin());g.tail=n.find_then_pin()
            g.do('/Script/Engine.GameplayStatics.SaveGameToSlot',SaveGameObject=g.get('SaveObject'),SlotName=g.get('LearningSlot'),UserIndex=0)
    # Saving is optional; default off so demo outcomes never contaminate player learning.
    g.if_(g.both(g.get('EnableLearningSave'),g.both(g.not_(g.get('SimulateResponses')),g.both(g.not_(g.get('AutoDemo')),g.not_(g.get('DemoDamage'))))),save_it)
    g=fs['LoadLearning']
    def load():
        loaded=g.do('/Script/Engine.GameplayStatics.LoadGameFromSlot',SlotName=g.get('LearningSlot'),UserIndex=0).find_result_pin();g.set('SaveObject',loaded)
        castname=next(str(x) for x in g.e.list_available_nodes([]) if str(x).endswith('|CastToBP_BossLearningSave'))
        cast=g.place(g.e.create_node_from_name(castname,u.Vector2D(0,0),[]));val(cast.find_input_pin('Object'),g.get('SaveObject'));link(g.tail,cast.find_execute_pin());g.tail=cast.find_then_pin()
        obj=next(p for p in cast.list_output_pins() if str(p.get_pin_name()).startswith('As'))
        fields={}
        for name in ('Success','Failure','Version'):
            n=g.place(g.e.add_get_member_variable_node(name,save.generated_class().get_path_name()));val(n.find_self_pin(),obj);fields[name]=n.find_result_pin()
        sizes=g.both(g.eq(g.p(A+'Array_Length',TargetArray=fields['Success']),50),g.eq(g.p(A+'Array_Length',TargetArray=fields['Failure']),50))
        g.if_(g.both(g.eq(fields['Version'],2),sizes),lambda:(g.set('LearnS',fields['Success']),g.set('LearnF',fields['Failure'])))
    exists=g.p('/Script/Engine.GameplayStatics.DoesSaveGameExist',SlotName=g.get('LearningSlot'),UserIndex=0)
    g.if_(g.both(g.get('EnableLearningSave'),exists),load)

def build_presentation(fs):
    g=fs['SetGoal'];g.put('Destinations',g.get('Who'),g.get('Goal'))
    g=fs['PlayPose'];who=g.get('Who');mode=g.get('Mode');g.declare('Anim',u.AnimationAsset,'')
    def pose():
        g.set('Anim','')
        g.if_(g.get('UsePlaceholderAnimations'),lambda:g.set('Anim',g.get('DefaultIdle')))
        for code,name in [(1,'DefaultRun'),(2,'DefaultJump'),(4,'DefaultDeath')]:g.if_(g.both(g.get('UsePlaceholderAnimations'),g.eq(mode,code)),lambda name=name:g.set('Anim',g.get(name)))
        def attack():
            g.if_(g.get('UsePlaceholderAnimations'),lambda:g.set('Anim',g.arr('FallbackAttacks',g.randint(0,2))))
            g.if_(g.ge(g.get('CurrentMove'),0),lambda:g.if_(valid(g,g.arr('MoveAnimations',g.get('CurrentMove'))),lambda:g.set('Anim',g.arr('MoveAnimations',g.get('CurrentMove')))))
        g.if_(g.eq(mode,3),attack)
        g.declare('AnimStateIndex','int',-1);g.set('AnimStateIndex',g.p(A+'Array_Find',TargetArray=g.get('StateIDs'),ItemToFind=g.get('ActiveState')))
        g.if_(g.ge(g.get('AnimStateIndex'),0),lambda:g.if_(valid(g,g.arr('StateAnimations',g.get('AnimStateIndex'))),lambda:g.set('Anim',g.arr('StateAnimations',g.get('AnimStateIndex')))))
        def play():g.do('/Script/Engine.SkeletalMeshComponent.PlayAnimation',self=g.arr('Meshes',who),NewAnimToPlay=g.get('Anim'),bLooping=g.lt(mode,2))
        g.if_(valid(g,g.get('Anim')),play)
        g.put('AnimationModeCache',who,mode)
    g.if_(g.both(g.ge(who,0),g.lt(who,g.length('Meshes'))),pose)
    g=fs['MoveActors'];g.declare('Position','vector','(X=0,Y=0,Z=0)');g.declare('Goal','vector','(X=0,Y=0,Z=0)');g.declare('Moving','bool',False)
    def move(i):
        def alive():
            g.do('/Script/Engine.Actor.SetActorHiddenInGame',self=g.arr('Fighters',i),bNewHidden=False)
            g.set('Position',loc(g,i));g.set('Goal',g.arr('Destinations',i))
            def hang():
                br=g.c(M+'BreakVector',InVec=g.get('Goal'))
                g.set('Goal',vec(g,br.find_output_pin('X'),br.find_output_pin('Y'),g.select(g.gt(g.arr('GroundUntil',i),g.get('Clock')),20.,g.add(230.,g.mul(15.,g.p(M+'Sin',A=g.mul(g.get('Clock'),2.)))))))
            g.if_(g.both(g.eq(i,0),g.ge(g.get('Phase'),2)),hang)
            new=g.p(M+'VInterpTo',Current=g.get('Position'),Target=g.get('Goal'),DeltaTime=g.get('Delta'),InterpSpeed=3.)
            g.do('/Script/Engine.Actor.K2_SetActorLocation',self=g.arr('Fighters',i),NewLocation=new,bSweep=False,bTeleport=False)
            look=g.c(M+'BreakRotator',InRot=g.p(M+'FindLookAtRotation',Start=new,Target=g.get('TargetLocation')))
            yaw=g.p(M+'MakeRotator',Roll=0.,Pitch=0.,Yaw=look.find_output_pin('Yaw'))
            g.do('/Script/Engine.Actor.K2_SetActorRotation',self=g.arr('Fighters',i),NewRotation=yaw,bTeleportPhysics=False)
            g.set('Moving',g.gt(g.p(M+'Vector_Distance',V1=g.get('Position'),V2=g.get('Goal')),35.))
            def locomotion():
                mode=g.select(g.get('Moving'),1,0)
                g.if_(g.not_(g.eq(g.arr('AnimationModeCache',i),mode)),lambda:g.fn('PlayPose',Who=i,Mode=mode))
            ready=g.both(g.le(g.arr('BrokenUntil',i),g.get('Clock')),g.le(g.arr('GroundUntil',i),g.get('Clock')))
            g.if_(g.both(g.ge(g.get('Clock'),g.arr('AttackPoseUntil',i)),ready),locomotion)
            def incapacitated():
                g.fn('SetGoal',Who=i,Goal=g.get('Position'))
                mode=g.select(g.gt(g.arr('GroundUntil',i),g.get('Clock')),4,0)
                g.if_(g.not_(g.eq(g.arr('AnimationModeCache',i),mode)),lambda:g.fn('PlayPose',Who=i,Mode=mode))
            g.if_(g.not_(ready),incapacitated)
        def dead():g.do('/Script/Engine.Actor.SetActorHiddenInGame',self=g.arr('Fighters',i),bNewHidden=True)
        g.if_(valid(g,g.arr('Fighters',i)),lambda:g.if_(g.gt(g.arr('HP',i),0.),alive,dead))
        def sword():
            g.do('/Script/Engine.Actor.SetActorHiddenInGame',self=g.arr('Swords',i),bNewHidden=g.le(g.arr('HP',i),0.))
            t=g.clamp(g.div(g.sub(g.get('Clock'),g.arr('PoseStart',i)),.55),0.,1.)
            yaw=g.select(g.lt(g.get('Clock'),g.arr('AttackPoseUntil',i)),g.mul(g.sub(g.mul(t,2.),1.),100.),0.)
            rot=g.p(M+'MakeRotator',Roll=0.,Pitch=g.select(g.eq(g.arr('LastBeatCodes',i),5),75.,20.),Yaw=yaw)
            g.do('/Script/Engine.Actor.K2_SetActorRelativeRotation',self=g.arr('Swords',i),NewRelativeRotation=rot,bSweep=False,bTeleport=False)
        g.if_(g.lt(i,g.length('Swords')),lambda:g.if_(valid(g,g.arr('Swords',i)),sword))
    g.loop(7,move)
    g=fs['EmitBeat'];who=g.get('Who');code=g.get('Code');g.declare('Color','color','(R=1,G=1,B=1,A=1)')
    def emit():
        inc(g,'HitsExecuted');g.fn('PlayPose',Who=who,Mode=3);g.put('AttackPoseUntil',who,g.add(g.get('Clock'),.85));g.put('LastBeatCodes',who,code);g.put('PoseStart',who,g.get('Clock'))
        g.set('Color','(R=0.9,G=0.9,B=0.7,A=1)')
        g.if_(g.ge(code,10),lambda:g.set('Color','(R=0.05,G=0.45,B=1,A=1)'))
        g.if_(g.ge(code,20),lambda:g.set('Color','(R=1,G=0.04,B=0.015,A=1)'))
        g.if_(g.ge(code,30),lambda:g.set('Color','(R=0.3,G=0.02,B=0.55,A=1)'))
        start=loc(g,who);target=g.get('TargetLocation')
        def debug():
            g.do(K+'DrawDebugLine',LineStart=g.add(start,vec(g,0.,0.,100.)),LineEnd=g.add(target,vec(g,0.,0.,80.)),LineColor=g.get('Color'),Duration=.35,Thickness=7.)
            g.do(K+'DrawDebugSphere',Center=g.add(target,vec(g,0.,0.,70.)),Radius=90.,Segments=16,LineColor=g.get('Color'),Duration=.22,Thickness=3.)
            def spray():
                direction=g.c(M+'BreakVector',InVec=g.p(M+'Normal',A=g.sub(target,start),Tolerance=.0001))
                side=vec(g,g.mul(-1.,direction.find_output_pin('Y')),direction.find_output_pin('X'),0.)
                g.loop(6,lambda j:g.do(K+'DrawDebugLine',LineStart=g.add(start,vec(g,0.,0.,100.)),LineEnd=g.add(g.add(target,vec(g,0.,0.,80.)),g.mul(side,g.mul(g.sub(j,3.),120.))),LineColor=g.get('Color'),Duration=.5,Thickness=4.))
            g.if_(g.either(g.eq(code,9),g.eq(code,29)),spray)
            g.if_(g.ge(code,30),lambda:g.do(K+'DrawDebugCylinder',Start=g.add(target,vec(g,0.,0.,5.)),End=g.add(target,vec(g,0.,0.,200.)),Radius=110.,Segments=16,LineColor=g.get('Color'),Duration=.5,Thickness=4.))
        g.if_(g.get('DrawCombatDebug'),debug)
        # Lunges/jumps move the mannequin itself, not merely a debug caption.
        delta=g.sub(start,target);direction=g.p(M+'Normal',A=delta,Tolerance=.0001)
        goal=g.add(target,g.mul(direction,160.))
        ranged=g.either(g.either(g.eq(code,8),g.eq(code,9)),g.either(g.eq(code,28),g.eq(code,29)))
        g.if_(g.not_(ranged),lambda:g.fn('SetGoal',Who=who,Goal=goal))
        g.if_(g.either(g.eq(code,6),g.eq(code,16)),lambda:g.fn('SetGoal',Who=who,Goal=g.add(goal,vec(g,0.,0.,180.))))
        def response():
            g.set('LastResult',g.select(g.lt(g.rand(),g.get('ResponseSkill')),1,0))
            g.if_(g.both(g.ge(code,20),g.eq(g.get('LastResult'),1)),lambda:g.set('LastResult',2))
            # A grouped impact is one player response window; all actors share this event key.
            eventid=g.p('/Script/Engine.KismetStringLibrary.Conv_DoubleToString',InDouble=g.get('Clock'))
            g.fn('ReportResponse',EventID=eventid,Outcome=g.get('LastResult'),MoveIndex=g.get('CurrentMove'))
        g.if_(g.get('SimulateResponses'),response)
    g.if_(g.both(g.gt(g.arr('HP',who),0.),g.both(g.le(g.arr('BrokenUntil',who),g.get('Clock')),g.le(g.arr('GroundUntil',who),g.get('Clock')))),emit)
    g=fs['Telegraph'];g.declare('Code','int',0);g.declare('Who','int',0);g.declare('Color','color','(R=1,G=1,B=1,A=1)')
    def telegraph():
        g.set('Code',g.arr('Beats',g.get('BeatIndex')));g.set('Who',g.max(0,g.arr('BeatActors',g.get('BeatIndex'))))
        g.set('Color','(R=0.8,G=0.75,B=0.35,A=1)')
        g.if_(g.ge(g.get('Code'),10),lambda:g.set('Color','(R=0.02,G=0.3,B=1,A=1)'))
        g.if_(g.ge(g.get('Code'),20),lambda:g.set('Color','(R=1,G=0.02,B=0.01,A=1)'))
        g.if_(g.ge(g.get('Code'),30),lambda:g.set('Color','(R=0.16,G=0.005,B=0.25,A=1)'))
        def circle(who):
            g.do(K+'DrawDebugSphere',Center=g.add(loc(g,who),vec(g,0.,0.,110.)),Radius=90.,Segments=12,LineColor=g.get('Color'),Duration=0.,Thickness=3.)
        circle(g.get('Who'))
        g.if_(g.eq(g.arr('BeatActors',g.get('BeatIndex')),-1),lambda:circle(7))
    g.if_(g.both(g.get('DrawCombatDebug'),g.both(g.both(g.ge(g.get('ActionStage'),2),g.le(g.get('ActionStage'),3)),g.lt(g.get('BeatIndex'),g.length('Beats')))),telegraph)
    g=fs['DrawHUD'];g.declare('Text','string','')
    phase=g.p('/Script/Engine.KismetStringLibrary.Conv_IntToString',InInt=g.get('Phase'))
    press=g.p('/Script/Engine.KismetStringLibrary.Conv_DoubleToString',InDouble=g.get('Pressure'))
    text=g.p('/Script/Engine.KismetStringLibrary.Concat_StrStr',A='BOSS LAB | PHASE ',B=phase)
    text=g.p('/Script/Engine.KismetStringLibrary.Concat_StrStr',A=text,B=' | State: ')
    text=g.p('/Script/Engine.KismetStringLibrary.Concat_StrStr',A=text,B=g.get('ActiveState'))
    text=g.p('/Script/Engine.KismetStringLibrary.Concat_StrStr',A=text,B=' | Pressure: ')
    text=g.p('/Script/Engine.KismetStringLibrary.Concat_StrStr',A=text,B=press)
    g.do(K+'PrintString',InString=text,bPrintToScreen=True,bPrintToLog=False,TextColor='(R=0.7,G=0.9,B=1,A=1)',Duration=.12,Key='BossHUD')
    g.do(K+'PrintString',InString='1-4 Phase | B Break | G Knockdown | H Hit disciple | K Kill red | J Kill master | R Reset | Space Pause | T Threat',bPrintToScreen=True,bPrintToLog=False,TextColor='(R=0.8,G=0.8,B=0.8,A=1)',Duration=.12,Key='BossKeys')

def build_controls(fs):
    g=fs['ReadControls'];pc=g.p('/Script/Engine.GameplayStatics.GetPlayerController',PlayerIndex=0)
    def keys():
        for key,fn in [('One','StartM1'),('Two','StartM2'),('Three','StartM3'),('Four','StartM4'),('B','BreakMaster'),('G','DropMaster'),('K','KillRed'),('J','KillMaster'),('R','ResetBattle')]:
            g.if_(g.p('/Script/Engine.PlayerController.WasInputKeyJustPressed',self=pc,Key='(KeyName='+key+')'),lambda fn=fn:g.fn(fn))
        g.if_(g.p('/Script/Engine.PlayerController.WasInputKeyJustPressed',self=pc,Key='(KeyName=SpaceBar)'),lambda:g.set('PauseEncounter',g.not_(g.get('PauseEncounter'))))
        g.if_(g.p('/Script/Engine.PlayerController.WasInputKeyJustPressed',self=pc,Key='(KeyName=H)'),lambda:g.fn('DamageFighter',Who=1,HPDamage=35.,QiDamage=30.,Impulse=30.,BypassGuard=True))
        g.if_(g.p('/Script/Engine.PlayerController.WasInputKeyJustPressed',self=pc,Key='(KeyName=T)'),lambda:g.fn('NotifyThreat',Who=0))
    g.if_(valid(g,pc),keys)
    g=fs['NotifyThreat'];i=g.get('Who')
    def react():
        def dodge():
            g.put('DodgeReady',i,g.add(g.get('Clock'),g.get('DodgeCooldown')));g.put('ActorState',i,'V_DODGE');g.fn('EnterState',StateID='V_DODGE')
            direction=g.p(M+'Normal',A=g.sub(loc(g,i),g.get('TargetLocation')),Tolerance=.0001)
            g.fn('SetGoal',Who=i,Goal=g.add(loc(g,i),g.mul(direction,250.)));g.fn('PlayPose',Who=i,Mode=2);g.put('AttackPoseUntil',i,g.add(g.get('Clock'),.6))
        def guard():g.put('ActorState',i,'V_GUARD');g.fn('EnterState',StateID='V_GUARD');g.fn('PlayPose',Who=i,Mode=0)
        g.if_(g.both(g.ge(g.get('Clock'),g.arr('DodgeReady',i)),g.lt(g.rand(),.35)),dodge,guard)
    g.if_(g.both(g.ge(i,0),g.le(i,7)),lambda:g.if_(g.both(g.gt(g.arr('HP',i),0.),g.both(g.le(g.arr('BrokenUntil',i),g.get('Clock')),g.le(g.arr('ActorBusyUntil',i),g.get('Clock')))),react))

def build_lifecycle(fs):
    g=fs['InitEncounter'];g.set('Clock',0.);g.set('Phase',1);g.set('Pressure',0.);g.set('Resolved',False);g.set('ActionStage',0);g.set('DecisionAt',2.);g.set('StageStart',0.);g.set('CurrentMove',-1);g.set('DetachedIndex',-1);g.set('RedEntered',False);g.set('DangerStreak',0);g.set('PreviousMove',-1);g.set('BeforePrevious',-1);g.set('DemoDamageAt',4.);g.set('OpenerPending',True);g.set('SuicideUntil',-1.);g.set('PauseEncounter',False);g.set('LastResult',-1);g.set('SupportCount',0);g.set('SupportAt',-1.);g.set('LastImpact',-10.);inc(g,'Epoch');inc(g,'BattleIndex')
    for arr in ('Participants','Beats','BeatActors','History','SeenEventIDs','PressureTimes','PressureDeltas','ChoiceKeys'):g.clear(arr)
    g.loop(32,lambda i:(g.put('CooldownUntil',i,0.),g.put('Weights',i,0.),g.put('Probabilities',i,0.),g.put('Ages',i,0.),g.put('PendingS',i,0.),g.put('PendingN',i,0.)))
    g.loop(49,lambda i:(g.put('PendingS',i,0.),g.put('PendingN',i,0.)))
    state_index={n['id']:j for j,n in enumerate(GDATA['nodes'])}
    for item in json.loads((ROOT/'Research/Step3/asset_bindings.json').read_text(encoding='utf8'))['resources']:
        if item['name'].startswith('AN_'):g.put('StateAnimations',state_index[item['state']],g.get(item['name']))
    def reset(i):
        hp=g.select(g.eq(i,0),3000.,g.select(g.eq(i,7),0.,350.))
        g.put('HP',i,hp);g.put('MaxHP',i,g.select(g.eq(i,7),1800.,hp));g.put('Qi',i,100.);g.put('BrokenStart',i,-1.)
        for arr in ('BrokenUntil','GroundUntil','KnockLock','ActorBusyUntil','AttackPoseUntil','ImpactAccum','ImpactAt'):g.put(arr,i,0.)
        g.put('Destinations',i,g.arr('HomePositions',i));g.put('ActorState',i,'S_IDLE');g.put('AnimationModeCache',i,-1)
    g.loop(7,reset)
    for n in ('SummonReady','DrainReady','HealReady','WaveReady','SupportReady'):g.set(n,0.)
    g.fn('EnterState',StateID='B_M1')
    g=fs['TickEncounter'];g.set('Delta',g.min(g.get('Seconds'),.1));inc(g,'Clock',g.get('Delta'));inc(g,'FrameCounter')
    g.set('Pressure',g.mul(g.get('Pressure'),g.p(M+'Power',Base=2.,Exp=g.div(g.mul(-1.,g.get('Delta')),12.))))
    def target():
        g.set('TargetLocation',vec(g,g.mul(g.get('TargetMoveRadius'),g.p(M+'Cos',A=g.mul(g.get('Clock'),g.get('TargetMoveSpeed')))),g.mul(g.get('TargetMoveRadius'),g.p(M+'Sin',A=g.mul(g.get('Clock'),g.get('TargetMoveSpeed')))),0.))
        g.if_(valid(g,g.get('TargetActor')),lambda:g.do('/Script/Engine.Actor.K2_SetActorLocation',self=g.get('TargetActor'),NewLocation=g.get('TargetLocation'),bSweep=False,bTeleport=False))
    g.if_(g.get('MoveTarget'),target,lambda:g.if_(valid(g,g.get('TargetActor')),lambda:g.set('TargetLocation',g.p('/Script/Engine.Actor.K2_GetActorLocation',self=g.get('TargetActor')))))
    g.fn('TickResources');g.fn('TickDemo');g.fn('PhaseCheck')
    def active():
        g.fn('TickAction')
        g.if_(g.ge(g.get('CurrentMove'),0),lambda:g.if_(g.both(g.ge(g.get('ActionStage'),2),g.le(g.get('ActionStage'),3)),lambda:g.fn('TryWave')))
        def decide():
            g.set('DecisionAt',g.add(g.get('Clock'),.75))
            def attack():
                picked=own(g,'ChooseMove');g.set('CurrentMove',picked)
                g.if_(g.both(g.eq(g.get('Phase'),1),g.get('OpenerPending')),lambda:g.if_(own(g,'CanMove',MoveIndex=INDEX['M1-04']),lambda:(g.set('CurrentMove',INDEX['M1-04']),g.set('OpenerPending',False))))
                def support_pick():
                    g.if_(own(g,'CanMove',MoveIndex=INDEX['M1-01-J']),lambda:g.set('CurrentMove',INDEX['M1-01-J']))
                g.if_(g.both(g.eq(g.get('Phase'),1),g.ge(g.get('SupportAt'),g.get('Clock'))),support_pick)
                def choose():
                    p=g.clamp(g.add(.7,g.mul(.18,g.div(g.get('Pressure'),100.))),.52,.88)
                    yes=g.either(g.ge(g.sub(g.get('Clock'),g.get('LastOffense')),3.),g.lt(g.rand(),p))
                    g.if_(yes,lambda:g.fn('StartMove',MoveIndex=g.get('CurrentMove')),
                          lambda:g.fn('EnterState',StateID='M_STAND'))
                g.if_(g.ge(g.get('CurrentMove'),0),choose,lambda:g.fn('EnterState',StateID='M_CHASE'))
                # Reposition available actors when waiting; low Qi does not recover.
                def reposition(i):
                    angle=g.add(g.mul(i,.8976),g.mul(g.get('Clock'),.09))
                    radius=g.select(g.eq(i,0),260.,g.select(g.eq(i,7),240.,380.))
                    goal=g.add(g.get('TargetLocation'),vec(g,g.mul(radius,g.p(M+'Cos',A=angle)),g.mul(radius,g.p(M+'Sin',A=angle)),0.))
                    g.if_(g.both(g.gt(g.arr('HP',i),0.),g.both(g.le(g.arr('ActorBusyUntil',i),g.get('Clock')),g.le(g.arr('BrokenUntil',i),g.get('Clock')))),lambda:g.fn('SetGoal',Who=i,Goal=goal))
                g.loop(7,reposition)
            g.if_(g.not_(own(g,'TryServices')),attack)
        g.if_(g.both(g.eq(g.get('ActionStage'),0),g.ge(g.get('Clock'),g.get('DecisionAt'))),decide)
    g.if_(g.not_(g.get('Resolved')),active)
    g.if_(g.both(g.gt(g.get('SuicideUntil'),0.),g.ge(g.get('Clock'),g.get('SuicideUntil'))),lambda:(g.put('HP',7,0.),g.set('SuicideUntil',-1.),g.fn('EnterState',StateID='B_VICTORY')))
    g.fn('MoveActors')
    g.fn('Telegraph')
    g.if_(g.get('ShowHUD'),lambda:g.fn('DrawHUD'))
    g=fs['TickDemo'];elapsed=g.sub(g.get('Clock'),g.get('StageStart'))
    def demo():
        def advance():
            phase=g.get('Phase')
            def p1():g.fn('DamageFighter',Who=0,HPDamage=99999.,QiDamage=0.,Impulse=0.,BypassGuard=True)
            def p2():g.fn('DamageFighter',Who=0,HPDamage=g.max(0.,g.sub(g.arr('HP',0),1900.)),QiDamage=0.,Impulse=0.,BypassGuard=True)
            def p3():g.fn('DamageFighter',Who=g.select(g.get('MasterDiesFirst'),0,7),HPDamage=99999.,QiDamage=0.,Impulse=0.,BypassGuard=True)
            # Snapshot phase so multiple branches cannot consume a new phase in same tick.
            g.declare('OldPhase','int',0);g.set('OldPhase',phase)
            for n,fn in ((1,p1),(2,p2),(3,p3),(4,p1)):g.if_(g.eq(g.get('OldPhase'),n),fn)
        g.if_(g.ge(elapsed,g.get('DemoStageSeconds')),advance)
    g.if_(g.both(g.get('AutoDemo'),g.not_(g.get('Resolved'))),demo)
    def damage_demo():
        g.set('DemoDamageAt',g.add(g.get('Clock'),4.))
        g.fn('DamageFighter',Who=g.select(g.eq(g.get('Phase'),1),g.randint(1,6),0),HPDamage=60.,QiDamage=22.,Impulse=25.,BypassGuard=False)
    g.if_(g.both(g.get('DemoDamage'),g.ge(g.get('Clock'),g.get('DemoDamageAt'))),damage_demo)
    g.if_(g.both(g.get('Resolved'),g.get('LoopDemo')),lambda:g.fn('InitEncounter'))

def fill_defaults(bp):
    c=u.get_default_object(bp.generated_class());n=len(MOVELIST)
    values={'MoveIDs':[m.id for m in MOVELIST],'BaseWeights':[m.base for m in MOVELIST],'PressureSlopes':[m.pressure for m in MOVELIST],
            'Ranges':[m.reach for m in MOVELIST],'Ideals':[m.ideal for m in MOVELIST],'Widths':[m.width for m in MOVELIST],
            'Cooldowns':[m.cooldown for m in MOVELIST],'Windups':[m.windup for m in MOVELIST],'Recoveries':[m.recovery for m in MOVELIST],
            'Owners':[{'M':0,'R':1,'D':2,'G':3,'Q':4}[m.owner] for m in MOVELIST],
            'MinPhase':[min(m.phases) for m in MOVELIST],'MaxPhase':[max(m.phases) for m in MOVELIST],
            'RequiredDisciples':[m.disciples for m in MOVELIST],'Danger':[m.danger for m in MOVELIST],
            'MoveAnimations':[None]*n,'FrozenProb':[False]*n,'StateIDs':[nd['id'] for nd in GDATA['nodes']],
            'StateVisitCounts':[0]*len(GDATA['nodes']),'ActorState':['S_IDLE']*8,'AnimationModeCache':[-1]*8,
            'MoveRootStates':[GDATA['move_roots'][m.id] for m in MOVELIST],'LastBeatCodes':[0]*8,'PoseStart':[-10.]*8,
            'StateAnimations':[None]*len(GDATA['nodes']),'LengthWeights':[0.]*4,'LengthProbs':[0.]*4,'LengthFrozen':[False]*4}
    for name in ('CooldownUntil','Weights','Probabilities','Ages','LearnS','LearnF','PendingS','PendingN','BranchS','BranchF'):values[name]=[0.]*n
    for name in ('LearnS','LearnF','PendingS','PendingN'):values[name]=[0.]*50
    for name in ('HP','MaxHP','Qi','BrokenUntil','GroundUntil','KnockLock','ImpactAccum','ImpactAt','GuardReady','DodgeReady','ActorBusyUntil','AttackPoseUntil'):values[name]=[0.]*8
    values['BrokenStart']=[-1.]*8
    for name in ('HomePositions','Destinations'):values[name]=[u.Vector(600*math.cos(j*math.pi/4),600*math.sin(j*math.pi/4),0) for j in range(8)]
    folder='/Game/Characters/Mannequins/Anims/Unarmed/'
    paths={'DefaultIdle':folder+'MM_Idle','DefaultRun':folder+'Run/MF_Unarmed_Run_Fwd','DefaultJump':folder+'Jump/MM_Jump','DefaultDeath':'/Game/Characters/Mannequins/Anims/Death/MM_Death_Front_01'}
    for name,path in paths.items():
        asset=u.load_asset(path)
        if not asset and name=='DefaultRun':
            candidates=u.EditorAssetLibrary.list_assets(folder+'Run',recursive=True);asset=u.load_asset(candidates[0]) if candidates else None
        values[name]=asset
    values['FallbackAttacks']=[u.load_asset(folder+'Attack/MM_Attack_0'+str(i)) for i in (1,2,3)]
    for name,v in values.items():c.set_editor_property(name,v)

def build_single_page(bp):
    g=Graph(bp);g.x=-1800;g.y=-2200
    begin=g.event('ReceiveBeginPlay')
    g.fn('InitEncounter');g.fn('LoadLearning')
    g.if_(g.ge(g.get('StartingPhase'),2),lambda:g.fn('SetPhase',NewPhase=2))
    g.if_(g.ge(g.get('StartingPhase'),3),lambda:g.fn('SetPhase',NewPhase=g.min(4,g.get('StartingPhase'))))
    pc=g.p('/Script/Engine.GameplayStatics.GetPlayerController',PlayerIndex=0)
    g.if_(valid(g,g.get('CameraActor')),lambda:g.do('/Script/Engine.PlayerController.SetViewTargetWithBlend',self=pc,NewViewTarget=g.get('CameraActor'),BlendTime=0.))
    # Register transition definitions from the same linked state nodes the user can inspect.
    state_nodes={}
    path=bp.generated_class().get_path_name()
    for nd in GDATA['nodes']:
        n=g.e.add_call_function_node(path+':DefineState');n.set_node_pos(u.IntPoint(int(nd['x']*2.8),int(nd['y']*2.7)))
        for key,value in [('StateID',nd['id']),('DisplayName',nd['title']),('Hierarchy',nd.get('hierarchy',''))]:val(n.find_input_pin(key),value)
        comment=g.e.add_comment_node(nd['id']+' | '+nd['title']+'\n'+nd['body'],u.Vector2D(nd['x']*2.8-12,nd['y']*2.7-75),u.Vector2D(450,310))
        L.set_comment_color(comment,u.LinearColor(.08,.20,.24,1.))
        state_nodes[nd['id']]=n
    offsets={}
    for ed in GDATA['edges']:
        src=next(nd for nd in GDATA['nodes'] if nd['id']==ed['source']);offset=offsets.get(src['id'],0);offsets[src['id']]=offset+1
        n=g.e.add_call_function_node(path+':RegisterTransition')
        n.set_node_pos(u.IntPoint(int(src['x']*2.8+480),int(src['y']*2.7+offset*130)))
        link(state_nodes[ed['source']].find_result_pin(),n.find_input_pin('FromState'));link(state_nodes[ed['target']].find_result_pin(),n.find_input_pin('ToState'))
        val(n.find_input_pin('Guard'),ed['guard']);val(n.find_input_pin('Kind'),ed['kind']);val(n.find_input_pin('Priority'),ed['priority'])
        link(g.tail,n.find_execute_pin());g.tail=n.find_then_pin()
    for group in GDATA['groups']:
        c=g.e.add_comment_node(group['title']+'\n'+group['subtitle'],u.Vector2D(group['x']*2.8-60,group['y']*2.7-100),u.Vector2D(group['width']*2.8,group['height']*2.7))
        L.set_comment_color(c,u.LinearColor(.10,.16,.22,1.))
    g.x=-1800;g.y=-1100;g.counter=0;tick=g.event('ReceiveTick')
    g.fn('ReadControls');g.if_(g.not_(g.get('PauseEncounter')),lambda:g.fn('TickEncounter',Seconds=tick.find_output_pin('DeltaSeconds')))
    g.e.add_comment_node('RUNNING BLUEPRINT HFSM | Native Tick / weighted decision / finite combo / phase & resource services\nState registry and all transition guards are expanded on this EventGraph. Functions contain executable calculations.',u.Vector2D(-1900,-2400),u.Vector2D(4000,1800))

if __name__=='__main__':
    try:build()
    except Exception:
        (REPORT/'build_error.txt').write_text(traceback.format_exc(),encoding='utf8');raise
