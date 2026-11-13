"""Single-canvas HFSM specification and viewer. No Unreal asset mutations."""
from pathlib import Path
import csv
import html
import json
import math
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'Step2' / 'Engineering'))
from catalog import MOVES, ALIASES, DISABLED, EVENT_WEIGHTS

NODES, EDGES, GROUPS = {}, [], {}
COLORS = {'phase':'#e9bd75','logic':'#66c8b5','move':'#83bddb','defense':'#94c789',
          'normal':'#a9b5c6','blue':'#65bfff','red':'#f18b83','black':'#c8a0ed',
          'service':'#d7ad77','terminal':'#ed879b','data':'#69c8b6'}


def group(key, title, subtitle, cols=4):
    GROUPS[key] = dict(id=key,title=title,subtitle=subtitle,cols=cols,nodes=[])


def node(key,title,body='',kind='logic',action=False,detail='',params=None,owner='Coordinator'):
    assert key not in NODES, key
    g = next(reversed(GROUPS))
    if action and owner=='Coordinator':owner='ActorInstance'
    NODES[key] = dict(id=key,title=title,body=body,kind=kind,group=g,action=action,
                      detail=detail or body,params=params or {},owner=owner,assets=[],rules=[])
    GROUPS[g]['nodes'].append(key)
    return key


def edge(a,b,label,guard=None,kind='flow',priority=50,actions=''):
    EDGES.append(dict(id=f'T{len(EDGES)+1:04}',source=a,target=b,label=label,
                      guard=guard or label,kind=kind,priority=priority,actions=actions))


def chain(ids,labels):
    for a,b,l in zip(ids,ids[1:],labels): edge(a,b,l)


def build_supervision():
    group('phase','01 · 战斗生命周期 / 四阶段','父状态作用域：Encounter；换阶段只前进；终局一次提交')
    node('B_ENTRY','战斗入口','玩家进入战斗区域；新 BattleID',kind='phase')
    node('B_INIT','初始化本场','P=0；冻结学习；角色/令牌初始化',params={'InitialMasterHP':3000,'Phase2MasterHP':4000,'RedHP':1800})
    node('B_M1','M1 · 七星剑阵','大师兄＋6弟子；无黑光',kind='phase')
    node('B_OPENER','固定开场 / M1-06','别名=M1-04；仅尝试一次',kind='phase')
    node('B_M2','M2 · 丝线大师兄','4000新生命池；继承本场压力',kind='phase')
    node('B_ENTER_RED','红衣加入 / 锁存','HP≤50%；只触发一次',kind='phase',action=True,owner='Red')
    node('B_M3','M3 · 双 Boss','继承M2＋红衣＋联合招',kind='phase')
    node('B_M4','M4 · 大师兄狂暴','红衣先死；保留HP/Qi；加六刀',kind='phase')
    node('B_SUICIDE','红衣殉情','停止战斗伤害；演出最多2s',kind='terminal',action=True,owner='Red',params={'SuicideDuration':2})
    node('B_BOTH','双 Boss 同批死亡','不狂暴；不重复殉情',kind='terminal')
    node('B_RESOLVE','结算胜负','玩家同批死亡优先判失败',kind='terminal')
    node('B_WIN','战斗胜利','锁 BattleResolved；提交一次学习',kind='terminal')
    node('B_LOSE','玩家死亡 / 战斗失败','锁 BattleResolved；提交一次学习',kind='terminal')
    node('B_ABORT','退出 / 读档 / 调试中断','清理动作；丢弃本场学习',kind='terminal')
    node('B_END','终局封存','禁止治疗、召唤、攻击与重复结算',kind='terminal')
    chain(['B_ENTRY','B_INIT','B_M1','B_OPENER'],['新场次','初始化完成','OpenerConsumed=false'])
    edge('B_OPENER','S_FORCED','开场意图=M1-04',actions='OpenerConsumed=true；中断后不重播')
    edge('B_OPENER','S_IDLE','人员/角色条件不满足','已消耗开场一次机会且不能合法启动')
    edge('B_M1','E_EPOCH','大师兄HP≤0',priority=10,actions='NextPhase=M2；撤销弟子；建立4000HP新池')
    edge('E_EPOCH','B_M2','NextPhase=M2')
    edge('B_M2','B_ENTER_RED','HP≤50% 且 !RedEntered',priority=15,actions='RedEntered=true；NextPhase=M3')
    edge('B_ENTER_RED','E_EPOCH','加入已锁存','不加血、不追加无敌；致死跨阈值亦触发',actions='NextPhase=M3')
    edge('E_EPOCH','B_M3','NextPhase=M3')
    edge('B_M3','E_EPOCH','红衣HP≤0 且 大师兄HP>0',priority=12,actions='NextPhase=M4')
    edge('E_EPOCH','B_M4','NextPhase=M4')
    edge('B_M3','B_SUICIDE','大师兄HP≤0 且 红衣HP>0',priority=11)
    edge('B_M3','B_BOTH','双方HP≤0（同批）',priority=10)
    edge('B_M4','B_RESOLVE','大师兄HP≤0',priority=10)
    edge('B_SUICIDE','B_RESOLVE','演出完成或逻辑2s','有效动作ID且动画完成 OR 战斗逻辑计时≥2s',actions='红衣HP=0')
    edge('B_BOTH','B_RESOLVE','同批伤害结算完毕')
    edge('B_RESOLVE','B_WIN','PlayerHP>0 且 !BattleResolved',priority=30)
    edge('B_RESOLVE','B_LOSE','PlayerHP≤0 且 !BattleResolved',priority=5)
    for k in ('B_WIN','B_LOSE'):
        edge(k,'L_COMMIT','有效完整战斗',kind='data')
        edge(k,'B_END','一次结算锁已置位')
    edge('B_ABORT','L_DISCARD','Abort不学习',kind='data')
    edge('B_ABORT','B_END','资源清理完成')
    for k in ('B_M2','B_M3','B_M4'): edge(k,'S_IDLE','进入本阶段常规调度')
    edge('B_INIT','L_FREEZE','本场只读历史快照',kind='data')
    edge('B_INIT','P_RESET','本场压力初始化',kind='data')
    edge('B_ENTRY','L_LOAD','开战读取历史证据',kind='data')
    edge('B_INIT','E_CLOCK','启动唯一战斗逻辑时钟',kind='event')

    group('events','02 · 帧结算 / 全局抢占','并行监督器；数值越小优先级越高；事件边≠互斥角色状态')
    node('E_CLOCK','战斗逻辑时钟','Tick；暂停/纯过场不推进')
    node('E_PAUSE','暂停 / 纯过场冻结','压力、冷却、破防、动作时钟一起停')
    node('E_COLLECT','收集本帧伤害批次','AttackID + Beat + Target 去重')
    node('E_VALID','验证事件身份','BattleID / Epoch / ActionID / BeatID')
    node('E_DROP','丢弃旧/重复回调','无伤害、无学习、无状态跳转')
    node('E_DAMAGE','原子结算伤害','按帧首存活快照扣HP/Qi/冲击')
    node('E_DEATH','死亡 / 阶段仲裁','同批双亡；玩家死亡优先结果',kind='terminal')
    node('E_EPOCH','阶段纪元变更','Epoch++；清未来预约/令牌/意图',detail='不清压力与本场样本；清历史/年龄；继承技能CD保留；回调必须匹配新Epoch。',kind='phase')
    node('E_RESOURCE','破防 / 坠地仲裁','死亡之后处理资源；两维独立')
    node('E_OUTPUT','投递已结算结果','单拍最坏结果；己方攻击另计',kind='data')
    node('E_CALLBACK','推进动作回调','有效ActionID；单拍仅推进一次')
    node('E_GLOBAL','全体活动动作 / 监督入口','每个活动节点继承G1/G2/G3规则',detail='G1死亡/换阶段最高优先；G2强制中断次之；G3锁超时/计划漂移进入安全恢复。非动作数据节点不继承动作中断。')
    node('E_CANCEL','中止原动作','清未执行段；释放锁；CD不退款',kind='terminal')
    node('E_TIMEOUT','安全恢复 / 超时','计划漂移>0.1s 或租期已到',kind='terminal',params={'TimingDriftTolerance':.1,'LeaseSlack':1})
    edge('E_CLOCK','E_PAUSE','Paused || CinematicOnly')
    edge('E_PAUSE','E_CLOCK','恢复战斗逻辑时钟')
    edge('E_CLOCK','E_COLLECT','非暂停Tick')
    chain(['E_COLLECT','E_VALID','E_DAMAGE','E_DEATH'],['批次关闭','事件身份有效且未结算','HP/Qi/冲击已提交'])
    edge('E_VALID','E_DROP','身份过期或重复',priority=0)
    edge('E_DROP','E_CLOCK','等待下一有效事件')
    edge('E_DEATH','B_LOSE','玩家HP≤0且尚未结算',priority=5)
    for k in ('B_M1','B_M2','B_M3','B_M4'): edge('E_DEATH',k,f'按当前阶段={k[2:]}判条件',kind='event',priority=10)
    edge('E_DEATH','E_RESOURCE','非终局；无待执行阶段清理',priority=20)
    edge('E_RESOURCE','Q_ASSESS','处理角色资源条件',kind='event')
    edge('E_RESOURCE','E_OUTPUT','资源仲裁后')
    edge('E_OUTPUT','P_DECAY','本场操作结果',kind='data')
    edge('E_OUTPUT','L_ELIGIBLE','招式应对样本',kind='data')
    edge('E_OUTPUT','E_CALLBACK','事件投递完成')
    edge('E_CALLBACK','E_CLOCK','本帧推进结束')
    edge('E_GLOBAL','E_DEATH','G1：死亡 / 阶段阈值',priority=5,kind='event')
    edge('E_GLOBAL','E_CANCEL','G2：有效强制中断',priority=20,kind='event')
    edge('E_GLOBAL','E_TIMEOUT','G3：租期/时序失效',priority=25,kind='event')
    edge('E_CANCEL','F_BREAK','被打断者属于当前阵法','以冻结参阵名单判定，非参阵脱阵者不触发',priority=20)
    edge('E_CANCEL','Q_ASSESS','非阵法个体中断',priority=21)
    edge('E_TIMEOUT','S_ROLLBACK','撤销尚未执行的伤害')
    edge('E_CLOCK','B_ABORT','退出/读档/调试终止',priority=0,kind='event')

    group('pressure','03 · 单场实时动态压力','并行数据状态；只读本场已结算操作；P ∈ [−100,100]')
    node('P_RESET','清零本场压力','P=0；清事件去重和2s预算',kind='data')
    node('P_DECAY','先按逻辑时间衰减','P ← P × 2^(−Δt/12)',kind='data',params={'PressureHalfLife':12})
    node('P_DEDUP','事件归并 / 去重','同拍只取最终最坏结果',kind='data')
    node('P_WEIGHT','映射操作增量','拼刀−12；精闪−8；闪−5；命中−1',kind='data',detail='格挡+2；己方落空+3；吃招+30；玩家破防+40；抓取+45。抓>破防>命中>格挡>拼刀>精闪>闪；玩家攻击独立事件。乱按/无效闪避不产生分值。')
    node('P_POS','正向滚动预算','2s内正增量≤60',kind='data',params={'PressureWindow':2,'PositiveBudget':60})
    node('P_NEG','负向滚动预算','2s内负变化绝对值≤30',kind='data',params={'NegativeBudget':30})
    node('P_CLAMP','应用增量 / 截断','P=clamp(P+δ,−100,100)',kind='data')
    node('P_READY','本场压力输出','x=P/100；不直接改历史学习',kind='data')
    edge('P_RESET','P_READY','初始化完成')
    chain(['P_DECAY','P_DEDUP','P_WEIGHT'],['衰减完成','新有效事件'])
    edge('P_DEDUP','P_READY','重复/无操作事件：只衰减')
    edge('P_WEIGHT','P_POS','w>0')
    edge('P_WEIGHT','P_NEG','w<0')
    for k in ('P_POS','P_NEG'): edge(k,'P_CLAMP','δ=剩余预算内允许变化')
    edge('P_WEIGHT','P_READY','w=0')
    edge('P_CLAMP','P_READY','更新事件预算')
    edge('E_CLOCK','P_DECAY','非暂停Tick：无操作也按时间衰减',kind='data')
    edge('S_FILTER','P_DECAY','选择前刷新到当前逻辑时刻',kind='data')
    edge('P_READY','S_WEIGHT','实时P参与权重',kind='data')
    edge('P_READY','S_OFFENSE','实时P参与进攻门',kind='data')

    group('learning','04 · 跨场学习 / 冻结快照','并行数据状态；本场只收集；胜利/失败后原子提交')
    node('L_LOAD','读取已完成战斗证据','版本迁移；规范招式ID；新招先验',kind='data')
    node('L_FREEZE','本场冻结S/F快照','本场样本不改变当前L',kind='data')
    node('L_MULT','计算各招学习倍率','r=(2+S)/(4+n)；c=n/(n+8)',kind='data',detail='L=exp[1.2c(1−2r)]；n=S+F。无样本L=1；应对差提高权重，应对好降低但不删除。')
    node('L_ELIGIBLE','样本资格判定','可见有效威胁；实际执行；去重',kind='data')
    node('L_ROOT','根招实例评分','有效拍均值；格挡0.65；失败0',kind='data',detail='拼刀/有效闪避=1；玩家成功打断整套根样本=1。行政取消、未执行、无威胁不采样。联合共同窗口只计一个根。')
    node('L_BRANCH','条件分支评分','/blue；/length/n 独立键',kind='data')
    node('L_PENDING','本场样本缓冲','每根动作一个根样本；等待终局',kind='data')
    node('L_COMMIT','完整战斗提交门','胜/负且BattleID未提交',kind='data')
    node('L_LIMIT','衰减旧证据 / 限本场','旧×0.9；每招本场最多等效6份',kind='data')
    node('L_CAP','压缩总证据','S+F>40按比例缩到40',kind='data')
    node('L_SAVE','原子保存一次','临时写入→替换；失败可重试同ID',kind='data')
    node('L_DISCARD','丢弃本场缓冲','Abort或无资格样本不污染历史',kind='data')
    chain(['L_LOAD','L_FREEZE','L_MULT'],['存档有效/先验','复制不可变快照'])
    edge('L_MULT','S_WEIGHT','冻结L_i参与权重',kind='data')
    edge('L_ELIGIBLE','L_ROOT','根实例完成或玩家主动打断')
    edge('L_ELIGIBLE','L_BRANCH','有效追加段/完整指定前缀',kind='data')
    edge('L_ELIGIBLE','L_DISCARD','行政取消/无威胁/未执行/重复')
    for k in ('L_ROOT','L_BRANCH'): edge(k,'L_PENDING','SampleID未记录')
    edge('L_PENDING','L_COMMIT','等待胜/负事件','非终局期间仅留缓冲，不触发此边')
    chain(['L_COMMIT','L_LIMIT','L_CAP','L_SAVE'],['本BattleID首次提交','S/F按公式更新','数据版本有效'])
    edge('L_COMMIT','L_DISCARD','Abort/已提交：不重复写')
    edge('L_SAVE','L_LOAD','下一场开始时读取',kind='data')
    edge('L_DISCARD','L_LOAD','下一场开始时重新读取；不写本场',kind='data')


