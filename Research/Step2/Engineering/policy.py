"""Executable decision reference. Standard library only; no Unreal/art bindings.

Includes probability selection, frozen cross-battle memory, finite combo branches,
phase transactions, resource recovery, health services and attack reservations.
"""
from dataclasses import dataclass, field
from collections import defaultdict, deque
import math
import random
from catalog import MOVES, EVENT_WEIGHTS, RESPONSE_SCORE

def clamp(x, lo, hi):
    return min(hi, max(lo, x))

def sigmoid(x):
    return 1 / (1 + math.exp(-clamp(x, -30, 30)))

@dataclass
class Pressure:
    value: float = 0.
    time: float = 0.
    seen: set = field(default_factory=set)
    recent: deque = field(default_factory=deque)

    def advance(self, time):
        if time < self.time:
            raise ValueError("non-monotonic pressure clock")
        # Decay is independent of resources and is disabled by caller during cinematics.
        self.value *= 2 ** (-(time - self.time) / 12.)
        self.time = time
        while self.recent and self.recent[0][0] <= time - 2.:
            self.recent.popleft()

    def apply(self, event_id, outcomes, time):
        self.advance(time)
        if event_id in self.seen:
            return 0.
        self.seen.add(event_id)
        # One semantic episode (attack instance/beat), worst outcome takes precedence.
        # Attack hit/miss is submitted on its own player-attack episode.
        order = ["grab", "break", "hit", "block", "parry", "perfect_dodge", "dodge",
                 "attack_hit", "attack_miss"]
        outcome = next((o for o in order if o in outcomes), None)
        if outcome is None:
            return 0.
        raw = EVENT_WEIGHTS[outcome]
        positive = raw > 0
        used = sum(abs(d) for _, d in self.recent if (d > 0) == positive)
        budget = 60. if positive else 30.
        delta = math.copysign(min(abs(raw), max(0., budget - used)), raw)
        self.value = clamp(self.value + delta, -100., 100.)
        self.recent.append((time, delta))
        return delta

@dataclass
class Evidence:
    success: float = 0.
    failure: float = 0.

class Learning:
    """Persisted evidence is immutable during a battle. Samples commit exactly once."""
    def __init__(self):
        self.saved = {}
        self.committed = set()
        self.active = None
        self.snapshot = {}
        self.pending = defaultdict(list)
        self.sample_ids = set()

    def begin(self, battle_id):
        if self.active is not None or battle_id in self.committed:
            raise ValueError("battle already active/committed")
        self.active = battle_id
        self.snapshot = {k: Evidence(v.success, v.failure) for k, v in self.saved.items()}
        self.pending = defaultdict(list)
        self.sample_ids = set()

    def multiplier(self, key):
        e = self.snapshot.get(key, Evidence())
        n = e.success + e.failure
        posterior = (2 + e.success) / (4 + n)
        confidence = n / (n + 8)
        return math.exp(1.2 * confidence * (1 - 2 * posterior))

    def sample(self, sample_id, key, score, eligible=True):
        if self.active is None:
            raise ValueError("no battle")
        if not eligible or sample_id in self.sample_ids:
            return
        self.sample_ids.add(sample_id)
        self.pending[key].append(clamp(score, 0., 1.))

    def finish(self, reason):
        if self.active is None:
            return False
        if reason not in ("victory", "defeat"):
            # Abort/reload is explicitly not a completed attempt.
            self.active = None
            self.pending.clear()
            return False
        battle_id = self.active
        for key in sorted(set(self.saved) | set(self.pending)):
            e = self.saved.get(key, Evidence())
            samples = self.pending.get(key, [])
            scale = min(1., 6 / len(samples)) if samples else 0.
            success = .9 * e.success + scale * sum(samples)
            failure = .9 * e.failure + scale * sum(1 - s for s in samples)
            compression = min(1., 40 / (success + failure)) if success + failure else 1.
            self.saved[key] = Evidence(success * compression, failure * compression)
        self.committed.add(battle_id)
        self.active = None
        return True

