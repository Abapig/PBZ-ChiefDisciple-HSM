"""Versioned reproduction defaults, not recovered Phantom Blade Zero data."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json

VERSION = "boss-policy-1.0"

@dataclass(frozen=True)
class Move:
    id: str
    name: str
    phases: tuple
    owner: str
    family: str
    base: float
    pressure: float
    reach: float
    ideal: float
    width: float
    cooldown: float
    windup: float
    recovery: float
    atoms: tuple
    disciples: int = 0
    danger: bool = False

# id | name | phases | owner | family | base | pressure | max cm | ideal cm |
# width cm | cooldown s | windup s | recovery s | authored atoms | disciples | danger
ROWS = """
M1-01-L|左横劈|1|M|basic|12|-.25|300|170|180|1.2|.55|.45|L|0|0
M1-01-R|右横劈|1|M|basic|12|-.25|300|170|180|1.2|.55|.45|R|0|0
M1-01-D|下劈|1|M|basic|10|-.15|320|190|180|1.6|.65|.55|D|0|0
M1-01-J|跳劈|1|M|basic|8|.15|600|400|250|3|.8|.65|J|0|0
M1-01-T|戳刺|1|M|basic|10|0|430|280|200|2|.6|.5|T|0|0
M1-01-U|上挑|1|M|basic|8|.1|260|140|150|2|.6|.5|U|0|0
M1-01-K|鞭腿|1|M|basic|8|.1|230|110|140|2|.5|.5|K|0|0
M1-01-Q|大师兄普通剑气|1|Q|wave|10|.15|1600|700|650|4|.7|.5|Q|0|0
M1-02|跳板跃斩|1|M|formation|10|.45|1100|650|500|9|.85|.9|B:J|2|1
M1-03|阶梯借势冲刺|1|M|formation|10|.6|1500|900|600|10|.85|1|B:T|2|1
M1-04|多向合围突刺|1|M|formation|8|.8|1200|600|500|12|.9|1|R:T|2|1
M1-07|七人轮攻|1|M|formation|8|.7|1000|500|500|12|.75|1|ROTATION|2|1
M1-09|无光三拍剑阵|1|M|formation|10|.2|1300|650|600|10|.8|.9|J,J,Q|6|0
M2-01-A|四斩蓝刺|2,3,4|M|sword|14|.4|600|300|300|3|.65|.8|L,R,U,D,B:T|0|1
M2-01-B|二斩蓝刺|2,3,4|M|sword|18|-.1|550|280|280|2|.65|.75|L,R,B:T|0|1
M2-01-C|可变前缀接二斩|2,3,4|M|sword|9|.8|650|350|320|7|.7|.95|PREFIX,L,R,B:T|0|1
M2-01-D|二刺接蓝刺|2,3,4|M|sword|12|.25|750|400|350|4|.7|.8|T,T,B:T|0|1
M2-01-E|普通无光剑招|2,3,4|M|sword|18|-.65|600|300|300|1.5|.6|.6|PLAIN|0|0
M2-01-F|独立蓝光突刺|2,3,4|M|sword|10|.35|1100|600|500|5|.85|.85|B:T|0|1
M2-03|高空无光追踪丝线|2,3,4|M|thread|10|.25|2000|1200|900|12|1|1|Q,Q,Q,Q|0|0
M2-04|拉远红光攻击|2,3,4|M|thread|9|.7|2000|1300|800|10|1|1.1|R:Q|0|1
M2-05-N|近距红光扇形喷射|2,3,4|M|spray|10|.6|450|250|250|8|.85|.9|R:SPRAY|0|1
M2-05-F|远距无光扇形喷射|2,3,4|M|spray|12|.2|1800|1000|700|8|.85|.85|SPRAY|0|1
M3-01|双人蓝光齐攻|3|D|duet|11|.7|1000|500|500|12|1|1.1|B:DUET|0|1
M3-02|双人错拍红光|3|D|duet|8|.9|1800|800|700|14|1|1.2|R:M,R:R|0|1
M4-01|丝线长剑六连斩|4|M|rage|20|.7|1100|650|500|8|.85|1.2|L,R,U,D,L,B:D|0|1
R-01|红衣三连快剑|3|R|red_sword|18|-.25|350|180|200|2|.55|.65|L,R,D|0|0
R-02|红衣剑腿组合|3|R|red_sword|14|0|280|140|180|3|.55|.7|L,K,R|0|0
R-03|二斩接红光后翻斩|3|R|red_special|10|.45|400|230|230|7|.65|.85|L,R,R:BACK|0|1
R-04|红光后翻投刃|3|R|red_special|10|.4|1700|950|650|7|.85|.85|R:Q|0|1
R-05|踏空二斩蓝光收尾|3|R|red_special|12|.35|700|400|350|5|.75|.8|L,R,B:D|0|1
R-07|黑光束缚突袭|3|R|black|7|.9|1300|700|550|13|1|1.1|K:BIND|0|1
R-08|黑光极速挥剑|3|R|black|6|.85|380|230|200|12|.8|1|K:D|0|1
"""

def parse():
    result = {}
    for row in ROWS.strip().splitlines():
        v = row.split("|")
        move = Move(v[0], v[1], tuple(map(int, v[2].split(","))), v[3], v[4],
                    *map(float, v[5:13]), tuple(v[13].split(",")), int(v[14]), bool(int(v[15])))
        if move.family == "basic":
            move = Move(**{**asdict(move), "owner": "G"})
        result[move.id] = move
    return result

MOVES = parse()
ALIASES = {"M1-06": "M1-04", "M2-02": "M2-01-F", "R-06": "R-04"}
DISABLED = ["M1-05", "M1-08", "M2-06", "R-09"]
EVENT_WEIGHTS = {"parry": -12, "perfect_dodge": -8, "dodge": -5,
                 "attack_hit": -1, "block": 2, "attack_miss": 3,
                 "hit": 30, "break": 40, "grab": 45}
RESPONSE_SCORE = {"parry": 1., "perfect_dodge": 1., "dodge": 1.,
                  "interrupt": 1., "block": .65, "hit": 0., "break": 0., "grab": 0.}

def export(path):
    data = {"version": VERSION, "source": "reproduction_design",
            "moves": [asdict(m) for m in MOVES.values()], "aliases": ALIASES,
            "disabled": DISABLED, "event_weights": EVENT_WEIGHTS,
            "response_score": RESPONSE_SCORE}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    export(Path(__file__).with_name("move_catalog.json"))