def build_scheduler():
    group('selector','05 · 中央选择 / 角色与攻击预约','空闲才抽根招；每次决策最多一次随机选择；原子占用并可回滚')
    node('S_IDLE','空闲 / 等待决策','无不可取消动作；重入间隔0.2s')
    node('S_PRIORITY','确定性优先级','开场→召唤→吸血→输血→支援→常规')
    node('S_FORCED','确定性动作意图','满足服务/开场时该意图概率1')
    node('S_FILTER','合法候选筛选','阶段/角色/距离/视线/CD/人员',detail='禁止相同根三连、危险根三连；近喷d≤450、远喷450<d≤1800；阵法≥2弟子，M1-09需6；独立剑气与副通道单独入口。')
    node('S_WEIGHT','逐招计算权重','w=b·exp(kx)·L·D·R·A·C',detail='D=.25+.75exp(−.5((d−μ)/σ)^2)；R=.7^近4次次数×立即重复.25；A=1+.04min(年龄,10)；C=低玩家Qi危险1.15×可见收势短前摇1.2。参数按33招表。')
    node('S_NORMALIZE','探索 / 封顶 / 归一化','12%均匀探索；N≥3封顶45%',detail='N=2上限65%；N=1概率1；N=0不除零。water-filling最多N轮。无效/NaN配置拒绝加载。')
    node('S_OFFENSE','是否本次进攻','O=clamp(.70+.18x,.52,.88)',detail='有合法招且距离上次进攻开始≥3s时O=1；无合法招O=0。该条件不抢占当前动作。')
    node('S_DRAW','根招只抽一次','Pr(i)=O·q_i；记录随机数/原因')
    node('S_PLAN','编译有限动作计划','前缀长度/演员/参阵者此处预选',detail='C/E长度用exp(.4x(n−2.5))×L_length，探索12%、长度封顶55%。Actor按等待与距离权重；冻结名单。存完整预警和分支时刻并集；最大7拍。')
    node('S_RESERVE','原子申请角色与日历','普通间隔≥.35；彩色间隔≥.65',detail='锁与预约同一事务。预警前允许延迟0..1s、步长.05最多21次。预订所有观察/蓝刺分支并集；任何失败整体回滚。')
    node('S_COMMIT','启动承诺 / 消耗CD','更新共享历史；CD开始；不退款')
    node('S_EXEC','按MoveID/Intent分发','角色可行动；身份/计划仍有效')
    node('S_COMPLETE','动作收束 / 释放','清剩余预约；提交本场样本')
    node('S_ROLLBACK','申请失败 / 安全回滚','不持半套锁；取消未执行段')
    node('S_WAIT','短等待 / 安全重试','至少0.5s；不能同帧重抽',action=True)
    chain(['S_IDLE','S_PRIORITY'],['到决策时刻且无终局'])
    edge('S_PRIORITY','S_FORCED','有合法高优先意图')
    edge('S_PRIORITY','S_FILTER','无确定性服务/支援')
    edge('S_FORCED','S_PLAN','服务/开场意图已选')
    chain(['S_FILTER','S_WEIGHT','S_NORMALIZE','S_OFFENSE','S_DRAW','S_PLAN','S_RESERVE','S_COMMIT','S_EXEC'],
          ['N>0','所有权重有限且>0','q之和=1','u<O','记录唯一MoveID','有限计划完整','原子申请成功','实际启动；消耗CD'])
    edge('S_FILTER','M_CHOICE','N=0：走位或等待')
    edge('S_WEIGHT','S_ROLLBACK','参数非法/非有限值')
    edge('S_OFFENSE','M_CHOICE','u≥O')
    edge('S_RESERVE','S_ROLLBACK','角色冲突/21次预约均失败')
    edge('S_ROLLBACK','S_WAIT','确认全部回滚')
    edge('S_WAIT','S_IDLE','逻辑等待≥0.5s')
    edge('S_COMPLETE','L_ELIGIBLE','动作实例已结束',kind='data')
    edge('S_COMPLETE','S_IDLE','释放完成＋0.2s重入间隔')
    edge('S_PRIORITY','H_PRIORITY','M1生命服务条件可检查',kind='event')
    edge('S_PRIORITY','U_HEAL_GATE','M3输血条件可检查',kind='event')
    edge('S_PRIORITY','D_SUPPORT','有效支援请求待消费',kind='event')

    group('movement','06 · 非攻击移动 / 对峙','角色共用行为模板；参数按角色实例；移动不清攻击历史')
    node('M_CHOICE','移动分布选择','追赶/后撤/侧移/对峙',detail='追赶d>650权3否则.5；后撤1+2I(Qi<30%)；侧移2；对峙2；归一化上限65%。')
    node('M_FACE','面向 / 转向','仅合法动作窗口；挥出后限制追踪',kind='move',action=True,params={'TurnRate':'config','TrackingCutoff':'config'})
    node('M_STAND','对峙 / 等待出手','面向玩家；无出手权者等待',kind='move',action=True,params={'StandoffDuration':.6})
    node('M_CHASE','追击 / 追赶','导航到招式理想距离；0.6–1.2s',kind='move',action=True)
    node('M_STRAFE','侧移 / 避免重叠','可导航方向；0.6s；不额外抢攻',kind='move',action=True)
    node('M_RETREAT','后撤 / 拉开距离','0.6–1s；低Qi偏好；不回气',kind='move',action=True)
    node('M_PATH_FAIL','导航失败等待','1.2s改善<50cm；禁止穿墙瞬移',kind='move',action=True,params={'PathRetryDelay':1})
    edge('M_CHOICE','M_FACE','行为选择前先确定目标朝向')
    for k,label in [('M_STAND','选中对峙'),('M_CHASE','选中追赶'),('M_STRAFE','选中侧移'),('M_RETREAT','选中后撤')]: edge('M_FACE',k,label)
    for k in ('M_STAND','M_CHASE','M_STRAFE','M_RETREAT'): edge(k,'S_IDLE','到期/达到目标且角色仍可行动')
    for k in ('M_CHASE','M_STRAFE','M_RETREAT'): edge(k,'M_PATH_FAIL','路径不可达或进展不足')
    edge('M_PATH_FAIL','M_FACE','逻辑1s后可重新导航')
    edge('M_FACE','V_SENSE','观察到新威胁',kind='event')

    group('defense','07 · 感知 / 格挡 / 闪避 / 普通受击','所有角色各实例；ThreatID只反应一次；无Boss精准反击技能')
    node('V_SENSE','感知已展示威胁','不读未来输入；登记ThreatID')
    node('V_REACT','反应延迟','0.18s后重查威胁与可取消窗',kind='defense',action=True)
    node('V_GUARD_GATE','格挡合法性','正面±60°；可格挡；Qi>0；非破防')
    node('V_GUARD','主动格挡 / 招架','普通攻击不扣HP；扣Qi；动作0.25s',kind='defense',action=True)
    node('V_GUARD_END','格挡结束','不可用格挡覆盖破防或死亡',kind='defense',action=True)
    node('V_DODGE_GATE','位移闪避选择','无合法优先格挡；CD到；路径可达',detail='p=clamp(.2+.35(1−Qi比)−.1x,.1,.6)；只对同ThreatID抽一次。冷却2.5s。')
    node('V_DODGE','闪避 / 无无敌帧','0.55s移动250cm；仍可被命中',kind='defense',action=True,params={'DodgeDuration':.55,'DodgeDistance':250,'DodgeCooldown':2.5})
    node('V_NO_REACT','保持原合法动作','不能取消/未选中闪避/路径失败')
    node('V_HIT','普通命中 / 抗打断检查','先扣HP/Qi/冲击；死亡已优先',detail='轻/重/蓄力强度1/2/3；普通准备/收势抗0，普通承诺段1，彩色有效段2；强度≥阈值则中断。破防一律可中断。')
    node('V_STAGGER','轻 / 重受击硬直','0.35 / 0.6s；连轻击不刷新末时刻',kind='defense',action=True)
    chain(['V_SENSE','V_REACT','V_GUARD_GATE'],['ThreatID新且动作可反应','反应延迟到'])
    edge('V_SENSE','V_NO_REACT','重复威胁或不可取消')
    edge('V_GUARD_GATE','V_GUARD','全部格挡守卫满足')
    edge('V_GUARD_GATE','V_DODGE_GATE','不能合法优先格挡')
    edge('V_GUARD','Q_ASSESS','结算格挡Qi损失',kind='event')
    edge('V_GUARD','V_GUARD_END','0.25s结束且未破防')
    edge('V_GUARD_END','S_IDLE','恢复可行动')
    edge('V_DODGE_GATE','V_DODGE','u<p 且 CD/位移合法')
    edge('V_DODGE_GATE','V_NO_REACT','其余情况')
    edge('V_DODGE','S_IDLE','0.55s结束且未受强制中断')
    edge('V_NO_REACT','E_CALLBACK','保留原动作上下文',kind='event')
    edge('V_HIT','V_STAGGER','强度≥当前抗打断且非更高优先表现')
    edge('V_HIT','E_CALLBACK','未达到中断阈值：仅受伤',kind='event')
    edge('V_HIT','F_BREAK','参阵者实际被中断',kind='event',priority=20)
    edge('V_STAGGER','Q_ASSESS','硬直到期；不清破防标志')

    group('resource','08 · 杀气破防 / 冲击坠地（正交）','Qi与Ground各自计时；表现优先坠地；只有破防后恢复Qi')
    node('Q_ASSESS','资源 / 表现仲裁','死亡先处理；Ground优先于Broken')
    node('Q_NORMAL','未破防资源状态','Qi不自然恢复；受到有效攻击才扣')
    node('Q_BREAK_START','破防进入','Qi=0；锁BreakStart；禁格挡',kind='defense',action=True)
    node('Q_REGEN','破防回气（并行）','M=4s / R=3.5s / 弟子=3s',kind='data',detail='Qi=QiMax*clamp((t−BreakStart)/duration,0,1)。破防中命中扣HP，不扣恢复中的Qi、不重置起点。未满仍保持Broken。')
    node('Q_BREAK_STUN','破防起始硬直','逻辑0.6s；演出结束≠破防解除',kind='defense',action=True,params={'BreakInitialStunDuration':.6})
    node('Q_HANG','悬吊破防静止','仅大师兄M2+；等待Qi回满',kind='defense',action=True,owner='Master')
    node('Q_BROKEN_FREE','地面角色破防持续','红衣/弟子/M1大师兄；不能格挡',kind='defense',action=True)
    node('Q_IMPULSE','2s冲击窗口累加','轻10 / 重25 / 蓄力50；阈值100',kind='data')
    node('Q_GROUND','大师兄坠地','2.8s；保留独立破防计时',kind='defense',action=True,owner='Master')
    node('Q_REHANG','重新悬吊','坠地结束；按Broken选择表现',kind='defense',action=True,owner='Master')
    node('Q_LOCK','抗再次坠地窗口','重悬后3s；仍承伤/杀气损失',kind='data')
    node('Q_READY','资源恢复可行动','Qi回满才解除Broken；不加HP')
    edge('Q_ASSESS','Q_GROUND','悬吊大师兄且 GroundUntil>t',priority=25)
    edge('Q_ASSESS','Q_BREAK_START','Qi≤0 且 !Broken',priority=30)
    edge('Q_ASSESS','Q_HANG','Broken && 悬吊 && !Ground',priority=35)
    edge('Q_ASSESS','Q_BROKEN_FREE','Broken && 非悬吊 && !Ground',priority=35)
    edge('Q_ASSESS','Q_NORMAL','非Broken且非Ground',priority=40)
    edge('Q_NORMAL','S_IDLE','没有尚在执行的原动作')
    edge('Q_NORMAL','E_CALLBACK','原动作仍有效则继续',kind='event')
    edge('Q_BREAK_START','Q_REGEN','初始化一次BreakStart',kind='data')
    edge('Q_BREAK_START','Q_BREAK_STUN','进入破防表现')
    edge('Q_BREAK_START','D_DETACH_GATE','弟子破防：申请唯一脱阵槽',kind='event')
    edge('Q_BREAK_STUN','Q_ASSESS','起始硬直到期')
    edge('Q_REGEN','Q_READY','t≥BreakEnd；Qi=QiMax',actions='Broken=false；不刷新GroundUntil')
    edge('Q_HANG','Q_READY','Qi=QiMax 且 !Ground')
    edge('Q_BROKEN_FREE','Q_READY','Qi=QiMax 且 !Ground')
    edge('Q_READY','D_REJOIN','该弟子占脱阵槽',kind='event')
    edge('Q_READY','Q_ASSESS','回气完成；仍须复查Ground')
    edge('E_RESOURCE','Q_IMPULSE','悬吊形态实际受攻',kind='data')
    edge('Q_IMPULSE','Q_GROUND','2s冲击≥100 且 t≥KnockLock',actions='GroundUntil=t+2.8；KnockLock=GroundUntil+3；清窗口')
    edge('Q_IMPULSE','Q_ASSESS','未到阈值或处于坠地保护窗口')
    edge('Q_GROUND','Q_REHANG','t≥GroundUntil')
    edge('Q_GROUND','Q_REGEN','若Broken仍并行回气',kind='data')
    edge('Q_REHANG','Q_LOCK','启动剩余抗坠地计时',kind='data')
    edge('Q_REHANG','Q_HANG','Broken且Qi未满')
    edge('Q_REHANG','S_IDLE','未破防或Qi已满')
    edge('Q_LOCK','Q_IMPULSE','t≥KnockLock 后可再次累计',kind='data')


