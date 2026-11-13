"""Editor-time generator only. Produced assets execute ordinary Blueprint bytecode."""
import unreal as u
L=u.BlueprintEditorLibrary
M='/Script/Engine.KismetMathLibrary.'
K='/Script/Engine.KismetSystemLibrary.'
A='/Script/Engine.KismetArrayLibrary.'

def typ(t):
    if isinstance(t,str) and t.endswith('[]'):return L.get_array_type(typ(t[:-2]))
    if t in ('float','double','int','bool','string','name'):return L.get_basic_type_by_name('real' if t in ('float','double') else t)
    if t in ('vector','rotator','color','transform'):
        return L.get_struct_type(u.load_object(None,{'vector':'/Script/CoreUObject.Vector','rotator':'/Script/CoreUObject.Rotator','color':'/Script/CoreUObject.LinearColor','transform':'/Script/CoreUObject.Transform'}[t]))
    return L.get_object_reference_type(t)

def link(a,b):
    if not a.try_create_connection(b):raise RuntimeError('Connect failed '+str(a.get_pin_name())+' => '+str(b.get_pin_name()))

def val(pin,v):
    if hasattr(v,'get_pin_name'):link(v,pin)
    else:
        s='true' if v is True else 'false' if v is False else str(v)
        if not pin.set_pin_value(s):raise RuntimeError('Literal failed '+str(pin.get_pin_name())+'='+s)

