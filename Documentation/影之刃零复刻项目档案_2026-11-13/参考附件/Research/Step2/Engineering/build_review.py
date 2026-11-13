"""Build human-readable artifacts from the SAME tested catalog and simulation output."""
from pathlib import Path
import csv
import json
from catalog import MOVES, ALIASES, DISABLED

HERE = Path(__file__).resolve().parent


def load_csv(name):
    with (HERE / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def probability_table():
    lines = ["# 逐招参数与概率表", "", "所有数字为本项目复刻默认，不是原作解包数据。由 catalog.py 自动生成。",
             "", "b 是基础权重、k 是压力斜率；距离单位 cm，时间单位 s。实际概率须代入工程规格第5节，不能直接把 b 当百分比。",
             "", "G=大师兄/可出手弟子择一；M=大师兄；Q=大师兄独立剑气；D=两名Boss联合；R=红衣。",
             "", "普通拍间隔0.50，彩色拍0.85，有效窗0.18；阵法额外归阵0.6/1.3；M1-03额外每次借力0.22；观察额外0.35。",
             "", "| ID／内容 | 阶段 | 演员 | b | k | 最大距 | 理想距μ | 宽度σ | CD | 前摇 | 收势 | 最少弟子 | 危险候选 |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for m in MOVES.values():
        lines.append(f"| {m.id} {m.name} | {','.join(map(str,m.phases))} | {m.owner} | {m.base:g} | {m.pressure:g} | {m.reach:g} | {m.ideal:g} | {m.width:g} | {m.cooldown:g} | {m.windup:g} | {m.recovery:g} | {m.disciples} | {'是' if m.danger else '否'} |")
    lines += ["", "## 招式内容与独立学习键", "", "| ID | 原子序列 | 学习说明 |", "|---|---|---|"]
    for m in MOVES.values():
        note = "根ID一份学习证据"
        if m.id in ("M2-01-C", "M2-01-E"):
            note += "；另有 /length/1..4 条件证据"
        if m.id == "M2-05-F":
            note += "；另有 /blue 追加段条件证据"
        lines.append(f"| {m.id} | {' → '.join(m.atoms)} | {note} |")
    lines += ["", "原子与可变模板的具体内容、颜色、节点规则见工程规格第6、7节。R-01/02普通、R-03/04红光、R-05蓝光收尾、R-07/08黑光；红衣具体节奏与参数为资料不足下的复刻补全，应与用户已确认的大师兄动作区分来源。",
              "", "M1-01招架属于反应防御状态，不与随机攻击原子混抽。M1普通攻击之间0.18秒过渡。M1-09的3拍中，J指双人跳劈一组，Q指最后双人与大师兄的一次共同剑气窗口。",
              "", "别名：" + "；".join(f"{a}→{b}" for a,b in ALIASES.items()) + "。",
              "", "禁用：" + "、".join(DISABLED) + "。无证据招式不自动激活；大师兄黑光排除项保持禁用。",
              "", "## 固定上下文示例：M2、350cm、无历史重复／冷却、双方资源正常", "",
              "表中为已决定攻击后的条件率；本次决策率还需乘O，预约失败则不启动。跨场记忆中立。",
              "", "| 招式 | P=−80 | P=0 | P=80 |", "|---|---:|---:|---:|"]
    rows = load_csv("probability_scenarios.csv")
    selected = [r for r in rows if r["phase"] == "2" and r["distance"] == "350" and r["memory"] == "neutral"]
    for key in sorted({r["move"] for r in selected}):
        values = [next(float(r["conditional_probability"]) for r in selected if r["move"] == key and int(r["pressure"]) == p) for p in (-80,0,80)]
        lines.append(f"| {key} | " + " | ".join(f"{p:.2%}" for p in values) + " |")
    lines += ["", "三列O依次为55.6%、70.0%、84.4%；满3秒且仍有合法攻击时O=100%。更多阶段、距离、构造历史条件见 probability_scenarios.csv 与交互页面。"]
    (HERE / "逐招参数与概率表.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def report():
    r = json.loads((HERE / "simulation_results.json").read_text(encoding="utf-8"))
    f, c, j = r["fuzz"], r["calendar"], r["joint_scheduler"]
    lines = ["# 模拟与核对报告", "", "模型 boss-policy-1.0；主随机种子 20261112；2026-11-12。数字从本次实际运行的 simulation_results.json 自动生成。",
             "", "结论：本版在所列检查中没有出现非法选择、概率异常、无限连招、跨动作时刻冲突或遗留角色锁。它提供可复现的算法依据；尚不能据此保证 UE 集成、碰撞与实际战斗体验没有Bug。",
             "", "## 运行范围与结果", "", "| 检查 | 实际规模 | 结果 |", "|---|---:|---|",
             f"| 自动边界测试 | {r['unit_tests']} 项 | {r['unit_failures']} 失败 |",
             f"| 随机上下文 | {f['contexts']:,} 组 | {f['nonempty']:,} 组有合法候选；{f['moves_reached']} / {len(MOVES)} 招可达；0非法概率 |",
             f"| 固定分布抽样 | {r['frequency']['draws']:,} 次 | 所有招式误差在逐项6σ界内 |",
             f"| 固定阶段合成会话 | {r['fixed_phase_attempts']:,} 场 | 6种玩家模型 × 4阶段 × 48种子 |",
             f"| 连续学习会话 | {r['longitudinal_attempts']} 场 | 3种模型，各连续30场 |",
             f"| 会话选择与结算 | {r['total_decisions']:,} 次决策、{r['total_attacks']:,} 次起招、{r['total_events']:,} 个结果事件 | 最大{r['max_combo_beats']}伤害拍；无三连相同根或三连危险根 |",
             f"| 日历过载请求 | {c['requests']:,} 次 | 通过{c['accepted']:,}，拒绝{c['rejected']:,}，0冲突 |",
             f"| 多角色锁＋分支预订联合压力测试 | {j['requests']:,} 次 | 通过{j['accepted']:,}，拒绝{j['rejected']:,}，0角色重叠／孤儿预约／遗留锁 |",
             "", f"固定分布最大绝对频率误差为 **{r['frequency']['max_absolute_error']*100:.4f} 个百分点**。这检查随机实现是否忠实于公式，不代表公式天然平衡。",
             "", "随机上下文特意包括不可见、超距、角色不可行动、冷却未到、人员不足，因此空池是正确结果，不是6万次失败。过载测试每0.10/0.15秒塞入一套完整攻击，远高于正式调度频率；大量拒绝表示安全等待，不能把通过率解读为实战空转率。联合测试还执行了角色中断、分支并集预约和阶段纪元切换。",
             "", "## 合成玩家的行为差异", "", "每场保持指定阶段180逻辑秒，随机距离180/350/600/1000/1600cm。玩家成功率为人为输入；普通失败可部分转为格挡，8%根动作模拟玩家主动打断。命中结果随机采样，不模拟真实玩家生命、真实路线或完整通关时间。",
             "", "| 阶段 | 玩家模型 | 平均压力 | 危险候选根占比 | 完整动作平均拍数 | 正压力顶格事件占比 |", "|---|---|---:|---:|---:|---:|"]
    names = {"novice":"应对较弱", "expert":"应对熟练", "blue_weak":"蓝光薄弱", "red_weak":"红光薄弱", "aggressive":"持续进攻", "passive":"不主动攻击"}
    for row in r["aggregate"]:
        lines.append(f"| M{row['phase']} | {names[row['profile']]} | {row['mean_pressure']:.2f} | {row['danger_fraction']:.2%} | {row['mean_combo_beats']:.2f} | {row['saturated_positive_fraction']:.2%} |")
    lines += ["", "判读：",
              "", "1. 压力能区分近期成功与失败；有效进攻产生−1事件，不主动进攻本身没有额外加分或扣分。此处持续进攻与不进攻模型的防御成功率也不同，不能用二者均值单独证明进攻行为的因果作用。",
              "2. 危险候选根占比受到‘连续两次后必须等普通招机会’的硬限制，等待期间可移动，但移动不清计数。高压力下不会无限接红蓝黑。高低压力的危险占比差异可能只有几个百分点，这是约束发挥作用；差异还体现在进攻门概率、具体长模板、前缀长度及追加蓝刺上。",
              "3. 危险候选占比不是彩色攻击拍占比：远无光喷射可能不追加蓝光，A–D也可能停招，但仍按危险候选预算。",
              "4. 低成功率输入下正压力经常达到顶格，说明本版保留了‘吃招后加压’的设计方向。通过滚动上限、12秒衰减、常规进攻门上限88%（空闲且3秒未攻时可到100%）、危险连发限制和不可压缩预警控制反馈强度。真实体验若过苛刻，先调事件增量和半衰期，不放松安全约束。",
              "5. 会话内每次动作都有正时间推进，循环看门狗2000次/会话未触发；但这不是对玩家永久不在导航范围内时‘必须打到玩家’的承诺。",
              "", "## 跨场学习的实际变化", "", "下表是同一合成玩家连续训练后的下一场权重倍率，不是概率。每场开始冻结，结束才改变。",
              "", "| 玩家模型 | 完成场数 | 独立蓝突刺L | 红衣红光远程L |", "|---|---:|---:|---:|"]
    for row in r["longitudinal"]:
        if row["battle"] in (1,10,30):
            lines.append(f"| {names[row['profile']]} | {row['battle']} | {row['blue_multiplier_next']:.3f} | {row['red_multiplier_next']:.3f} |")
    lines += ["", "能看到蓝光薄弱时蓝刺被提高，红光薄弱时红衣红光被提高，熟练应对时两者下降。下降不等于删除：探索、先验和上限仍生效。每招最终概率需要与其他招一起归一化，不能把倍率1.6当成60%出招率。",
              "", "## 审查中处理的关键漏洞", "",
              "- 召唤血量与吸血形成增益环：新召唤总血量限制为费用的80%，吸血等量转移；每次召唤总血至少减少200，保留用户要求的无固定召唤次数规则。",
              "- 远喷射起手无光绕过危险连发限制：按可能带蓝的危险候选计数。",
              "- 动态追加蓝刺／停顿改变命中时刻：预订可能分支的时刻并集，提前解决冲突，禁止预警之后临时挪动时间。",
              "- 远喷射够得着但追加突刺够不着：分支节点重新检查蓝刺1100cm范围、视线与可行动性；不合法直接结束，不采未执行样本。",
              "- 归阵与观察时间在时长和日历各算一遍导致不一致：两者统一调用 impact_offsets，边界测试逐招比较。",
              "- 大师兄无法行动误冻结所有弟子：普通攻击使用G演员组，仍有可行动弟子就能参加选择。",
              "- 同一时间直接写入长期学习导致重复放大：冻结战斗快照，结束一次性更新；Abort不写入。",
              "- M2致死越过半血引发补血／假无敌：先触发加入锁存，再按真实死亡殉情；不凭空加血。",
              "- 破防与坠地共用一个状态计时：拆成独立维度；破防期间不重复扣恢复中杀气或延长回满时间。",
              "- 死亡后服务继续吸血／治疗复活：死亡与终局检查先于资源服务。",
              "- 双Boss部分拿锁互等：原子申请、失败整体回滚、租期超时、阶段纪元取消。",
              "", "## 已覆盖的边界与仍待实机验证的边界", "",
              "已覆盖：450cm喷射分界；HP恰为75%与1/3；最少参阵人数；大师兄不可行动而弟子可行动；独立红衣距离；别名与共享冷却；0/1/2/多招候选；无视线；所有招式可达；极端权重；无自然回气；破防与坠地重叠；治疗守恒；双亡；阶段不可逆；分支预留与锁清理。具体断言见 test_results.txt 和 verify.py。",
              "", "尚未用UE验证：威胁可见性判定、真实格挡角度、闪避位移、动画预警可读性、普通硬直抗连控、导航失败、玩家与Boss同帧死亡的完整调度、服务前摇重检、网络复制、帧率波动。参考程序包含算法组件和独立调度压力测试，合成会话没有把以上所有组件整合为一个物理战斗器。",
              "", "红衣具体动作和数值、阵型几何、借力次数映射等补全仍是设计假设。模拟未验证玩家主观公平性；任何‘原作一定如此’或‘绝对不会有Bug’的结论都超出本次证据。下一步应将这些约束映射成HFSM节点与守卫，再在逻辑蓝图中进行同样的自动事件回放。",
              "", "## 复现", "", "```powershell", "& 'D:\\Program Files\\Unreal\\UE_5.8\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe' -B Research/Step2/Engineering/verify.py", "& 'D:\\Program Files\\Unreal\\UE_5.8\\Engine\\Binaries\\ThirdParty\\Python3\\Win64\\python.exe' -B Research/Step2/Engineering/build_review.py", "```", "", "Python 3.10+，仅标准库。测试未通过时 verify.py 返回非零，不生成新的通过报告。当前目录是UE项目根目录。"]
    (HERE / "模拟与核对报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def dashboard():
    catalog = json.loads((HERE / "move_catalog.json").read_text(encoding="utf-8"))
    rows = load_csv("probability_scenarios.csv")
    scenarios = {}
    for row in rows:
        key = "/".join(row[k] for k in ("phase", "distance", "pressure", "memory"))
        scenarios.setdefault(key, []).append({"id": row["move"], "q": float(row["conditional_probability"]), "p": float(row["decision_probability"])})
    data = {"moves": catalog["moves"], "scenarios": scenarios}
    html = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>七星剑阵 · 双 Boss 决策检查器</title>
<style>
:root{color-scheme:dark;--bg:#10151b;--panel:#19222c;--muted:#a5b5c3;--ink:#eff4f6;--gold:#e9bd75;--line:#31404e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1300px;margin:auto;padding:38px 28px 60px}h1{font-size:32px;line-height:1.3;margin:10px 0}h2{font-size:20px;margin:0 0 16px}.eyebrow{color:var(--gold);letter-spacing:.12em;font-size:13px}.muted{color:var(--muted)}p{margin:8px 0 20px}.path{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0}.path div,.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}.path b{display:block;color:var(--gold)}.path small{color:var(--muted)}.controls{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}label{display:block;color:var(--muted);font-size:13px}select{display:block;width:100%;margin-top:8px;padding:12px;background:#111a23;color:var(--ink);border:1px solid #526171;border-radius:7px;font:inherit}select:focus{outline:2px solid var(--gold)}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0}.metric{padding:14px 18px;border-left:3px solid var(--gold);background:#19222c}.metric strong{display:block;font-size:27px}.metric small{color:var(--muted)}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th{text-align:left;color:var(--muted);font-size:13px}td,th{padding:12px 10px;border-bottom:1px solid var(--line)}td:first-child{min-width:230px}.id{font-size:12px;color:var(--muted);display:block}.bar{height:9px;background:#283747;border-radius:8px;width:140px;margin-top:7px;overflow:hidden}.fill{height:100%;background:var(--gold)}.blue{color:#8cceff}.red{color:#ff8b87}.black{color:#d7b4ff}.scroll{overflow-x:auto}.notes{margin-top:26px;display:grid;grid-template-columns:1fr 1fr;gap:18px}.notes p{font-size:14px;margin-bottom:0}.tag{border:1px solid #53616e;border-radius:5px;padding:1px 6px;font-size:12px}a{color:#add9ff}.formula{font-family:ui-monospace,monospace;font-size:14px;color:#d9e4ec}@media(max-width:800px){main{padding:22px 16px}.controls,.path,.notes{grid-template-columns:1fr 1fr}.metrics{grid-template-columns:1fr}h1{font-size:25px}}@media print{body{background:white;color:black}.panel,.path div,.metric{background:white;border-color:#aaa}.muted,label,th,.id{color:#555}}
</style></head><body><main>
<div class="eyebrow">第二步 · 工程量化设计 · V1.0</div>
<h1>七星剑阵与双 Boss：出招概率检查器</h1>
<p class="muted">切换本场压力与上一场留下的招式经验，查看同一公式如何改变每招概率。以下是本项目的复刻默认值。</p>
<div class="path"><div><b>① 本场结果 → 压力</b><small>每场从0开始，仅使用已结算操作</small></div><div><b>② 历史应对 → 学习倍率</b><small>开战冻结，结束后更新</small></div><div><b>③ 筛选 → 归一化</b><small>阶段、距离、冷却、重复与人员</small></div><div><b>④ 预约 → 有限执行</b><small>角色锁、攻击间隔、合法变招节点</small></div></div>
<section class="panel"><h2>选择比较场景</h2><div class="controls">
<label>战斗阶段<select id="phase"><option value="1">M1 · 七星剑阵</option><option value="2" selected>M2 · 丝线大师兄</option><option value="3">M3 · 双 Boss</option><option value="4">M4 · 大师兄狂暴</option></select></label>
<label>玩家距离<select id="distance"><option value="180">180 cm · 贴身</option><option value="350" selected>350 cm · 近距</option><option value="800">800 cm · 中距</option><option value="1400">1400 cm · 远距</option></select></label>
<label>本场实时压力<select id="pressure"><option value="-80">−80 · 玩家应对有利</option><option value="0" selected>0 · 中立</option><option value="80">+80 · 玩家受到高压</option></select></label>
<label>冻结的历史经验<select id="memory"><option value="neutral">无历史 · 所有L=1</option><option value="blue_weak">蓝招应对薄弱</option><option value="red_weak">红招应对薄弱</option><option value="mastered">所有招较熟练</option></select></label>
</div><p class="muted" style="margin-top:16px;font-size:13px">比较条件：冷却均就绪、无最近重复、6名弟子可参阵、双方可行动、有视线、无玩家杀气或收势加权、未触发3秒必攻。双 Boss 使用相同距离。历史非中立选项为构造的40份有效证据：薄弱招S/F=4/36，其余32/8。</p></section>
<div class="metrics"><div class="metric"><small>本次决策进入攻击的概率 O</small><strong id="offense"></strong></div><div class="metric"><small>合法主通道根招</small><strong id="count"></strong></div><div class="metric"><small>危险候选条件占比</small><strong id="danger"></strong></div></div>
<section class="panel"><h2>逐招概率</h2><p class="muted" style="font-size:14px">条件率之和为100%。本次决策率 = O × 条件率；实际开始仍要求角色与时间预约成功。危险候选包括可能追加蓝光的无光喷射。</p><div class="scroll"><table><thead><tr><th>根招式</th><th>攻击条件率 q</th><th>本次决策率 Oq</th><th>基础权重 / 压力斜率</th><th>冷却 / 前摇</th></tr></thead><tbody id="body"></tbody></table></div></section>
<div class="notes"><section class="panel"><h2>从根招进入分支</h2><p class="formula">wᵢ = bᵢ · exp(kᵢP/100) · Lᵢ · 距离 · 重复 · 等待 · 环境</p><p class="muted">先混入12%探索，再封顶再分配。≥3招每招至多45%；2招至多65%；唯一合法招为100%。远喷射在命中结算后才决定是否追加蓝刺，近距红喷射禁止追加。</p></section><section class="panel"><h2>始终有效的约束</h2><p class="muted">大师兄没有黑光；无闪避无敌帧；杀气仅破防后恢复；最多7伤害拍；禁止第三次连续相同根招或危险候选；不同动作的彩色命中间隔至少0.65秒。</p></section></div>
<p class="muted" style="margin-top:24px;font-size:13px">本页面展示192组由已测试Python公式生成的静态上下文，不是实机胜率预测，也不是完整状态机图。M1独立剑气、副通道、确定性生命服务的额外概率见工程规格。所有数据内嵌，可离线打开。</p>
<p><a href="战斗决策工程规格.md">工程规格</a> · <a href="逐招参数与概率表.md">逐招参数</a> · <a href="模拟与核对报告.md">模拟报告</a></p>
</main><script id="model-data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('model-data').textContent);
const byId=Object.fromEntries(data.moves.map(m=>[m.id,m]));
const controls=['phase','distance','pressure','memory'];
function pct(x){return (100*x).toFixed(2)+'%'}
function update(){
 const key=controls.map(k=>document.getElementById(k).value).join('/');
 const rows=[...(data.scenarios[key]||[])].sort((a,b)=>b.q-a.q);
 document.getElementById('offense').textContent=pct(rows.reduce((s,r)=>s+r.p,0));
 document.getElementById('count').textContent=rows.length+' 招';
 document.getElementById('danger').textContent=pct(rows.filter(r=>byId[r.id].danger).reduce((s,r)=>s+r.q,0));
 const body=document.getElementById('body');body.replaceChildren();
 rows.forEach(r=>{const m=byId[r.id],tr=document.createElement('tr');
 const td=document.createElement('td');td.textContent=m.name;const span=document.createElement('span');span.className='id';span.textContent=m.id+(m.danger?' · 危险候选':' · 普通');td.append(span);tr.append(td);
 const q=document.createElement('td');q.textContent=pct(r.q);const bar=document.createElement('div');bar.className='bar';const fill=document.createElement('div');fill.className='fill';fill.style.width=(r.q*100)+'%';bar.append(fill);q.append(bar);tr.append(q);
 [pct(r.p),m.base+' / '+m.pressure,m.cooldown+'s / '+m.windup+'s'].forEach(v=>{const t=document.createElement('td');t.textContent=v;tr.append(t)});body.append(tr);});
}
controls.forEach(k=>document.getElementById(k).addEventListener('change',update));update();
</script></body></html>'''
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (HERE / "概率检查器.html").write_text(html, encoding="utf-8")


def main():
    probability_table()
    report()
    dashboard()
    print("Generated parameter table, audit report and offline probability dashboard.")


if __name__ == "__main__":
    main()