def build_m1_coordination():
    group('formation','09 · M1 归阵 / 参阵名单 / 阵型','仅冻结名单中的参与者能中断本阵；至少2弟子＋大师兄')
    node('F_ENTRY','剑阵执行入口','读取计划已冻结参阵者；不换人')
    node('F_COUNT','参阵人数复核','合格弟子≥2；M1-09需6')
    node('F_DISTANCE','归阵方式选择','参与者两两最大距离≤700cm？')
    node('F_SPIN','近距回旋跳归阵','0.6s；不造成伤害；无无敌帧',kind='move',action=True,owner='Formation')
    node('F_RISE','远距丝线上跃','离开屏幕表现；仍无无敌帧',kind='move',action=True,owner='Formation')
    node('F_LAND','丝线落地集结','远归阵总预算1.3s；落点需有效',kind='move',action=True,owner='Formation')
    node('F_DISPATCH','归阵完成 / 分发阵法','保持主令牌与全员角色锁')
    node('F_BREAK','全阵中断','参与者被强制打断：撤销全部未来拍',kind='terminal',action=True,owner='Formation')
    node('F_RECOVER','全阵中断恢复','0.8s；各自死亡/破防/坠地优先',kind='defense',action=True,owner='Formation')
    node('F_FAIL','归阵失败','落点非法/人数变化；不反复瞬移')
    node('F_SHAPE2','2弟子 · 双人短阶','借力1次；逻辑阵型配置接口',kind='move',action=True,owner='Formation')
    node('F_SHAPE3','3弟子 · 三角阶','借力2次；逻辑阵型配置接口',kind='move',action=True,owner='Formation')
    node('F_SHAPE4','4弟子 · 双排折线阶','借力3次；逻辑阵型配置接口',kind='move',action=True,owner='Formation')
    node('F_SHAPE5','5弟子 · 扇形阶','借力4次；逻辑阵型配置接口',kind='move',action=True,owner='Formation')
    node('F_SHAPE6','6弟子 · 完整阶','借力5次；逻辑阵型配置接口',kind='move',action=True,owner='Formation')
    chain(['F_ENTRY','F_COUNT','F_DISTANCE'],['冻结名单身份有效','当前仍满足人数'])
    edge('F_COUNT','F_FAIL','人数不足/参与者失效')
    edge('F_DISTANCE','F_SPIN','最大两两距离≤700cm')
    edge('F_DISTANCE','F_RISE','最大两两距离>700cm')
    edge('F_RISE','F_LAND','上跃计时完成；使用配置分配总1.3s')
    for k in ('F_SPIN','F_LAND'):
        edge(k,'F_DISPATCH','归阵计时完成且落点有效')
        edge(k,'F_FAIL','落点无效/无法导航')
    edge('F_BREAK','F_RECOVER','原子撤销全阵攻击与预约')
    edge('F_RECOVER','S_COMPLETE','0.8s且个体恢复条件允许')
    edge('F_RECOVER','Q_ASSESS','个体仍破防/坠地',kind='event')
    edge('F_FAIL','S_ROLLBACK','回滚后至少等待0.5s')

    group('support','10 · M1 脱阵 / 支援 / 独立剑气','主近战一人或预定义双人组；独立Q不占密度令牌但占大师兄自身')
    node('D_DETACH_GATE','破防弟子 / 脱阵槽','至多一名脱阵；其余仍可破防')
    node('D_DETACHED','唯一脱阵弟子','可移动受击；破防时不能攻击/格挡',kind='defense',action=True,owner='Disciple')
    node('D_SECOND_BREAK','第二弟子破防','不取第二槽；若参阵则全阵中断',kind='defense',action=True,owner='Disciple')
    node('D_HIT_COUNT','脱阵目标被持续进攻','3s内有效命中≥3次；支援CD4s')
    node('D_SUPPORT','支援请求 / 排队','等待主令牌；请求最多存活2s')
    node('D_PICK_HELPER','选择支援者','最近可行动同伴；不抢不可取消段')
    node('D_SUPPORT_POOL','普通支援招式池','仅M1-01近战；同权重再归一化')
    node('D_REJOIN','释放脱阵槽 / 再入队','Qi回满；下一次阵法才可参阵',kind='move',action=True,owner='Disciple')
    node('D_WAVE_GATE','大师兄独立剑气门','每次弟子主攻击最多尝试一次',detail='大师兄自身空闲且不在阵法/服务；Q冷却4s；O_wave=clamp(.18+.10x,.08,.28)。不占近战密度令牌；仍走全局日历。')
    node('D_WAVE_INTENT','独立剑气意图','MoveID=M1-01-Q；不增加近战人数')
    edge('D_DETACH_GATE','D_DETACHED','槽空或本弟子已占槽',actions='DetachedActor=当前弟子；参与阵法先取消')
    edge('D_DETACH_GATE','D_SECOND_BREAK','槽被另一弟子占用')
    edge('D_SECOND_BREAK','F_BREAK','该弟子仍在当前冻结参阵名单')
    edge('D_SECOND_BREAK','Q_BROKEN_FREE','未参阵：仅自身破防')
    edge('D_DETACHED','D_HIT_COUNT','收到该弟子的有效受击事件',kind='event')
    edge('D_DETACHED','M_CHOICE','初始硬直结束后可脱阵移动','DetachedActor=本弟子 && InitialBreakStunEnded && HP>0；仍Broken时只允许移动，不获得进攻/格挡权限',kind='event')
    edge('D_HIT_COUNT','D_SUPPORT','命中计数≥3 && 支援CD已到')
    edge('D_HIT_COUNT','D_DETACHED','未达触发条件')
    edge('D_SUPPORT','D_PICK_HELPER','主令牌可用且请求未超2s')
    edge('D_SUPPORT','S_FILTER','无请求/请求超时')
    edge('D_PICK_HELPER','D_SUPPORT_POOL','存在合法可行动同伴')
    edge('D_PICK_HELPER','S_WAIT','暂时没有合法同伴')
    edge('D_SUPPORT_POOL','S_PLAN','按普通招权重抽一次；Intent=Support')
    edge('D_DETACHED','D_REJOIN','Qi已回满且未死亡')
    edge('D_REJOIN','S_IDLE','DetachedActor清空')
    edge('S_EXEC','D_WAVE_GATE','M1弟子主攻击已开始',kind='event')
    edge('D_WAVE_GATE','D_WAVE_INTENT','全部守卫满足且 u<O_wave')
    edge('D_WAVE_INTENT','S_PLAN','独立Q计划申请角色/日历')
    edge('D_WAVE_GATE','E_CALLBACK','未抽中或条件不满足：继续主动作',kind='event')

    group('health','11 · M1 召唤 / 吸血服务','支付与收益一次原子提交；死亡优先；冷却启动即消耗')
    node('H_PRIORITY','M1生命服务仲裁','先召唤，再吸血，再支援/普通')
    node('H_SUMMON_INTENT','召唤意图','活弟子<3 && HP>MaxHP/3 && CD到',kind='service')
    node('H_SUMMON_W','召唤前摇','1.0s；开始消耗CD18s',kind='service',action=True,owner='Master')
    node('H_SUMMON_CHECK','召唤提交前复查','仍活着、M1、人数不足、费用足')
    node('H_SUMMON_PAY','扣费并补至3人','总费用MaxHP/3；新血总≤费用80%',kind='service',detail='每新弟子HP=min(350,.8*Cost/Missing)。恰1/3不能召唤。无次数上限。召唤后3s禁止吸血；资源总量每次至少降低费用20%。')
    node('H_SUMMON_R','召唤收势','0.6s；成员重新登记',kind='service',action=True,owner='Master')
    node('H_DRAIN_INTENT','吸血意图 / 锁定目标','HP<75%；挑当前绝对HP最高弟子',kind='service')
    node('H_DRAIN_W','吸血前摇','0.9s；开始消耗CD12s',kind='service',action=True,owner='Master')
    node('H_DRAIN_CHECK','吸血提交前复查','目标身份未失效；不临时换目标')
    node('H_DRAIN_PAY','等量生命转移','min(.15MaxHP,缺血,目标HP−1)',kind='service')
    node('H_DRAIN_R','吸血收势','0.5s；不把弟子吸死',kind='service',action=True,owner='Master')
    edge('H_PRIORITY','H_SUMMON_INTENT','召唤条件满足',priority=40)
    edge('H_PRIORITY','H_DRAIN_INTENT','召唤不可行且吸血条件满足',priority=41)
    edge('H_PRIORITY','D_SUPPORT','两种服务均不可行',priority=42)
    for intent in ('H_SUMMON_INTENT','H_DRAIN_INTENT'): edge(intent,'S_PLAN','确定性意图进入统一预约')
    edge('S_EXEC','H_SUMMON_W','Intent=Summon')
    edge('S_EXEC','H_DRAIN_W','Intent=Drain')
    chain(['H_SUMMON_W','H_SUMMON_CHECK','H_SUMMON_PAY','H_SUMMON_R','S_COMPLETE'],['1s到期且动作有效','复查全部通过','扣费/生成同一事务','0.6s收势到期'])
    chain(['H_DRAIN_W','H_DRAIN_CHECK','H_DRAIN_PAY','H_DRAIN_R','S_COMPLETE'],['0.9s到期且动作有效','复查全部通过','扣弟子与加大师兄同一事务','0.5s收势到期'])
    for k in ('H_SUMMON_CHECK','H_DRAIN_CHECK'): edge(k,'S_ROLLBACK','目标/阶段/存活/费用条件失效；CD不退')


