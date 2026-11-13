"""Create the self-contained BossLab observation arena with existing UE template assets."""
from pathlib import Path
import json,math,traceback
import unreal as u
ROOT=Path(u.Paths.convert_relative_path_to_full(u.Paths.project_dir()))
OUT=ROOT/'Saved/BossImplementation';OUT.mkdir(parents=True,exist_ok=True)
BASE='/Game/BossLab';AS=u.get_editor_subsystem(u.EditorActorSubsystem)

def material(name,color,emission=0,metal=.0):
    path=BASE+'/Materials/'+name;m=u.load_asset(path)
    if m:return m
    m=u.AssetToolsHelpers.get_asset_tools().create_asset(name,BASE+'/Materials',u.Material,u.MaterialFactoryNew())
    lib=u.MaterialEditingLibrary
    c=lib.create_material_expression(m,u.MaterialExpressionConstant3Vector,-400,0);c.set_editor_property('constant',u.LinearColor(*color,1))
    lib.connect_material_property(c,'',u.MaterialProperty.MP_BASE_COLOR)
    r=lib.create_material_expression(m,u.MaterialExpressionConstant,-400,180);r.set_editor_property('r',.6);lib.connect_material_property(r,'',u.MaterialProperty.MP_ROUGHNESS)
    if emission:
        v=lib.create_material_expression(m,u.MaterialExpressionConstant3Vector,-400,300);v.set_editor_property('constant',u.LinearColor(*(x*emission for x in color),1));lib.connect_material_property(v,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
    lib.recompile_material(m);u.EditorAssetLibrary.save_loaded_asset(m);return m

def spawn(cls,label,loc=(0,0,0),rot=(0,0,0)):
    a=AS.spawn_actor_from_class(cls,u.Vector(*loc),u.Rotator(*rot));a.set_actor_label(label);return a

def mesh(label,asset,loc,scale,mat,rotation=(0,0,0)):
    a=spawn(u.StaticMeshActor,label,loc,rotation);c=a.static_mesh_component;c.set_mobility(u.ComponentMobility.MOVABLE);c.set_static_mesh(u.load_asset(asset));c.set_material(0,mat);a.set_actor_scale3d(u.Vector(*scale));return a

def main():
    level=u.get_editor_subsystem(u.LevelEditorSubsystem)
    if level.is_in_play_in_editor():level.editor_request_end_play();raise RuntimeError('End Play requested; rerun build_scene after PIE closes')
    target=BASE+'/Maps/L_BossLab'
    if u.EditorAssetLibrary.does_asset_exist(target):
        level.load_level(target)
        for a in AS.get_all_level_actors():
            if a.get_actor_label().startswith('BossLab_'):AS.destroy_actor(a)
    else:level.new_level(target)
    white=material('M_MannequinWhite',(.78,.81,.85));red=material('M_RedBoss',(.48,.025,.035));gray=material('M_Disciple',(.38,.44,.50))
    floor=material('M_ArenaFloor',(.07,.09,.12));wall=material('M_ArenaStone',(.14,.18,.23));gold=material('M_ArenaGold',(.7,.45,.13),.3)
    cyan=material('M_TargetCyan',(.02,.6,.8),1.);blade=material('M_Blade',(.7,.8,.9),.2)
    mesh('BossLab_Arena','/Engine/BasicShapes/Cylinder',(0,0,-35),(32,32,.7),floor)
    for j in range(24):
        ang=j*math.pi/12
        mesh('BossLab_Rim_'+str(j),'/Engine/BasicShapes/Cube',(1540*math.cos(ang),1540*math.sin(ang),25),(2.,.15,.15),gold,(0,math.degrees(ang)+90,0))
    for j in range(8):
        ang=j*math.pi/4
        mesh('BossLab_Column_'+str(j),'/Engine/BasicShapes/Cube',(1800*math.cos(ang),1800*math.sin(ang),230),(1.2,1.2,4.6),wall)
    light=spawn(u.DirectionalLight,'BossLab_Key',(0,0,1500),(-48,-35,0));light.light_component.set_editor_property('intensity',3.)
    sky=spawn(u.SkyLight,'BossLab_Sky',(0,0,1000));sky.light_component.set_editor_property('intensity',1.3);sky.light_component.set_editor_property('real_time_capture',True)
    spawn(u.SkyAtmosphere,'BossLab_Atmosphere')
    fill=spawn(u.PointLight,'BossLab_Fill',(-800,-500,700));fill.light_component.set_editor_property('intensity',5000.);fill.light_component.set_editor_property('attenuation_radius',3500.)
    post=spawn(u.PostProcessVolume,'BossLab_Exposure');post.set_editor_property('unbound',True)
    settings=post.get_editor_property('settings')
    for k,v in [('override_auto_exposure_min_brightness',True),('override_auto_exposure_max_brightness',True),('auto_exposure_min_brightness',1.),('auto_exposure_max_brightness',1.),('override_auto_exposure_bias',True),('auto_exposure_bias',0.)]:settings.set_editor_property(k,v)
    post.set_editor_property('settings',settings)
    cam=spawn(u.CameraActor,'BossLab_ObservationCamera',(1350,-1550,1250));cam.set_actor_rotation(u.MathLibrary.find_look_at_rotation(cam.get_actor_location(),u.Vector(0,0,140)),False)
    cam.camera_component.set_editor_property('field_of_view',60.)
    targetactor=mesh('BossLab_TargetDummy','/Engine/BasicShapes/Cylinder',(300,0,0),(.65,.65,2.0),cyan)
    # Geometry is authored above its logical foot origin, so movement can keep Z=0.
    targetactor.static_mesh_component.set_relative_location(u.Vector(0,0,50),False,False)
    fighters=[];meshes=[];homes=[];swords=[]
    idle=u.load_asset('/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle')
    for i in range(8):
        pos=(-550,0,0) if i==0 else (600,300,0) if i==7 else (650*math.cos((i-1)*math.pi/3),650*math.sin((i-1)*math.pi/3),0)
        a=spawn(u.SkeletalMeshActor,['BossLab_Master']+[f'BossLab_Disciple{j}' for j in range(1,7)]+['BossLab_Red'] if False else ('BossLab_Master' if i==0 else 'BossLab_Red' if i==7 else f'BossLab_Disciple{i}'),pos)
        c=a.skeletal_mesh_component;c.set_mobility(u.ComponentMobility.MOVABLE)
        sk=u.load_asset('/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple' if i==7 else '/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple');c.set_skeletal_mesh_asset(sk)
        for slot in range(c.get_num_materials()):c.set_material(slot,red if i==7 else white if i==0 else gray)
        c.set_animation_mode(u.AnimationMode.ANIMATION_SINGLE_NODE)
        if idle:c.set_animation(idle);c.set_editor_property('animation_data',u.SingleAnimationPlayData(anim_to_play=idle,saved_looping=True,saved_playing=True))
        sword=mesh('BossLab_Sword_'+str(i),'/Engine/BasicShapes/Cube',(0,0,0),(.045,.065,1.15),blade)
        sword.attach_to_component(c,'hand_r',u.AttachmentRule.SNAP_TO_TARGET,u.AttachmentRule.SNAP_TO_TARGET,u.AttachmentRule.KEEP_WORLD,False)
        sword.set_actor_relative_location(u.Vector(0,0,45),False,False)
        sword.static_mesh_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        swords.append(sword)
        a.set_actor_scale3d(u.Vector(1.12,1.12,1.12) if i==0 else u.Vector(1,1,1))
        if i==7:a.set_actor_hidden_in_game(True)
        fighters.append(a);meshes.append(c);homes.append(u.Vector(*pos))
    report=json.loads((OUT/'blueprint_build.json').read_text(encoding='utf8'))
    bp=u.load_asset(report['asset']);director=spawn(bp.generated_class(),'BossLab_EncounterDirector')
    for k,v in [('Fighters',fighters),('Meshes',meshes),('Swords',swords),('HomePositions',homes),('TargetActor',targetactor),('CameraActor',cam)]:director.set_editor_property(k,v)
    gm=u.load_asset(BASE+'/Blueprints/BP_BossLabGameMode')
    if not gm:
        factory=u.BlueprintFactory();factory.set_editor_property('parent_class',u.GameModeBase)
        gm=u.AssetToolsHelpers.get_asset_tools().create_asset('BP_BossLabGameMode',BASE+'/Blueprints',u.Blueprint,factory)
    u.BlueprintEditorLibrary.compile_blueprint(gm);cdo=u.get_default_object(gm.generated_class());cdo.set_editor_property('default_pawn_class',None);u.EditorAssetLibrary.save_loaded_asset(gm)
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();world.get_world_settings().set_editor_property('default_game_mode',gm.generated_class())
    u.EditorLevelLibrary.set_level_viewport_camera_info(cam.get_actor_location(),cam.get_actor_rotation())
    level.save_current_level()
    (OUT/'scene_build.json').write_text(json.dumps({'map':target,'director':director.get_path_name(),'actors':len(AS.get_all_level_actors()),'fighters':8,'player_character':None,'placeholder_animations':'existing project mannequin content','sword_animations':None},ensure_ascii=False,indent=2),encoding='utf8')
    print('BOSS_SCENE_SAVED',target)

try:main()
except Exception:
    (OUT/'scene_error.txt').write_text(traceback.format_exc(),encoding='utf8');raise
