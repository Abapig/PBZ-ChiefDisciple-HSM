import sys
from pathlib import Path
import unreal as u
p=Path(u.Paths.project_dir()).resolve();sys.path.insert(0,str(p/'Tools/BossLab'))
from bp_dsl import *
bp=L.create_blueprint_asset_with_parent('/Game/BossLab/Diagnostics/BP_DSL_Test',u.Actor)
variable(bp,'Values','double[]');variable(bp,'Value','double',0)
g=Graph(bp,'Check',{'Index':'int'},'double');g.declare('Weight','double',0)
g.set('Weight',g.add(g.arr('Values',g.get('Index')),2.0))
g.if_(g.gt(g.get('Weight'),0.0),lambda:g.set('Value',g.mul(g.get('Weight'),3.0)))
g.return_(g.get('Value'))
compile_bp(bp)
c=u.get_default_object(bp.generated_class());c.set_editor_property('Values',[1.,4.]);print('DSL_RESULT',c.call_method('Check',(1,)))
u.EditorAssetLibrary.save_loaded_asset(bp)