def move_kind(atom):
    return {'B':'blue','R':'red','K':'black'}.get(atom.split(':')[0],'normal') if ':' in atom else 'normal'


ATOM_NAMES={'L':'左横劈','R':'右横劈','U':'上挑','D':'下劈','T':'前刺','J':'跳劈','K':'鞭腿','Q':'普通剑气 / 投射',
            'B:T':'蓝光突刺','B:J':'蓝光跳斩','B:D':'蓝光斩击','R:T':'红光突刺','R:Q':'红光远程',
            'SPRAY':'无光扇形丝线喷射','R:SPRAY':'红光近距丝线喷射','R:BACK':'红光后翻斩',
            'K:BIND':'黑光束线突袭','K:D':'黑光快速斩击','B:DUET':'两人联合蓝光','R:M':'大师兄红光','R:R':'红衣错拍红光'}
ROOTS = {}


def attack_node(key,title,body,move,atom=None):
    actor={'G':'MasterOrDisciple','M':'Master','Q':'Master','R':'Red','D':'MasterAndRed'}[move.owner]
    n=node(key,title,body,kind=move_kind(atom) if atom else 'normal',action=True,owner=actor,
           params={'MoveID':move.id,'Windup':move.windup,'Recovery':move.recovery,'Cooldown':move.cooldown,
                   'BaseWeight':move.base,'PressureSlope':move.pressure,'RangeMax':move.reach,
                   'IdealRange':move.ideal,'RangeWidth':move.width,'AllowedPhases':list(move.phases),
                   'RequiredDisciples':move.disciples,'DangerousCandidate':move.danger,
                   'SharedCooldownKey':'M2-05' if move.id.startswith('M2-05') else move.id})
    NODES[n]['move']=move.id
    if atom: NODES[n]['atom']=atom
    return n


def begin_move(key):
    m=MOVES[key]; base=key.replace('-','_')
    entry=attack_node(base+'_W',f'{key} · {m.name}',f'前摇 {m.windup:g}s；CD {m.cooldown:g}s；模板计划已冻结',m)
    ROOTS[key]=entry
    recovery=attack_node(base+'_R',f'{key} · 收势',f'{m.recovery:g}s；最后有效窗结束后计时；不再派生',m)
    edge(recovery,'S_COMPLETE','逻辑收势到期 / 匹配动画完成','动画资源可空；至少满足配置有效时间，且ActionID/Epoch匹配')
    if m.disciples: edge('F_DISPATCH',entry,f'MoveID={key}；归阵已完成')
    else: edge('S_EXEC',entry,f'MoveID={key}；预约已承诺')
    return m,base,entry,recovery


def fixed_move(key,atoms=None,branch=False):
    m,b,w,r=begin_move(key); atoms=atoms or list(m.atoms)
    last=w
    for i,atom in enumerate(atoms):
        beat=attack_node(f'{b}_B{i+1}',f'{i+1}/{len(atoms)} · {ATOM_NAMES[atom]}','有效窗0.18s；一次BeatID；结算后推进',m,atom)
        if atom=='R:M':NODES[beat]['owner']='Master'
        if atom=='R:R':NODES[beat]['owner']='Red'
        edge(last,beat,'首拍预约时刻到' if i==0 else '下拍预定时刻到且身份有效')
        if i==len(atoms)-1:
            edge(beat,r,'末拍有效窗结束；不得接普通段')
        else:
            gap=attack_node(f'{b}_G{i+1}',f'{i+1}→{i+2} · 段间过渡','连接动作0.18s包含在拍间隔内；普通间隔.50/彩色.85',m)
            if branch and i==1:
                branch_nodes(b,m,beat,gap,r)
            else: edge(beat,gap,'本拍有效窗结束且已结算；无中断')
            last=gap
    return b


