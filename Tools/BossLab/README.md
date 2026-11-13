# BossLab：UE 5.8 白盒战斗测试

打开 `/Game/BossLab/Maps/L_BossLab`，按 Play，点击游戏画面取得键盘焦点。无需主角。

场景中白色 Manny 为大师兄，灰色 Manny 为六名弟子，红色 Quinn 为红衣剑客，青色圆柱是移动靶标。默认每阶段演示 35 秒，走红衣先死→大师兄狂暴→战斗结束的分支。阶段推进用演示伤害触发，不参与压力评分。关闭 `AutoDemo` 后停留在当前阶段，继续自主选招。

## 入口

| 资产 | 用途 |
|---|---|
| `/Game/BossLab/Maps/L_BossLab` | 默认启动地图、测试场景 |
| `/Game/BossLab/Blueprints/BP_BossEncounter_Final` | 战斗逻辑、状态总览、资源接口 |
| `/Game/BossLab/Blueprints/BP_BossLabGameMode` | 观察模式，Default Pawn 为空 |
| `/Game/BossLab/Blueprints/BP_BossLearningSave` | 可选跨场学习存档，版本 2 |

运行时执行普通 Blueprint 字节码；不需要 Python Tick、MCP 在线或额外 FSM 插件。

## 测试操作

| 按键 | 行为 |
|---|---|
| `1 / 2 / 3 / 4` | 重置并进入相应阶段 |
| `B` | 大师兄杀气耗尽、破防 |
| `G` | 大师兄受到足够冲击、坠地；用于二阶段以后 |
| `H` | 对弟子 1 施加伤害、杀气伤害及冲击；连按可测试脱阵与支援 |
| `T` | 向大师兄发送可见攻击威胁，测试格挡／闪避选择 |
| `K` | 击杀红衣剑客；在三阶段测试狂暴分支 |
| `J` | 击杀大师兄；在三阶段测试殉情分支 |
| `R` | 重置战斗，不提交未结算学习 |
| `Space` | 暂停／恢复战斗逻辑 |
| `Esc` | 结束 PIE |

也可选中关卡中的 `BossLab_EncounterDirector`，使用 Details 的 Call In Editor 按钮。正式观察建议进入 Play；编辑器按钮不代替游戏 Tick。

## 状态图与执行逻辑

打开主蓝图的 **EventGraph**，可以在同一页看到 20 个分组、349 个状态定义、756 条带条件的关系，以及 BeginPlay / Tick 入口。中文注释保留状态名称与层级，状态节点输出接入转换定义节点，方便分区截图。完整关系还可用 `Research/Step3/Boss全量分层状态机.html` 放大查看。

需要区分：这 756 条关系包括流程、事件、数据和全局继承关系；它们不全是一次实际运行转换。单页中的 Guard 是设计说明文本，不是运行时表达式解释器。实际条件、选招与状态推进在 49 个蓝图函数中执行；修改 Guard 文本本身不会改变执行行为。

常用函数：

- `CanMove / ComputeWeight / ChooseMove`：逐招资格、权重、探索、概率上限。
- `BuildCombo / ChooseLength / ExecuteBeat`：有限招式池、长度、变招、逐拍执行。
- `StartMove / TickAction / FinishAction`：归阵、前摇、段间过渡、收招及中断。
- `DamageFighter / TickResources`：格挡耗气、破防回气、冲击坠地、脱阵与支援请求。
- `TryServices / CommitService / SetPhase / PhaseCheck`：召唤、吸血、治疗与阶段结算。
- `ReportResponse / RecordRoot / CommitLearning / LoadLearning`：实时压力与跨场学习。
- `PlayPose / MoveActors / Telegraph / EmitBeat`：占位动作、移动、预警和攻击轨迹。

运行时观察 `Phase`、`ActiveState`、`ActorState`、`CurrentMove`、`Beats`、`BeatIndex`、`HP`、`Qi`、`Probabilities`、`Pressure`、`StateVisitCounts`。`StateVisitCounts` 是实际进入该状态 ID 的次数，并不意味着总览中的每个设计节点都已独立执行。

## 已实现的战斗行为

- 四阶段及两种先后击杀结局；三阶段继承二阶段招式并加入双人组合技。
- 一阶段固定红光开场，蓝光 02 / 03、红光 04、弟子末段蓝光轮攻、无光三拍双人剑阵；大师兄普通剑气单独受节奏间隔约束。
- 普通攻击统一调度，合围／双人动作作为一个组合动作执行，避免七人各自无限发起攻击。
- 两弟子加大师兄的剑阵门槛、参与者打断整个剑阵、单个脱阵槽位、持续追打后的支援请求。
- 近距离回旋归阵与分散时高跳归阵的不同时间和目标位置；03 延迟随参与人数变化。
- 75% 血量以下吸取最高血量弟子，等量转移并留 1 HP；不足三名弟子时付出最大血量三分之一召至三名，等于／低于三分之一不能召唤。
- M2 A～F 招式池及有限长度、普通段后的停招／观察分支、远喷丝后的可选蓝刺；近距离红喷丝绝不接蓝刺；M4 六斩末段蓝光。
- 有杀气且朝向满足条件时格挡并耗气；没有自然回气；破防后恢复。坠地与杀气耗尽分别计时，坠地结束后仍破防则继续悬吊。
- 实时压力由本场 `ReportResponse` 事件计算，带去重、12 秒半衰期及 2 秒增减上限；不读取历史胜负给本场加压力。
- 跨场学习在结算时更新，场内冻结；33 个招式和 17 个长度／分支学习键，总共 50 个证据槽；样本预算、衰减、平滑及概率上限均在蓝图内计算。