def capped_distribution(weights, explore=.12, requested_cap=.45):
    """Exploration mixture followed by water filling; feasible even for n=1/2."""
    if not weights:
        return {}
    if any(not math.isfinite(v) or v <= 0 for v in weights.values()):
        raise ValueError("weights must be positive finite")
    n = len(weights)
    total = math.fsum(weights.values())
    raw = {k: (1 - explore) * v / total + explore / n for k, v in weights.items()}
    cap = max(requested_cap, 1 / n)
    # For exactly two moves, use .65 cap instead of making adaptation disappear at .5.
    if n == 2:
        cap = .65
    left, mass, result = dict(raw), 1., {}
    while left:
        total = math.fsum(left.values())
        over = [k for k, v in left.items() if mass * v / total > cap + 1e-12]
        if not over:
            result.update({k: mass * v / total for k, v in left.items()})
            break
        for k in over:
            result[k] = cap
            mass -= cap
            del left[k]
    return result

@dataclass
class Context:
    phase: int = 2
    distance: float = 350.
    now: float = 0.
    pressure: float = 0.
    ready_disciples: int = 6
    master_ready: bool = True
    red_ready: bool = True
    red_alive: bool = True
    los: bool = True
    low_player_qi: bool = False
    punish_window: bool = False
    red_distance: float | None = None

    def distance_for(self, move):
        red = self.distance if self.red_distance is None else self.red_distance
        return red if move.owner == "R" else max(self.distance, red) if move.owner == "D" else self.distance

class Selector:
    def __init__(self, learning):
        self.learning = learning
        self.cooldowns = {}
        self.history = deque(maxlen=4)
        self.age = defaultdict(int)

    def phase_changed(self):
        self.history.clear()
        self.age.clear()
        # Inherited move cooldowns persist; a phase change cannot refresh a move.

    @staticmethod
    def cd_key(move):
        return "M2-05" if move.id.startswith("M2-05") else move.id

    def eligible(self, m, c, channel="primary"):
        if channel not in ("primary", "wave", "secondary"):
            raise ValueError("unknown channel")
        if c.phase not in m.phases or not c.los or c.distance_for(m) > m.reach:
            return False
        if channel == "wave" and m.owner != "Q":
            return False
        if channel == "secondary" and m.id not in ("R-01", "R-02"):
            return False
        if channel == "primary" and m.owner == "Q":
            return False
        if m.owner in ("M", "Q", "D") and not c.master_ready:
            return False
        if m.owner == "G" and not c.master_ready and c.ready_disciples < 1:
            return False
        if m.owner in ("R", "D") and (not c.red_alive or not c.red_ready):
            return False
        if m.disciples > c.ready_disciples:
            return False
        if m.id == "M2-05-F" and c.distance <= 450:
            return False
        if c.now < self.cooldowns.get(self.cd_key(m), 0):
            return False
        # Never select the same attack as three consecutive root actions.
        if len(self.history) >= 2 and list(self.history)[-2:] == [m.id, m.id]:
            return False
        if m.danger and len(self.history) >= 2 and all(MOVES[k].danger for k in list(self.history)[-2:]):
            return False
        return True

    def distribution(self, c, channel="primary"):
        weights = {}
        x = clamp(c.pressure / 100, -1., 1.)
        for m in MOVES.values():
            if not self.eligible(m, c, channel):
                continue
            distance = .25 + .75 * math.exp(-.5 * ((c.distance_for(m) - m.ideal) / m.width) ** 2)
            last_factor = .25 if self.history and self.history[-1] == m.id else 1.
            repetition = .7 ** list(self.history).count(m.id) * last_factor
            starvation = 1 + .04 * min(self.age[m.id], 10)
            situation = (1.15 if c.low_player_qi and m.danger else 1.) * (
                1.2 if c.punish_window and m.windup <= .7 else 1.)
            weights[m.id] = (m.base * math.exp(m.pressure * x) *
                             self.learning.multiplier(m.id) * distance * repetition * starvation * situation)
        return capped_distribution(weights)

    def commit(self, move_id, c, admitted):
        if move_id not in admitted:
            raise ValueError("move not admitted")
        m = MOVES[move_id]
        for k in admitted:
            self.age[k] = min(10, self.age[k] + 1)
        self.age[move_id] = 0
        self.history.append(move_id)
        self.cooldowns[self.cd_key(m)] = c.now + m.cooldown