def branch_nodes(b,m,source,continuation,recovery):
    check=node(b+'_STOP_GATE',f'{m.id} · 第二普通拍变招','本次连段只检查一次',detail='p_stop=clamp(.12−.06x+.18I(上拍被成功拼刀/闪避),.06,.36)。仅用已结算上一拍；读取当时P与本场冻结L。')
    observegate=node(b+'_OBS_GATE','不停招时是否观察','p_observe=clamp(.12+.08x,.04,.20)')
    observe=attack_node(b+'_OBS','一次观察 / 节奏停顿','0.35s；恢复已选剩余序列；不重新选根招',m)
    edge(source,check,'普通拍计数=2 && !BranchVisited',actions='BranchVisited=true')
    edge(check,recovery,'u<p_stop：提前结束')
    edge(check,observegate,'u≥p_stop：继续')
    edge(observegate,observe,'u<p_observe')
    edge(observegate,continuation,'u≥p_observe')
    edge(observe,continuation,'0.35s观察结束；仍可行动')
    edge('P_READY',check,'节点时刻实时P',kind='data')


def build_m1_moves():
    group('m1basic','12 · M1 普通拼刀 / 独立剑气','每招独立状态；普通之间有连接动作；招架见07格挡区')
    for key,m in MOVES.items():
        if m.phases==(1,) and not m.disciples:
            fixed_move(key)
    group('m1forms','13 · M1 剑阵招式 / 动态人数','M1-02/03必蓝；04=06必红；07最后弟子蓝；09无光三拍')
    edge('S_EXEC','F_ENTRY','所选M1阵法：先执行共同归阵')
    fixed_move('M1-02')
    fixed_move('M1-04')
    m,b,w,r=begin_move('M1-03')
    step=attack_node(b+'_STEP','大师兄踏步借力','每次0.22s；StepIndex递增；目标次数=N−1',m)
    blue=attack_node(b+'_BLUE','最终蓝光借势突刺','只在借力次数完成后发动；蓝光预警不压缩',m,'B:T')
    for n in range(2,7):
        edge(w,f'F_SHAPE{n}',f'前摇完成且冻结参与弟子数={n}')
        edge(f'F_SHAPE{n}',step,f'阵型就绪；StepTarget={n-1}',actions='StepIndex=0')
    edge(step,step,'逻辑0.22s且 StepIndex+1<StepTarget','每次状态完成先StepIndex++；仍未达目标才重入',actions='StepIndex++')
    edge(step,blue,'已完成StepTarget；蓝拍预约到期',actions='最后一次StepIndex++；不再借力')
    edge(blue,r,'蓝光有效窗结束')
    m,b,w,r=begin_move('M1-07')
    mq=attack_node(b+'_MASTER_Q','第1拍 · 大师兄剑气','普通剑气；大师兄不斩击',m,'Q')
    dg=attack_node(b+'_GAP','轮攻交接 / 段间过渡','按冻结名单推进；弟子Index单调递增',m)
    dn=attack_node(b+'_DISCIPLE','中间弟子普通斩','非最后弟子；每人最多一次',m,'D')
    db=attack_node(b+'_LAST','最后弟子蓝光斩','N名弟子时总N+1拍；大师兄无额外斩击',m,'B:D')
    NODES[dn]['owner']='CurrentFormationDisciple'
    NODES[db]['owner']='LastFormationDisciple'
    chain([w,mq,dg],['前摇完成／首拍预约到','剑气有效窗结束；Index=1'])
    edge(dg,dn,'Index<N；普通拍预约到')
    edge(dn,dg,'有效窗结束；Index++')
    edge(dg,db,'Index=N；末段蓝拍预约到')
    edge(db,r,'蓝光有效窗结束')
    m,b,w,r=begin_move('M1-09')
    names=['第一对弟子跳劈','第二对弟子紧跟跳劈','最后两弟子＋大师兄剑气']
    prev=w
    for i,title in enumerate(names):
        hit=attack_node(b+f'_PAIR{i+1}',f'第{i+1}拍 · {title}','同组共同应对窗口；无光；满6弟子限定',m,'J' if i<2 else 'Q')
        NODES[hit]['owner']='DisciplePair'+str(i+1) if i<2 else 'MasterAndDisciplePair3'
        edge(prev,hit,'对应拍预约到期；名单仍有效')
        if i<2:
            gap=attack_node(b+f'_GAP{i+1}','无光阵法交接','0.18s连接；总普通拍间隔0.50s',m)
            edge(hit,gap,'本拍有效窗结束')
            prev=gap
        else: edge(hit,r,'第三拍结束')


def pooled_move(key):
    m,b,w,r=begin_move(key)
    is_c=key.endswith('C')
    gate=node(b+'_ROUTE',f'{key} · 有界序列路由','读取计划n∈1..4；只推进索引，不重抽长度',detail='长度在S_PLAN按压力和冻结长度经验预选。首原子L/R/U/D/T等概率；后续按显式边1/3。C前缀后接L/R/蓝刺；E前缀结束即收势。')
    settle=attack_node(b+'_SETTLE','普通拍结算 / 连接过渡','有效窗结束；OrdinaryCount++；对应游标++；0.18s连接',m)
    cont=node(b+'_NEXT','继续已冻结计划','前缀最多4；C后缀3；无递归续套')
    edge(w,gate,'前摇完成；初始化一次计数',actions='PrefixIndex=0；SuffixIndex=0；OrdinaryCount=0；BranchVisited=false')
    edges={'L':('R','U','T'),'R':('L','D','T'),'U':('D','R','T'),'D':('U','L','T'),'T':('L','R','D')}
    for a in ('L','R','U','D','T'):
        beat=attack_node(b+'_P_'+a,f'前缀池 · {ATOM_NAMES[a]}','普通拍；按已预约的拍时刻执行',m,a)
        pred=','.join(p for p,targets in edges.items() if a in targets)
        edge(gate,beat,f'前缀未满；合法抽中{a}',f'PrefixIndex<n 且 [(首次u落入1/5区间) 或 LastNormal∈{{{pred}}}且合法边1/3抽中{a}]')
        edge(beat,settle,'有效窗完成',actions=f'LastNormal={a}；Origin=Prefix')
    if is_c:
        for idx,a in enumerate(('L','R')):
            beat=attack_node(b+'_S_'+a,f'二系列后缀 · {ATOM_NAMES[a]}','前缀结束后按固定L→R推进',m,a)
            edge(gate,beat,f'PrefixIndex=n && SuffixIndex={idx}')
            edge(beat,settle,'有效窗完成',actions='Origin=Suffix')
        blue=attack_node(b+'_BLUE','末拍 · 蓝光突刺','C完整路径最多7拍；蓝后禁止继续',m,'B:T')
        edge(gate,blue,'PrefixIndex=n && SuffixIndex=2；蓝拍时刻到')
        edge(blue,r,'蓝拍有效窗结束')
        branch_nodes(b,m,settle,cont,r)
        edge(settle,cont,'OrdinaryCount≠2 或 BranchVisited')
    else: edge(settle,cont,'本拍结算完成')
    edge(cont,gate,'仍有计划普通/蓝拍；等待预定下一拍')
    if not is_c: edge(gate,r,'PrefixIndex=n：E无蓝结束')


def build_m2_moves():
    group('m2fixed','14 · M2 / M3 / M4 继承剑招 A/B/D/F','A/B/D第2普通拍可停招/观察；F为独立蓝刺；蓝必最后且为突刺')
    for key in ('M2-01-A','M2-01-B','M2-01-D'): fixed_move(key,branch=True)
    fixed_move('M2-01-F')
    group('m2pool','15 · M2 可变前缀 C / 无蓝串 E','有限出招池显式展开；所有循环都由计数器限制并含有效时间')
    pooled_move('M2-01-C')
    pooled_move('M2-01-E')
    group('m2thread','16 · M2 高空丝线 / 拉远红光 / 喷射','起手按距离锁定颜色；远喷可追加；近红禁止追加')
    fixed_move('M2-03')
    m,b,w,r=begin_move('M2-04')
    retreat=attack_node(b+'_RETREAT','拉远准备 / 后撤','最多1.2s；不能瞬移；保留完整红光预警',m)
    red=attack_node(b+'_RED','拉远后的红光远程','红预警≥0.65s；一次有效窗',m,'R:Q')
    EDGES[:] = [e for e in EDGES if not (e['source']=='S_EXEC' and e['target']==w)]
    ROOTS['M2-04']=retreat
    edge('S_EXEC',retreat,'MoveID=M2-04；先拉远准备')
    edge(retreat,w,'到达合法位置；开始完整红光前摇')
    edge(w,red,'红光前摇到期且红拍预约到期')
    edge(retreat,r,'1.2s不可达：结束准备，不产生红拍')
    edge(red,r,'红拍有效窗结束')
    fixed_move('M2-05-N')
    m,b,w,r=begin_move('M2-05-F')
    spray=attack_node(b+'_SPRAY','远距离无光扇形丝线','起手d>450；预警后不改成近红',m,'SPRAY')
    gate=node(b+'_BRANCH','喷射后追加判断','读取刚结算结果；分支只判一次',detail='p=clamp(sigmoid(−.15+.65x+h+ln L_blue),.15,.8)；h命中.45/格挡.1/拼刀−.55/普通闪−.35/精闪−.45/落空−.35。')
    blue=attack_node(b+'_BLUE','追加蓝光快速突刺','复查距离≤1100、视线、可行动；先前已预约',m,'B:T')
    chain([w,spray,gate],['无光首拍预约到期','喷射拍已结算'])
    edge(gate,blue,'u<p_blue 且追加守卫全部满足',
         'u<p_blue && MasterHP>0 && MasterCanAct && DistanceToPlayer≤1100cm && HasLOS && Phase∈{M2,M3,M4} && ActionID/Epoch有效 && 蓝拍时间已在本动作预约并集中')
    edge(gate,r,'未选追加或距离/视线/角色失效',
         'u≥p_blue OR MasterHP≤0 OR !MasterCanAct OR DistanceToPlayer>1100cm OR !HasLOS OR 阶段/动作身份失效；死亡/阶段抢占优先于本地收势；未执行蓝拍不采样')
    edge(blue,r,'追加蓝拍结束；禁止再派生')
    edge('P_READY',gate,'分支时刻实时P',kind='data')
    edge('L_MULT',gate,'本场冻结 L_/blue',kind='data')