## 动画与素材接口

本次使用工程已有的 Epic Manny / Quinn、Idle / Run / Jump / Death 与通用攻击动画。它们不是原作专用剑招，也不称作开源动作素材；未下载来源不明的动画。

`BossLab | Unbound Animation Interfaces` 下所有 `AN_…` 变量默认 None，沿用已确认状态的命名。InitEncounter 将这些引用接到 StateAnimations；播放时优先选择当前状态的已绑定动画，其次是 MoveAnimations 对应招式的动画，最后才用通用占位动作。首次接入建议使用兼容 Manny 骨架的 **AnimSequence**；当前单节点播放路径未实现 Montage 分段／通知调度。

`MoveAnimations` 的顺序与 `MoveIDs` 一致。关闭 `UsePlaceholderAnimations` 可禁用通用动画回退。运行中修改绑定后按 R 重新建立映射。

原设计完整的动画、碰撞、特效和音效空绑定清单仍在 `Research/Step3/asset_bindings.json`。碰撞／伤害 Notify 与美术特效未接入；当前轨迹和红蓝黑预警由调试几何展示。程序位移和附加剑模型提供可见动作，不依赖 Root Motion。

## 参数与压力测试

选中 `BossLab_EncounterDirector` 修改 `BossLab | Test Settings`：

- `AutoDemo`、`DemoStageSeconds`：自动阶段展示。
- `MasterDiesFirst`：自动演示改为大师兄先死。
- `MoveTarget`、`TargetMoveRadius`、`TargetMoveSpeed`：移动靶标轨迹。
- `StartingPhase`：开始 Play 时的阶段。
- `SimulateResponses`、`ResponseSkill`：合成靶标应对事件，用于观察压力变化，默认关闭。
- `DemoDamage`：周期性测试来袭伤害，默认关闭。
- `EnableLearningSave`：真实输入的跨场存档，默认关闭。AutoDemo / DemoDamage / SimulateResponses 开启时不会保存演示学习。
- `LoopDemo`：演示循环，默认关闭；`DrawCombatDebug / ShowHUD` 控制显示。

逐招参数表可在蓝图 Class Defaults 中修改 BaseWeights / PressureSlopes / Ranges / Ideals / Widths / Cooldowns / Windups / Recoveries。所有招式数组必须保持与 MoveIDs 的顺序和长度一致。具体数值与概率算法来源于 `Research/Step2/Engineering/战斗决策工程规格.md`；复刻估计值不代表原作内部数据。

对接真实战斗时调用 `DamageFighter(Who, HPDamage, QiDamage, Impulse, BypassGuard)` 与 `ReportResponse(EventID, Outcome, MoveIndex)`。Who：大师兄 0，弟子 1～6，红衣 7。Outcome：受击 0、完美格挡 1、完美闪避 2、普通闪避 3、格挡 4、玩家命中 5、玩家挥空 6、玩家破防 7、被抓 8。组合命中窗口必须共用 EventID，不能按多个攻击者重复记分。

## 这一版的边界

这是可运行、可观察的白盒战斗版本。招式节奏与阶段规则可以测试；动作外观仍然是通用动画和程序轨迹，阵型踏步、悬丝姿态、死亡演出尚不能替代专用动画。

双 Boss 目前由统一主攻队列轮换，组合技两人执行；设计稿中的独立副攻预约日历、角色避障和完整逐帧碰撞尚未启用。非攻击行为采用简化的朝向、环绕、靠近、退距和威胁反应；总览保留了完整设计层级，不能将其理解为已经做完原设计所有细粒度执行节点。输入威胁依靠接口／测试键，未创建玩家角色或玩家战斗系统。

## 验证与再生成

`Saved/BossImplementation/runtime_verification.json`：32 / 32 项真实 PIE 蓝图检查通过。

`Saved/BossImplementation/learning_verification.json`：11 / 11 项真实 PIE 蓝图学习与剑阵检查通过。

原 Python 工程参考模型：25 项单测通过、100,000 个随机上下文未发现概率约束违规。该模型测试与 UE 测试独立记录，不能互相代替。尚未进行打包或真实玩家碰撞验证。

编辑器里依次执行 `Tools/BossLab/build_runtime.py`、`Tools/BossLab/build_scene.py` 可生成资产。重复生成会创建新的运行蓝图版本，避免 UE 大图原地重构导致的原生编辑器崩溃。生成报告指出当前使用的蓝图；关卡构建会读取报告并绑定它。测试脚本只能在 PIE 中执行，会修改并重置测试中的战斗，应在测试结束后退出 PIE。

原 DefaultEngine.ini 的损坏前缀修复前备份在 `Saved/BossImplementation/Backup/DefaultEngine.before_boss.ini`。本次把启动地图设为 BossLab，原有游戏地图与角色资产保留。