def choose(distribution, rng):
    if not distribution:
        return None
    x = rng.random()
    last = None
    for key, p in distribution.items():
        last = key
        x -= p
        if x <= 0:
            return key
    return last

def offense_probability(pressure, elapsed):
    if elapsed >= 3.:
        return 1.
    return clamp(.70 + .18 * clamp(pressure / 100, -1, 1), .52, .88)

def movement_distribution(distance, qi_fraction):
    return capped_distribution({"chase": 3. if distance > 650 else .5,
                                "retreat": 1. + (2. if qi_fraction < .3 else 0),
                                "strafe": 2., "standoff": 2.}, explore=0, requested_cap=.65)

NORMALS = ("L", "R", "U", "D", "T")
# All edges explicit; repeated thrust is reserved for the authored D series.
EDGES = {"L": ("R", "U", "T"), "R": ("L", "D", "T"),
         "U": ("D", "R", "T"), "D": ("U", "L", "T"), "T": ("L", "R", "D")}

def pool_path(n, rng):
    path = [rng.choice(NORMALS)]
    while len(path) < n:
        path.append(rng.choice(EDGES[path[-1]]))
    return path

def length_distribution(x, learning, root, maximum):
    return capped_distribution({n: math.exp(.4 * x * (n - 2.5)) *
                               learning.multiplier(f"{root}/length/{n}")
                               for n in range(1, maximum + 1)}, requested_cap=.55)

def branch_probability(x, last_result, learning, key):
    impact = {"hit": .45, "block": .1, "parry": -.55, "dodge": -.35,
              "perfect_dodge": -.45, "miss": -.35, "none": 0}.get(last_result, 0)
    # Only previous completed-battle evidence contributes to this learning term.
    log_odds = -.15 + .65 * x + impact + math.log(learning.multiplier(key))
    return clamp(sigmoid(log_odds), .15, .8)

def prepare_combo(move_id, context, learning, rng):
    m = MOVES[move_id]
    atoms = list(m.atoms)
    x = clamp(context.pressure / 100, -1, 1)
    choices = []
    if move_id == "M1-07":
        # Master first, then all committed disciples, last disciple blue.
        atoms = ["Q"] + ["D"] * (context.ready_disciples - 1) + ["B:D"]
    if move_id == "M2-01-C":
        n = choose(length_distribution(x, learning, move_id, 4), rng)
        atoms = pool_path(n, rng) + ["L", "R", "B:T"]
        choices.append(("prefix_length", n))
    elif move_id == "M2-01-E":
        n = choose(length_distribution(x, learning, move_id, 4), rng)
        atoms = pool_path(n, rng)
        choices.append(("plain_length", n))
    return atoms, choices


def decide_branch(move_id, x, learning, rng, last_result, can_followup=True):
    """Invoke once AFTER the branch-point beat settles, using only its outcome."""
    choices = []
    if move_id == "M2-05-F":
        probability = branch_probability(x, last_result, learning, "M2-05-F/blue")
        append = can_followup and rng.random() < probability
        choices.append(("blue_followup", append))
    if move_id.startswith("M2-01-") and move_id[-1] in "ABCD":
        # One optional ordinary break-point only; never after blue commitment.
        stop_p = clamp(.12 - .06 * x + (.18 if last_result in ("parry", "dodge", "perfect_dodge") else 0), .06, .36)
        stopped = rng.random() < stop_p
        choices.append(("early_stop", stopped))
    if move_id.startswith("M2-01-") and move_id[-1] in "ABCD":
        observe_p = clamp(.12 + .08 * x, .04, .2)
        choices.append(("observe", not dict(choices).get("early_stop", False) and rng.random() < observe_p))
    return choices


def combo(move_id, context, learning, rng, last_result="none", allow_branch=True):
    """Offline complete-path helper; live execution uses prepare/decide separately."""
    atoms, choices = prepare_combo(move_id, context, learning, rng)
    if allow_branch:
        choices += decide_branch(move_id, clamp(context.pressure / 100, -1, 1), learning, rng, last_result,
                                 can_followup=context.distance <= 1100 and context.los and context.master_ready)
    decisions = dict(choices)
    if decisions.get("blue_followup"):
        atoms.append("B:T")
    if decisions.get("early_stop"):
        atoms = atoms[:2]
    return atoms, choices