def build_red_and_duet():
    group('red','17 · 红衣独立招式（M3）','普通/红/蓝/黑分别着色；具体节奏沿用第二步复刻参数')
    for key in ('R-01','R-02','R-03','R-04','R-05','R-07','R-08'): fixed_move(key)
    group('duet','18 · 联合技 / 副通道 / 输血 / M4','联合技锁两人；副通道只允许红衣普通招；输血不复活')
    fixed_move('M3-01')
    fixed_move('M3-02')
    fixed_move('M4-01')
    node('U_SECONDARY_GATE','红衣副通道机会','大师兄非联合主招中；最多尝试一次',detail='O_secondary=clamp(.10+.15x,.02,.25)。红衣空闲；只R-01/R-02；主/副共享CD/历史。联合招时关闭。')
    node('U_SECONDARY_PICK','红衣普通副招选择','R-01/R-02合法者按同公式归一化')
    edge('S_EXEC','U_SECONDARY_GATE','M3大师兄非联合主攻击已启动',kind='event')
    edge('U_SECONDARY_GATE','U_SECONDARY_PICK','角色合法且u<O_secondary')
    edge('U_SECONDARY_GATE','E_CALLBACK','未抽中/红衣不可行动：主动作继续',kind='event')
    edge('U_SECONDARY_PICK','S_PLAN','副通道意图进入同一预约器')
    node('U_HEAL_GATE','红衣输血条件','M3双方活；M_HP<40%；R_HP>25%；CD到',kind='service')
    node('U_HEAL_INTENT','输血意图 / 预约双人','CD20s；占两人角色锁',kind='service')
    node('U_HEAL_W','红衣输血前摇','1.2s；开始即耗CD；可强制中断',kind='service',action=True,owner='MasterAndRed')
    node('U_HEAL_CHECK','输血提交复查','先结算同帧死亡；死人不得治疗')
    node('U_HEAL_PAY','牺牲红衣HP治疗大师兄','min(300,大师兄缺血,红衣HP−1)',kind='service')
    node('U_HEAL_R','输血收势','0.6s；双方总血守恒',kind='service',action=True,owner='MasterAndRed')
    edge('U_HEAL_GATE','U_HEAL_INTENT','全部条件成立')
    edge('U_HEAL_GATE','S_FILTER','任何条件不满足')
    edge('U_HEAL_INTENT','S_PLAN','服务意图；不进入招式随机池')
    edge('S_EXEC','U_HEAL_W','Intent=RedHeal')
    chain(['U_HEAL_W','U_HEAL_CHECK','U_HEAL_PAY','U_HEAL_R','S_COMPLETE'],['1.2s前摇完成','双方仍活且全部条件合法','扣血/回血同一原子事务','0.6s收势完成'])
    edge('U_HEAL_CHECK','S_ROLLBACK','死亡/换阶段/目标失效：取消不退CD')


def add_contracts():
    group('interfaces','20 · 参数 / 资源接口 / 空绑定','资源名称已预留；引用均为null；逻辑计时不依赖动画文件')
    node('I_ACTORS','角色绑定接口','MasterActor / DiscipleActors[6] / RedActor',kind='data',detail='SoftObjectPtr/Actor引用全部null。仅约定接口 CanAct、CurrentHP、Qi、Distance、HasLOS、PerceivedThreat。')
    node('I_ANIM','动画资源接口','每个动作AN_<Owner>_<StateID> = null',kind='data',detail='动画未提供则使用配置逻辑计时器推进，不等待永远不会来的Montage回调；以后绑定时仍校验ActionID/Epoch与最短有效窗。')
    node('I_HIT','碰撞 / 特效 / 音频接口','每个有效拍HIT_/FX_/SFX_引用=null',kind='data',detail='需要调用ReportBeatOutcome才结算学习和压力。无碰撞资源时不伪造玩家成功/失败；逻辑演示可用明确标记的测试事件。')
    node('I_PARAMS','参数表 / 招式配置','保留第二步默认；公开命名字段',kind='data',detail='逐招b/k/距离μσ/最大距离/CD/前摇/收势；压力、学习、阶段、资源、调度常量全部独立命名。空资源不等于参数默认为0。')
    node('I_CALLBACK','逻辑计时 / 回调适配器','动画完成 OR LogicalDurationElapsed',kind='data',detail='ActionID/Epoch必须匹配；有效窗结束前不得提前推进；暂停冻结战斗时钟；缺动画用计时，不产生重复推进。')
    node('I_ALIASES','别名归并接口','M1-06→04；M2-02→01-F；R-06→04',kind='data',detail='别名指向同一根招、同一冷却与学习键；不是额外独立招式。开场M1-06只是M1-04的一次固定意图。')
    node('I_DISABLED','禁用 / 资料未确认项','M1-05 / M1-08 / M2-06 / R-09',kind='data',detail='不进入合法候选，不产生伤害与学习样本；大师兄黑光排除项保持禁用。')
    edge('I_ACTORS','S_FILTER','角色接口输入',kind='data')
    edge('I_PARAMS','S_WEIGHT','逐招参数输入',kind='data')
    edge('I_ANIM','I_CALLBACK','资源空则计时推进',kind='data')
    edge('I_CALLBACK','E_VALID','统一回调身份验证',kind='data')
    edge('I_HIT','E_COLLECT','真实/显式测试命中事件',kind='data')
    edge('I_PARAMS','I_ALIASES','读取规范ID映射',kind='data')
    edge('I_PARAMS','I_DISABLED','读取禁用集合',kind='data')
    edge('I_ALIASES','S_FILTER','归并后筛选/学习/共享CD',kind='data')
    edge('I_DISABLED','S_FILTER','禁用ID硬过滤',kind='data')
    edge('E_RESOURCE','V_HIT','存在普通HP命中且非死亡抢占',kind='event')
    for n in NODES.values():
        if 'move' not in n:
            for move_id,m in MOVES.items():
                if n['id'].startswith(move_id.replace('-','_')+'_'):
                    n['move']=move_id
                    if n['owner']=='Coordinator':n['owner']={'G':'MasterOrDisciple','M':'Master','Q':'Master','R':'Red','D':'MasterAndRed'}[m.owner]
                    break
        asset_owners={'MasterAndRed':['Master','Red'],
                      'MasterOrDisciple':['Master','Disciple'],
                      'Formation':['Master','FormationDisciple'],
                      'MasterAndDisciplePair3':['Master','Pair3DiscipleA','Pair3DiscipleB'],
                      'DisciplePair1':['Pair1DiscipleA','Pair1DiscipleB'],
                      'DisciplePair2':['Pair2DiscipleA','Pair2DiscipleB']}.get(n['owner'],[n['owner']])
        if n['action']:
            n['rules']=['G1'] if n['id'] in ('B_SUICIDE','F_RECOVER') else ['G1','G2','G3']
            for actor in asset_owners:n['assets'].append({'name':f"AN_{actor}_{n['id']}",'type':'AnimMontage/AnimSequence','target_role':actor,'binding':None})
        if 'atom' in n:
            for prefix,typ in [('HIT','HitVolumeDefinition'),('FX','NiagaraSystem'),('SFX','SoundBase')]:
                for actor in asset_owners:n['assets'].append({'name':f"{prefix}_{actor}_{n['id']}",'type':typ,'target_role':actor,'binding':None})
    # Explicit inherited event edges, not secretly omitted subgraph exits.
    for n in list(NODES.values()):
        if n['action'] and n['id'] not in ('B_SUICIDE','F_RECOVER'):
            edge(n['id'],'E_GLOBAL','G1/2/3：全局优先中断',
                 'Battle/Epoch有效作用域中发生死亡/阶段阈值，或有效强制中断，或锁超时/计划漂移；按G1→G2→G3优先处理',kind='global',priority=5)
    # Special terminal/recovery states remain interruptible only by higher priorities.
    edge('B_SUICIDE','B_LOSE','殉情演出期间玩家已死亡且未结算',kind='global',priority=5)
    edge('F_RECOVER','E_DEATH','恢复期间死亡/阶段阈值',kind='global',priority=5)


def build_actor_parents():
    group('actors','19 · 角色父状态 / 实例生命周期','父状态显式展开；公共行为为每名角色独立实例，不是共享一份运行状态')
    node('A_MASTER','大师兄 / 活动父状态','持有自己的HP/Qi/ActionState；绑定MasterActor',kind='phase')
    node('A_M_GROUND','大师兄 / M1地面战斗','公共行为＋M1普通招/阵法/服务',kind='phase')
    node('A_M_HANG','大师兄 / M2悬吊战斗','公共行为＋M2剑招池/丝线',kind='phase')
    node('A_M_DUO','大师兄 / M3双人战斗','继承M2＋联合技；可独立受控',kind='phase')
    node('A_M_RAGE','大师兄 / M4狂暴战斗','继承M2＋M4-01；没有黑光',kind='phase')
    node('A_M_DEAD','大师兄 / 最终死亡','注销攻击能力；交阶段总控结算',kind='terminal',action=True,owner='Master')
    node('A_RED_OUT','红衣 / 未入场','没有攻击、治疗、命中与学习资格',kind='phase')
    node('A_RED_ACTIVE','红衣 / M3活动父状态','自己的HP/Qi/ActionState；绑定RedActor',kind='phase')
    node('A_RED_DEAD','红衣 / 被击杀','注销角色锁；触发大师兄M4或双亡',kind='terminal',action=True,owner='Red')
    node('A_D_POOL','弟子 / 未生成或退场','6个稳定ActorID槽；资源引用可空',kind='phase')
    node('A_D_ACTIVE','弟子 / M1活动父状态 ×6','每人各自HP/Qi/动作；共享攻击密度令牌',kind='phase')
    node('A_D_DEAD','弟子 / 死亡','从存活/合格名单移除；若参阵则全阵取消',kind='terminal',action=True,owner='Disciple')
    node('A_COMMON','角色公共行为入口','每实例：移动/防御/受击/破防/招式执行',kind='phase',detail='Master、Red、Disciple[0..5]各自拥有CurrentActionState；这里的公共行为是模板定义，不是八人共用一份可变状态。中央协调器只管理共享令牌、日历、阶段、压力和学习。')
    node('A_FINISHER_GATE','被追击 / 处决事件校验','仅确认支持且收到实际有效事件')
    node('A_PURSUED','被追击表现','保留资源/死亡仲裁；完成后再评状态',kind='defense',action=True,params={'PursuedDuration':'interface'},owner='TargetActor')
    node('A_EXECUTED','被处决表现','仅已确认有效处决事件；不凭空扣死',kind='terminal',action=True,params={'ExecutionDuration':'interface'},owner='TargetActor')
    edge('B_INIT','A_MASTER','初始化大师兄实例',kind='event')
    edge('A_MASTER','A_M_GROUND','Phase=M1')
    edge('B_M2','A_M_HANG','阶段事件：建立悬吊父状态',kind='event')
    edge('B_M3','A_M_DUO','阶段事件：双人大师兄父状态',kind='event')
    edge('B_M4','A_M_RAGE','阶段事件：狂暴父状态',kind='event')
    for k in ('A_M_GROUND','A_M_HANG','A_M_DUO','A_M_RAGE','A_RED_ACTIVE','A_D_ACTIVE'):edge(k,'A_COMMON','角色已创建且当前存活',kind='event')
    edge('E_DEATH','A_M_DEAD','大师兄HP≤0且非M1换生命池',kind='event',priority=10)
    edge('A_M_DEAD','B_RESOLVE','终局由阶段规则判；M3先殉情则等待','当非M3殉情演出待完成；M3先走B_SUICIDE而非提前跳过',kind='event')
    edge('B_INIT','A_RED_OUT','红衣未入场',kind='event')
    edge('A_RED_OUT','A_RED_ACTIVE','RedEntered已锁存且HP>0')
    edge('B_ENTER_RED','A_RED_ACTIVE','生成/激活红衣实例',kind='event')
    edge('E_DEATH','A_RED_DEAD','红衣已入场且HP≤0',kind='event',priority=10)
    edge('A_RED_DEAD','B_M3','把同批红衣死亡交阶段判定',kind='event')
    edge('B_INIT','A_D_POOL','初始化六个弟子槽',kind='event')
    edge('A_D_POOL','A_D_ACTIVE','M1初始生成或合法召唤提交成功')
    edge('H_SUMMON_PAY','A_D_ACTIVE','本次新生弟子初始化HP/Qi/动作',kind='event')
    edge('E_DEATH','A_D_DEAD','当前弟子HP≤0',kind='event',priority=10)
    edge('A_D_DEAD','F_BREAK','该弟子是当前参阵者',kind='event',priority=20)
    edge('A_D_DEAD','A_D_POOL','注销实例；可等待后续付费召唤')
    edge('E_EPOCH','A_D_POOL','离开M1：注销所有弟子与旧回调',kind='event')
    edge('A_COMMON','S_IDLE','可行动且无现行动作')
    edge('A_COMMON','Q_ASSESS','有破防/坠地/受击表现待仲裁',kind='event')
    edge('A_COMMON','V_SENSE','收到已展示威胁',kind='event')
    edge('E_VALID','A_FINISHER_GATE','有效外部追击/处决事件',kind='event')
    edge('A_FINISHER_GATE','A_PURSUED','支持追击且有效事件且逻辑时长>0','SupportsPursuit && ConfirmedPursuitEvent && PursuedDuration>0')
    edge('A_FINISHER_GATE','A_EXECUTED','支持处决且有效事件且逻辑时长>0','SupportsExecution && ConfirmedExecutionEvent && ExecutionDuration>0')
    edge('A_FINISHER_GATE','E_DROP','未确认支持/无事件/身份过期')
    edge('A_PURSUED','Q_ASSESS','有效演出完成或配置逻辑计时到')
    edge('A_EXECUTED','E_DEATH','实际处决伤害事件结算后；不伪造致死')