class Graph:
    def __init__(self,bp,name='EventGraph',inputs=None,output=None,pure=False,existing=False):
        self.bp=bp;self.name=name;self.local=set();self.inputs={};self.counter=0;self.x=0;self.y=0
        self.e=(u.BlueprintGraphEditor.get_graph_editor_by_name(bp,name) if existing or name=='EventGraph'
                else u.BlueprintGraphEditor.create_and_edit_function_graph(bp,name))
        for k,t in (inputs or {}).items():self.inputs[k]=self.e.add_graph_input_parameter(k,typ(t))
        self.return_node=self.e.add_graph_output_parameter('Result',typ(output)) if output else None
        if pure:self.e.set_is_pure_function(True)
        self.tail=self.e.find_graph_entry_pin() if name!='EventGraph' else None
    def place(self,n):
        self.counter+=1;n.set_node_pos(u.IntPoint(self.x+(self.counter%8)*290,self.y+(self.counter//8)*210));return n
    def c(self,path,/,**kwargs):
        if path==M+'Power':path=M+'MultiplyMultiply_FloatFloat'
        n=self.e.add_call_function_node(path)
        if not n:raise RuntimeError('No function '+path)
        self.place(n)
        # connect typed pins before setting wildcard literals
        for k,v in sorted(kwargs.items(),key=lambda kv:not hasattr(kv[1],'get_pin_name')):val(n.find_input_pin(k),v)
        return n
    def p(self,path,/,**kwargs):return self.c(path,**kwargs).find_result_pin()
    def do(self,path,/,**kwargs):
        n=self.c(path,**kwargs);link(self.tail,n.find_execute_pin());self.tail=n.find_then_pin();return n
    def fn(self,name,**kwargs):return self.do(self.bp.generated_class().get_path_name()+':'+name,**kwargs)
    def pure(self,name,**kwargs):return self.p(self.bp.generated_class().get_path_name()+':'+name,**kwargs)
    def get(self,name):
        if name in self.inputs:return self.inputs[name]
        n=self.e.add_get_local_variable_node(name) if name in self.local else self.e.add_get_member_variable_node(name)
        return self.place(n).find_result_pin()
    def set(self,name,value):
        n=self.place(self.e.add_set_local_variable_node(name) if name in self.local else self.e.add_set_member_variable_node(name))
        val(n.find_input_pin(name),value);link(self.tail,n.find_execute_pin());self.tail=n.find_then_pin();return n
    def declare(self,name,t,default=''):
        assert self.e.add_local_variable(name,typ(t),str(default)),name;self.local.add(name)
    def arr(self,name,index):return self.c(A+'Array_Get',TargetArray=self.get(name),Index=index).find_output_pin('Item')
    def put(self,name,index,value):return self.do(A+'Array_Set',TargetArray=self.get(name),Index=index,Item=value,bSizeToFit=True)
    def append(self,name,value):return self.do(A+'Array_Add',TargetArray=self.get(name),NewItem=value)
    def clear(self,name):self.do(A+'Array_Clear',TargetArray=self.get(name))
    def length(self,name):return self.p(A+'Array_Length',TargetArray=self.get(name))
    def lit(self,v,t=None):
        t=t or ('bool' if isinstance(v,bool) else 'int' if isinstance(v,int) else 'string' if isinstance(v,str) else 'double')
        return self.p(K+{'bool':'MakeLiteralBool','int':'MakeLiteralInt','string':'MakeLiteralString','float':'MakeLiteralFloat','double':'MakeLiteralDouble'}[t],Value=v)
    def op(self,name,a,b=None):
        kwargs={'A':a if hasattr(a,'get_pin_name') else self.lit(a)}
        if b is not None:kwargs['B']=b if hasattr(b,'get_pin_name') else self.lit(b)
        return self.p(M+name,**kwargs)
    def add(self,a,b):return self.op('Add_DoubleDouble',a,b)
    def sub(self,a,b):return self.op('Subtract_DoubleDouble',a,b)
    def mul(self,a,b):return self.op('Multiply_DoubleDouble',a,b)
    def div(self,a,b):return self.op('Divide_DoubleDouble',a,b)
    def eq(self,a,b):return self.op('EqualEqual_IntInt',a,b)
    def lt(self,a,b):return self.op('Less_DoubleDouble',a,b)
    def le(self,a,b):return self.op('LessEqual_DoubleDouble',a,b)
    def gt(self,a,b):return self.op('Greater_DoubleDouble',a,b)
    def ge(self,a,b):return self.op('GreaterEqual_DoubleDouble',a,b)
    def both(self,a,b):return self.op('BooleanAND',a,b)
    def either(self,a,b):return self.op('BooleanOR',a,b)
    def not_(self,a):return self.p(M+'Not_PreBool',A=a)
    def clamp(self,v,lo,hi):return self.p(M+'FClamp',Value=v,Min=lo,Max=hi)
    def min(self,a,b):return self.p(M+'FMin',A=a,B=b)
    def max(self,a,b):return self.p(M+'FMax',A=a,B=b)
    def rand(self):return self.p(M+'RandomFloat')
    def randint(self,lo,hi):return self.p(M+'RandomIntegerInRange',Min=lo,Max=hi)
    def select(self,condition,a,b):
        t='SelectFloat'
        return self.p(M+t,A=a,B=b,bPickA=condition)
    def if_(self,cond,yes,no=None):
        n=self.place(self.e.add_branch_node());val(n.find_condition_pin(),cond);link(self.tail,n.find_execute_pin())
        self.tail=n.find_then_pin();yes();yt=self.tail
        self.tail=n.find_else_pin()
        if no:no()
        nt=self.tail
        # converge into an impure no-op function; shared execute input permits fan-in
        merge=self.c(K+'PrintString',InString='',bPrintToScreen=False,bPrintToLog=False,Duration=0)
        if yt:link(yt,merge.find_execute_pin())
        if nt:link(nt,merge.find_execute_pin())
        self.tail=merge.find_then_pin()
    def loop(self,last,body,first=0):
        n=self.place(self.e.add_macro_node('/Engine/EditorBlueprintResources/StandardMacros.StandardMacros:ForLoop'))
        val(n.find_input_pin('FirstIndex'),first);val(n.find_input_pin('LastIndex'),last)
        link(self.tail,n.find_execute_pin());self.tail=n.find_output_pin('LoopBody');body(n.find_output_pin('Index'));self.tail=n.find_output_pin('Completed')
    def return_(self,value=None):
        n=self.return_node or self.place(self.e.add_return_node())
        if value is not None:val(n.find_input_pin('Result'),value)
        if self.tail:link(self.tail,n.find_execute_pin())
        self.tail=None
    def event(self,name):
        n=self.e.find_event_node(name)
        if not n:n=L.add_event_override(self.bp,name,u.IntPoint(self.x,self.y))
        n.set_node_pos(u.IntPoint(self.x,self.y));self.tail=n.find_then_pin();return n

def compile_bp(bp):
    ok=L.compile_blueprint(bp)
    if not ok:
        errs=[]
        for gr in L.list_graphs(bp):
            e=u.BlueprintGraphEditor.get_graph_editor(gr)
            errs.extend([(str(gr.get_name()),n.get_node_title(),str(n.get_editor_property('error_msg'))) for n in e.list_nodes_with_errors()])
        raise RuntimeError('Blueprint compile failed '+str(errs)[:12000])
    return ok

def variable(bp,name,t,default='',category='BossLab|Runtime',editable=False):
    e=u.BlueprintGraphEditor.get_graph_editor_by_name(bp,'EventGraph')
    assert (e.add_member_variable(name,typ(t),str(default)) if e else L.add_member_variable(bp,name,typ(t))),name
    L.set_blueprint_variable_category(bp,name,category)
    L.set_blueprint_variable_instance_editable(bp,name,editable)