def atom_color(atom):
    return atom.split(":", 1)[0] if ":" in atom else "N"

def impact_offsets(move_id, atoms, choices=(), disciples=6, regroup=1.3):
    m = MOVES[move_id]
    t = m.windup + (regroup if m.disciples else 0)
    if move_id == "M1-03":
        t += .22 * max(0, disciples - 1)
    result = []
    for i, atom in enumerate(atoms):
        if i:
            t += .85 if atom_color(atom) != "N" else .50
        if i == 2 and dict(choices).get("observe"):
            t += .35
        result.append((t, atom_color(atom)))
    return result


def duration(move_id, atoms, choices=(), disciples=6, regroup=1.3):
    return impact_offsets(move_id, atoms, choices, disciples, regroup)[-1][0] + .18 + MOVES[move_id].recovery

class Calendar:
    """One global impact reservation calendar. Only cross-action conflicts are shifted."""
    def __init__(self):
        self.impacts = []

    def reserve(self, action_id, start, move_id, atoms, max_delay=1., delay_step=.05,
                choices=(), disciples=6, regroup=1.3):
        if any(x[2] == action_id for x in self.impacts):
            raise ValueError("duplicate action reservation")
        relative = impact_offsets(move_id, atoms, choices, disciples, regroup)
        return self._reserve(action_id, start, relative, max_delay, delay_step)

    def reserve_branches(self, action_id, start, move_id, planned_atoms, disciples=6, regroup=1.3):
        """Reserve the union of possible future timings before any telegraph begins."""
        if any(x[2] == action_id for x in self.impacts):
            raise ValueError("duplicate action reservation")
        atoms = list(planned_atoms)
        if move_id == "M2-05-F":
            atoms.append("B:T")
        relative = impact_offsets(move_id, atoms, disciples=disciples, regroup=regroup)
        if move_id.startswith("M2-01-") and move_id[-1] in "ABCD":
            relative += impact_offsets(move_id, atoms, [("observe", True)], disciples, regroup)
        return self._reserve(action_id, start, sorted(set(relative)), 1., .05)

    def _reserve(self, action_id, start, relative, max_delay, delay_step):
        for step in range(round(max_delay / delay_step) + 1):
            delay = step * delay_step
            proposed = [(start + delay + t, color, action_id) for t, color in relative]
            ok = all(abs(a[0] - b[0]) >= (.65 if a[1] != "N" or b[1] != "N" else .35) - 1e-9
                     for a in proposed for b in self.impacts if a[2] != b[2])
            if ok:
                self.impacts.extend(proposed)
                return delay
        return None

    def cancel(self, action_id):
        self.impacts = [x for x in self.impacts if x[2] != action_id]

    def prune(self, now):
        self.impacts = [x for x in self.impacts if x[0] >= now - 1]

class Leases:
    def __init__(self):
        self.held = {}

    def acquire(self, action_id, participants, expires, epoch):
        participants = set(participants)
        if not participants or action_id in self.held:
            return False
        if any(participants & x[0] for x in self.held.values()):
            return False
        self.held[action_id] = (participants, expires, epoch)
        return True

    def release(self, action_id):
        self.held.pop(action_id, None)

    def expire(self, now, epoch):
        self.held = {k: v for k, v in self.held.items() if v[1] > now and v[2] == epoch}

    def interrupt_member(self, actor):
        cancelled = [k for k, v in self.held.items() if actor in v[0]]
        for k in cancelled:
            self.release(k)
        return cancelled