def validate_graph():
    assert set(ROOTS)==set(MOVES), (set(MOVES)-set(ROOTS))
    for e in EDGES:
        assert e['source'] in NODES and e['target'] in NODES, e
        assert e['guard'].strip(),e
    for i,e in enumerate(EDGES): e['id']=f'T{i+1:04}'
    assert len({e['id'] for e in EDGES})==len(EDGES)
    incoming={n:0 for n in NODES};outgoing={n:0 for n in NODES}
    for e in EDGES:
        incoming[e['target']]+=1;outgoing[e['source']]+=1
    no_in=[n for n in NODES if not incoming[n]]
    no_out=[n for n in NODES if not outgoing[n]]
    allowed_in={'B_ENTRY','L_LOAD','I_ACTORS','I_ANIM','I_HIT','I_PARAMS','V_HIT'}
    assert set(no_in)<=allowed_in,no_in
    assert set(no_out)<= {'B_END'},no_out
    for key,m in MOVES.items():
        members=[n for n in NODES.values() if n.get('move')==key]
        assert any(n['id']==ROOTS[key] for n in members)
        assert all(a['binding'] is None for n in members for a in n['assets'])
        if m.owner!='R': assert all(n.get('kind')!='black' for n in members)
    # Check all action states have a finite timer or declared global escape contract.
    assert all(n['rules'] for n in NODES.values() if n['action'])
    assert NODES['M1_07_LAST']['owner']=='LastFormationDisciple'
    assert NODES['M3_02_B1']['owner']=='Master' and NODES['M3_02_B2']['owner']=='Red'
    assert NODES['M4_01_B6']['atom']=='B:D'
    assert NODES['M2_05_F_BRANCH']['move']=='M2-05-F'
    resource_names=[a['name'] for n in NODES.values() for a in n['assets']]
    assert len(resource_names)==len(set(resource_names))
    assert not any(e['source'].startswith('M2_05_N') and e['target'].startswith('M2_05_F_BLUE') for e in EDGES)
    return {'nodes':len(NODES),'edges':len(EDGES),'groups':len(GROUPS),
            'moves_covered':len(ROOTS),'inherited_edges':sum(e['kind']=='global' for e in EDGES),
            'empty_resource_bindings':sum(len(n['assets']) for n in NODES.values()),
            'dangling_edges':0,'empty_guards':0,'missing_move_roots':0,
            'external_inputs':no_in,'terminal_nodes':no_out}


def wrap(text,limit=27):
    # Chinese glyphs approximately 1 em, ASCII about half em.
    lines=[];line='';size=0
    for char in str(text):
        width=.56 if ord(char)<256 else 1
        if char=='\n' or size+width>limit:
            lines.append(line);line='';size=0
            if char=='\n':continue
        line+=char;size+=width
    if line: lines.append(line)
    return lines or ['']


def layout():
    out={k:[] for k in NODES}
    for e in EDGES:out[e['source']].append(e)
    for n in NODES.values():
        if n.get('move'):
            m=MOVES[n['move']]
            n['hierarchy']='Encounter.Active / Phase['+','.join('M'+str(p) for p in m.phases)+'] / '+n['owner']+'.Alive / Attack['+m.id+'] / '+n['id']
        else:
            paths={'phase':'Encounter / Lifecycle','actors':'Encounter.Active / Phase / ActorInstance',
                   'selector':'Encounter.Active / Concurrent.Scheduler','events':'Encounter / Concurrent.FrameSupervisor',
                   'pressure':'Encounter.Active / Concurrent.RealTimePressure','learning':'Encounter / Concurrent.CrossBattleLearning',
                   'movement':'ActorInstance.Alive / Behavior.Locomotion','defense':'ActorInstance.Alive / Behavior.Defense',
                   'resource':'ActorInstance.Alive / Orthogonal.QiAndGround','formation':'Phase.M1 / FormationCoordinator',
                   'support':'Phase.M1 / SupportAndDetachedMembership','health':'Phase.M1 / HealthServices',
                   'duet':'Phase.M3 / DuetCoordinator','interfaces':'Configuration / UnboundInterfaces'}
            n['hierarchy']=paths.get(n['group'],'Encounter.Active / Action')+' / '+n['id']
        n['outgoing']=[e['id'] for e in out[n['id']]]
        n['incoming']=[e['id'] for e in EDGES if e['target']==n['id']]
        n['width']=358
        n['title_lines']=wrap(n['title'],19)
        n['body_lines']=wrap(n['body'],26)
        base=26+25*len(n['title_lines'])+19*len(n['body_lines'])+20
        ports=[]
        for e in out[n['id']]:
            if e['kind']=='global':continue
            lines=wrap(e['label'],26)
            ph=12+16*len(lines)
            ports.append(dict(id=e['id'],y=base+ph/2,top=base,lines=lines,height=ph))
            base+=ph
        n['ports']=ports
        n['height']=base+24+(18 if n['action'] else 0)
    gx=[70+2110*i for i in range(4)]
    gy=170
    groups=list(GROUPS.values())
    for i in range(0,len(groups),4):
        row=groups[i:i+4]
        for col,g in enumerate(row):
            g['x']=gx[col];g['y']=gy;g['width']=2020
            # Stable row order preserves each authored sequence's ordering.
            yy=gy+115
            ids=g['nodes']
            for j in range(0,len(ids),4):
                ns=[NODES[k] for k in ids[j:j+4]]
                for nc,n in enumerate(ns):n['x']=g['x']+54+480*nc;n['y']=yy
                yy+=max(n['height'] for n in ns)+92
            g['height']=yy-gy+10
        gy+=max(g['height'] for g in row)+120
    return 8500,gy+80


def svg_text(x,y,content,size=14,fill='#c1ccd7',cls='',weight='400'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" class="{cls}">{html.escape(str(content))}</text>'


def render_svg(width,height):
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" id="fsm" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Boss全量分层状态机单页图">',
       '<defs><pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#1e2834" stroke-width=".7"/></pattern><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L8 4L0 8Z" fill="context-stroke"/></marker></defs>',
       '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}.state{cursor:pointer}.wire{fill:none;marker-end:url(#arrow)}.state:hover .box{stroke:#fff;stroke-width:3}.state .portlabel{fill:#b9c6d4}.selected .box{stroke:#fff!important;stroke-width:4}.dim{opacity:.12!important}.wire.highlight{opacity:1!important;stroke:#fff!important;stroke-width:3!important}.group-name{letter-spacing:1px}.wire.hide-wire{display:none}.state .portlabel:hover{fill:#fff}</style>',
       f'<rect width="{width}" height="{height}" fill="#10151d"/><rect width="{width}" height="{height}" fill="url(#grid)"/>',
       svg_text(75,65,'大师兄 × 红衣女剑客 / 全量分层状态机 · 单页展开',40,'#f1d7a7',weight='700'),
       svg_text(78,110,'实线：状态转换　虚线青：并行数据　虚线金：事件路由　淡红：继承全局抢占　所有资源引用=null',21,'#aab8ca')]
    for g in GROUPS.values():
        s.append(f'<g class="region" data-group="{g["id"]}"><rect x="{g["x"]}" y="{g["y"]}" width="{g["width"]}" height="{g["height"]}" rx="18" fill="#141c27" fill-opacity=".88" stroke="#33495e" stroke-width="2"/>')
        s.append(svg_text(g['x']+32,g['y']+45,g['title'],26,'#e6c990','group-name','700'))
        s.append(svg_text(g['x']+32,g['y']+78,g['subtitle'],16,'#8fa6bc'))
        s.append('</g>')
    s.append('<g id="wires">')
    for e in EDGES:
        a,b=NODES[e['source']],NODES[e['target']]
        port=next((p for p in a['ports'] if p['id']==e['id']),None)
        sx=a['x']+a['width'];sy=a['y']+(port['y'] if port else a['height']-12)
        tx=b['x'];ty=b['y']+25
        if a==b:
            path=f'M {sx} {sy} C {sx+100} {sy+110}, {tx-85} {ty+150}, {tx} {ty}'
        else:
            bend=max(65,min(600,abs(tx-sx)*.38))
            path=f'M {sx} {sy} C {sx+bend} {sy}, {tx-bend} {ty}, {tx} {ty}'
        color={'flow':'#99aabc','data':'#4facaa','event':'#c5a16b','global':'#cc7186'}[e['kind']]
        opacity={'flow':.58,'data':.29,'event':.3,'global':.09}[e['kind']]
        dash='' if e['kind']=='flow' else ' stroke-dasharray="9 7"'
        tooltip=html.escape(e['id']+' · '+a['title']+' → '+b['title']+'\n'+e['guard']+'\n'+e['actions'])
        s.append(f'<path id="{e["id"]}" class="wire {e["kind"]}" d="{path}" stroke="{color}" stroke-width="1.7" opacity="{opacity}"{dash} data-source="{a["id"]}" data-target="{b["id"]}"><title>{tooltip}</title></path>')
    s.append('</g><g id="states">')
    for n in NODES.values():
        x,y,w,h=n['x'],n['y'],n['width'],n['height'];color=COLORS[n['kind']]
        tooltip=html.escape(n['title']+'\n'+n['detail'])
        s.append(f'<g id="{n["id"]}" class="state" data-group="{n["group"]}" transform="translate({x} {y})" tabindex="0"><title>{tooltip}</title><rect class="box" width="{w}" height="{h}" rx="9" fill="#202b39" stroke="{color}" stroke-width="1.6"/><path d="M9 0H{w-9}Q{w} 0 {w} 9V{29+25*len(n["title_lines"])}H0V9Q0 0 9 0" fill="{color}" fill-opacity=".18"/>')
        s.append(svg_text(13,18,n['id'],11,color))
        yy=41
        for line in n['title_lines']:
            s.append(svg_text(13,yy,line,18,'#f0f4f9',weight='600'));yy+=25
        yy+=9
        for line in n['body_lines']:
            s.append(svg_text(13,yy,line,13,'#a8bbcf'));yy+=19
        for p in n['ports']:
            s.append(f'<g class="port" data-edge="{p["id"]}"><line x1="8" y1="{p["top"]}" x2="{w-8}" y2="{p["top"]}" stroke="#354457"/><circle cx="{w}" cy="{p["y"]}" r="3.5" fill="{color}"/>')
            for li,line in enumerate(p['lines']):s.append(svg_text(15,p['top']+17+li*16,line,12,cls='portlabel'))
            s.append('</g>')
        if n['action']:s.append(svg_text(13,h-10,'AN=null  ·  继承全局出口：'+'/'.join(n['rules']),10,'#7d93ac'))
        s.append('</g>')
    s.append('</g></svg>')
    return '\n'.join(s)


def export_tables(audit):
    bindings={'actors':{'MasterActor':None,'DiscipleActors':[None]*6,'RedActor':None},
              'resources':[dict(state=n['id'],**a) for n in NODES.values() for a in n['assets']],
              'fallback':'LogicalDurationElapsed with valid BattleID/Epoch/ActionID; no fabricated combat outcomes'}
    params={'version':'hfsm-design-1.0','source':'Step2 approved reproduction defaults + explicit interface declarations',
            'moves':{k:dict(vars(v)) for k,v in MOVES.items()},'pressure_event_weights':EVENT_WEIGHTS,
            'globals':{'PressureHalfLife':12,'PressureWindow':2,'PressurePositiveCap':60,'PressureNegativeCap':30,
                       'PressureMin':-100,'PressureMax':100,'LearningPriorSuccess':2,'LearningPriorFailure':2,
                       'LearningConfidenceScale':8,'LearningStrength':1.2,'LearningDecay':.9,'EvidencePerBattleCap':6,
                       'EvidenceTotalCap':40,'ExploreMix':.12,'ProbabilityCapMany':.45,'ProbabilityCapTwo':.65,
                       'DecisionInterval':.2,'ForceOffenseAfter':3,'FallbackWait':.5,'CloseRegroupDistance':700,
                       'CloseRegroupTime':.6,'FarRegroupTime':1.3,'StepTime':.22,'NormalBeatGap':.5,
                       'ColoredBeatGap':.85,'HitWindow':.18,'ObserveTime':.35,'MaxComboBeats':7,
                       'CrossNormalGap':.35,'CrossColoredGap':.65,'MaxReservationDelay':1,'ReservationStep':.05,
                       'MasterQiMax':100,'RedQiMax':100,'DiscipleQiMax':100,'MasterBreakDuration':4,
                       'RedBreakDuration':3.5,'DiscipleBreakDuration':3,'GroundDuration':2.8,
                       'KnockImmunityAfterGround':3,'ImpactWindow':2,'ImpactThreshold':100,
                       'GuardHalfAngle':60,'ReactionTime':.18,'DodgeDuration':.55,'DodgeDistance':250,
                       'DodgeCooldown':2.5,'DodgeInvulnerability':False,'NaturalQiRegeneration':False,
                       'SummonCooldown':18,'DrainCooldown':12,'PostSummonDrainBlock':3,'SummonCostRatio':1/3,
                       'SummonedHPRatioBudget':.8,'DrainTriggerRatio':.75,'DrainMaxRatio':.15,
                       'RedEnterRatio':.5,'RedHealMasterRatio':.4,'RedHealSelfRatio':.25,'RedHealAmount':300,
                       'RedHealCooldown':20,'SupportHitWindow':3,'SupportHitCount':3,'SupportCooldown':4,
                       'SupportRequestTTL':2,'MaxDetachedDisciples':1,'BreakInitialStunDuration':.6,
                       'FarRegroupRiseDuration':.5,'FarRegroupLandDuration':.8,'DeathPresentationDuration':.6,
                       'OffenseBase':.70,'OffensePressureSlope':.18,'OffenseMin':.52,'OffenseMax':.88,
                       'StopBase':.12,'StopPressureSlope':-.06,'StopSuccessfulResponseBonus':.18,'StopMin':.06,'StopMax':.36,
                       'ObserveBase':.12,'ObservePressureSlope':.08,'ObserveMin':.04,'ObserveMax':.20,
                       'BlueFollowupLogitBase':-.15,'BlueFollowupPressureSlope':.65,'BlueFollowupMin':.15,'BlueFollowupMax':.8,
                       'BlueFollowupRange':1100,'BlueFollowupResultOffsets':{'hit':.45,'block':.1,'parry':-.55,'dodge':-.35,'perfect_dodge':-.45,'miss':-.35},
                       'PrefixLengthPressureSlope':.4,'PrefixLengthCenter':2.5,'LengthProbabilityCap':.55,
                       'RepeatWindow':4,'RepeatFactor':.7,'ImmediateRepeatFactor':.25,'WaitingAgeStep':.04,'WaitingAgeCap':10,
                       'LowPlayerQiThreshold':.25,'LowQiDangerMultiplier':1.15,'PunishWindowMultiplier':1.2,'ShortWindupThreshold':.7,
                       'WaveBase':.18,'WaveSlope':.1,'WaveMin':.08,'WaveMax':.28,
                       'SecondaryBase':.10,'SecondarySlope':.15,'SecondaryMin':.02,'SecondaryMax':.25},
            'unbound_tuning_interfaces':{'TurnRate':None,'TrackingCutoff':None,'MoveSpeedByActor':None,
                                         'AttackDamageByBeat':None,'HitShapeByBeat':None,
                                         'FormationOffsetsByCount':None,'NavigationProjectionExtent':None,
                                         'PursuedDuration':None,'ExecutionDuration':None},
            'optional_features':{'SupportsPursuit':False,'SupportsExecution':False}}
    for filename,obj in [('asset_bindings.json',bindings),('parameter_interfaces.json',params),('graph_audit.json',audit)]:
        (HERE/filename).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    with (HERE/'全部状态转换.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['id','source','target','label','guard','kind','priority','actions']);writer.writeheader();writer.writerows(EDGES)
    md=['# 全量状态与转换索引','',f"{audit['groups']} 个分区，{audit['nodes']} 个节点，{audit['edges']} 条显式连线。所有分区在同一SVG画布内，无隐藏子图。",'',
        '实线=状态转换；青色虚线=并行数据依赖；金色虚线=事件路由；淡红虚线=每个动作继承的全局抢占。数据节点不占角色动作锁，不能把数据连线当角色互斥状态切换。','',
        'G1：死亡/阶段优先；G2：强制中断；G3：租期超时/时序失效。每个动作都列出继承出口。空动画用逻辑计时推进，资源引用保持null。','']
    for g in GROUPS.values():
        md+=['## '+g['title'],'',g['subtitle'],'']
        for nid in g['nodes']:
            n=NODES[nid];md += ['### '+nid+' · '+n['title'],'',n['detail'],'','层级路径：`'+n['hierarchy']+'`','']
            if n['assets']:md+=['预留：'+'；'.join('`'+a['name']+' = null`' for a in n['assets']),'']
            for e in EDGES:
                if e['source']==nid:md.append(f"- **{e['id']} → {e['target']}** [{e['kind']} / 优先级{e['priority']}]：{e['guard']}"+(f"；执行：{e['actions']}" if e['actions'] else ''))
            md.append('')
    (HERE/'全部状态与条件索引.md').write_text('\n'.join(md),encoding='utf-8')


def main():
    build_supervision();build_scheduler();build_m1_coordination();build_m1_moves();build_m2_moves();build_red_and_duet();build_actor_parents();add_contracts()
    audit=validate_graph();width,height=layout();audit.update(canvas_width=width,canvas_height=height)
    graph={'version':'hfsm-design-1.0','width':width,'height':height,'groups':list(GROUPS.values()),'nodes':list(NODES.values()),'edges':EDGES,'move_roots':ROOTS,'aliases':ALIASES,'disabled_moves':DISABLED,'audit':audit}
    (HERE/'fsm_graph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
    svg=render_svg(width,height);(HERE/'Boss全量分层状态机.svg').write_text(svg,encoding='utf-8')
    template=(HERE/'viewer.template.html').read_text(encoding='utf-8')
    data=json.dumps(graph,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    viewer=template.replace('__SVG__',svg).replace('__DATA__',data)
    (HERE/'Boss全量分层状态机.html').write_text(viewer,encoding='utf-8')
    export_tables(audit)
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