@dataclass
class Fighter:
    qi_max: float = 100.
    qi: float = 100.
    broken_until: float = -1.
    broken_start: float = -1.
    ground_until: float = -1.
    knock_lock_until: float = -1.
    impacts: deque = field(default_factory=deque)
    break_duration: float = 4.

    def update(self, now):
        if self.broken_start >= 0:
            self.qi = self.qi_max * clamp((now - self.broken_start) / self.break_duration, 0., 1.)
            if now >= self.broken_until:
                self.qi = self.qi_max
                self.broken_start = -1

    def lose_qi(self, amount, now):
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("invalid qi damage")
        self.update(now)
        if self.broken_start >= 0:
            return False  # hits still damage HP but do not restart break recovery
        self.qi = max(0., self.qi - amount)
        if self.qi <= 0:
            self.broken_start = now
            self.broken_until = now + self.break_duration
            return True
        return False

    def impact(self, amount, now):
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("invalid impulse")
        while self.impacts and self.impacts[0][0] < now - 2:
            self.impacts.popleft()
        if now < self.knock_lock_until:
            return False
        self.impacts.append((now, amount))
        if sum(x[1] for x in self.impacts) >= 100:
            self.ground_until = now + 2.8
            self.knock_lock_until = self.ground_until + 3.
            self.impacts.clear()
            return True
        return False

    def state(self, now):
        self.update(now)
        if now < self.ground_until:
            return "ground"
        if self.broken_start >= 0:
            return "hanging_broken"
        return "ready"

@dataclass
class Encounter:
    phase: int = 1
    master_hp: float = 3000.
    master_max: float = 3000.
    red_hp: float = 1800.
    epoch: int = 0
    terminal: str = ""
    red_entered: bool = False
    red_heal_ready: float = 0.

    def damage_batch(self, master_damage, red_damage, now):
        if any(not math.isfinite(x) or x < 0 for x in (master_damage, red_damage)):
            raise ValueError("damage must be nonnegative finite")
        if self.terminal:
            return
        old = self.phase
        self.master_hp = max(0., self.master_hp - master_damage)
        if self.phase == 3:
            self.red_hp = max(0., self.red_hp - red_damage)
        # The half-HP latch fires even on lethal damage. There are no free HP,
        # damage immunity or delayed resurrection on arrival.
        if self.phase == 2 and not self.red_entered and self.master_hp <= self.master_max * .5:
            self.phase, self.red_entered = 3, True
        if self.master_hp <= 0:
            if self.phase == 1:
                self.phase, self.master_max, self.master_hp = 2, 4000., 4000.
            else:
                self.terminal = "both_dead" if self.phase == 3 and self.red_hp <= 0 else (
                    "red_suicide" if self.phase == 3 else "master_dead")
                if self.phase == 3:
                    self.red_hp = 0.
        elif self.phase == 3 and self.red_hp <= 0:
            self.phase = 4
        if self.phase != old or self.terminal:
            self.epoch += 1

    def red_heal(self, now):
        if (self.terminal or self.phase != 3 or self.master_hp <= 0 or
                self.master_hp >= .4 * self.master_max or self.red_hp <= .25 * 1800 or
                now < self.red_heal_ready):
            return 0.
        amount = min(300., self.master_max - self.master_hp, self.red_hp - 1.)
        self.red_hp -= amount
        self.master_hp += amount
        self.red_heal_ready = now + 20.
        return amount

@dataclass
class HealthServices:
    master: float = 3000.
    maximum: float = 3000.
    disciples: list = field(default_factory=lambda: [350.] * 6)
    drain_ready: float = 0.
    summon_ready: float = 0.

    def perform(self, now):
        if self.master <= 0:
            return None
        alive = sum(h > 0 for h in self.disciples)
        # New minion HP is capped by 80% of the paid cost: no HP generator,
        # without adding a summon-count limit that contradicts the user's rule.
        if alive < 3 and self.master > self.maximum / 3 and now >= self.summon_ready:
            need = 3 - alive
            per = min(350., .8 * (self.maximum / 3) / need)
            self.master -= self.maximum / 3
            remaining = need
            for i, hp in enumerate(self.disciples):
                if hp <= 0 and remaining:
                    self.disciples[i] = per
                    remaining -= 1
            self.summon_ready = now + 18.
            self.drain_ready = max(self.drain_ready, now + 3.)
            return "summon"
        if self.master < .75 * self.maximum and now >= self.drain_ready:
            target = max(range(len(self.disciples)), key=lambda i: self.disciples[i])
            amount = min(.15 * self.maximum, self.maximum - self.master, max(0., self.disciples[target] - 1.))
            if amount > 0:
                self.master += amount
                self.disciples[target] -= amount
                self.drain_ready = now + 12.
                return "drain"
        return None

    def energy(self):
        return self.master + sum(self.disciples)
