"""Reproducible tests and synthetic simulations; not a substitute for UE playtests."""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import csv
import io
import json
import math
import random
import statistics
import unittest

from catalog import MOVES, ALIASES, export
from policy import (Pressure, Learning, Evidence, Context, Selector, Calendar, Leases,
                    Fighter, Encounter, HealthServices, capped_distribution, choose,
                    combo, prepare_combo, decide_branch, duration, impact_offsets,
                    atom_color, branch_probability, offense_probability, RESPONSE_SCORE)

HERE = Path(__file__).resolve().parent


class Invariants(unittest.TestCase):
    def memory(self):
        m = Learning()
        m.begin("test")
        return m

    def test_probability_caps(self):
        for n in range(1, 40):
            d = capped_distribution({str(i): 10. ** (i % 20) for i in range(n)})
            self.assertAlmostEqual(sum(d.values()), 1)
            self.assertGreater(min(d.values()), 0)
            self.assertLessEqual(max(d.values()), (1 if n == 1 else .65 if n == 2 else .45) + 1e-12)
        self.assertEqual(capped_distribution({}), {})
        for x in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                capped_distribution({"bad": x})

    def test_distribution_boundaries(self):
        s = Selector(self.memory())
        reached = set()
        for phase in (1, 2, 3, 4):
            for d in (0, 230, 450, 450.0001, 600, 1100, 1800, 2000, 2000.001):
                for count in range(7):
                    c = Context(phase=phase, distance=d, ready_disciples=count)
                    p = s.distribution(c)
                    if p:
                        self.assertAlmostEqual(sum(p.values()), 1)
                    for key in p:
                        reached.add(key)
                        self.assertTrue(s.eligible(MOVES[key], c))
                        self.assertGreaterEqual(count, MOVES[key].disciples)
                        if phase in (2, 3, 4):
                            self.assertFalse("M2-05-N" in p and "M2-05-F" in p)
        reached |= set(s.distribution(Context(phase=1), "wave"))
        self.assertEqual(reached, set(MOVES))
        self.assertEqual(s.distribution(Context(los=False)), {})

    def test_separate_actor_ranges(self):
        p = Selector(self.memory()).distribution(Context(phase=3, distance=300, red_distance=2100))
        self.assertTrue(p)
        self.assertTrue(all(MOVES[k].owner == "M" for k in p))

    def test_cooldown_and_repeat(self):
        s, c = Selector(self.memory()), Context(distance=400)
        s.commit("M2-05-N", c, s.distribution(c))
        c.distance, c.now = 800, 7.999
        self.assertNotIn("M2-05-F", s.distribution(c))
        c.now = 8
        self.assertIn("M2-05-F", s.distribution(c))
        s.history.clear()
        s.history.extend(["M2-01-A", "M2-01-B"])
        self.assertTrue(all(not MOVES[k].danger for k in s.distribution(c)))
        s.history.clear()
        s.history.extend(["M2-01-E", "M2-01-E"])
        self.assertNotIn("M2-01-E", s.distribution(c))
        self.assertEqual(ALIASES["M1-06"], "M1-04")

    def test_master_stunned_disciples_still_attack(self):
        s = Selector(self.memory())
        p = s.distribution(Context(phase=1, distance=180, master_ready=False, ready_disciples=2))
        self.assertTrue(p)
        self.assertTrue(all(MOVES[k].owner == "G" for k in p))
        self.assertFalse(s.distribution(Context(phase=1, master_ready=False, ready_disciples=0)))

    def test_pressure_precedence_caps_and_dedup(self):
        p = Pressure()
        self.assertEqual(p.apply(1, ["hit", "break", "grab"], 0), 45)
        self.assertEqual(p.apply(1, ["hit"], 0), 0)
        self.assertEqual(p.apply(2, ["hit"], 0), 15)
        self.assertEqual(p.apply(3, ["hit"], 0), 0)
        self.assertEqual(p.apply(4, ["parry"], 0), -12)
        self.assertEqual(p.apply(5, ["parry"], 0), -12)
        self.assertEqual(p.apply(6, ["parry"], 0), -6)
        self.assertEqual(p.value, 30)
        p.advance(12)
        self.assertAlmostEqual(p.value, 15)
        with self.assertRaises(ValueError):
            p.advance(1)

    def test_pressure_does_not_use_memory_or_spam(self):
        a, b = Pressure(), Pressure()
        memory = self.memory()
        memory.saved["M2-01-A"] = Evidence(0, 40)
        for i in range(100):
            a.apply(i, ["parry" if i % 3 else "hit"], i * .3)
            b.apply(i, ["parry" if i % 3 else "hit"], i * .3)
        self.assertEqual(a.value, b.value)
        p = Pressure()
        for i in range(1000):
            p.apply(i, ["button_press"], 0)
        self.assertEqual(p.value, 0)
        self.assertEqual(Pressure().value, 0)

    def test_learning_frozen_bounded_and_once(self):
        m = self.memory()
        for i in range(100):
            m.sample(i, "a", 0)
        self.assertEqual(m.multiplier("a"), 1)
        self.assertTrue(m.finish("defeat"))
        self.assertFalse(m.finish("defeat"))
        self.assertEqual(m.saved["a"].failure, 6)
        m.begin("next")
        self.assertGreater(m.multiplier("a"), 1)
        self.assertEqual(m.multiplier("unseen"), 1)
        m.finish("abort")
        for battle in range(100):
            m.begin(f"b{battle}")
            for i in range(100):
                m.sample(i, "a", 0)
            m.finish("defeat")
        self.assertLessEqual(m.saved["a"].failure, 40 + 1e-10)
        m.begin("last")
        self.assertLessEqual(m.multiplier("a"), math.exp(1.2))

    def test_learning_abort_and_eligibility(self):
        m = self.memory()
        m.sample("x", "a", 0, eligible=False)
        m.sample("x", "a", 1)
        m.sample("x", "a", 0)
        self.assertEqual(m.pending["a"], [1])
        m.finish("abort")
        self.assertFalse(m.saved)

    def test_combo_structure_and_branches(self):
        m, rng = self.memory(), random.Random(319)
        for pressure in (-100, 0, 100):
            for move in MOVES.values():
                for count in (2, 3, 6):
                    c = Context(phase=move.phases[0], pressure=pressure, ready_disciples=count)
                    for _ in range(60):
                        atoms, choices = combo(move.id, c, m, rng, rng.choice(["hit", "parry", "miss"]))
                        self.assertGreaterEqual(len(atoms), 1)
                        self.assertLessEqual(len(atoms), 7)
                        self.assertGreater(duration(move.id, atoms, choices, count), 0)
                        if move.owner != "R":
                            self.assertTrue(all(atom_color(a) != "K" for a in atoms))
                        if move.id.startswith("M2-01"):
                            for i, atom in enumerate(atoms):
                                if atom_color(atom) == "B":
                                    self.assertEqual((i, atom), (len(atoms) - 1, "B:T"))
                        if move.id == "M2-05-N":
                            self.assertEqual(atoms, ["R:SPRAY"])
                        if move.id == "M4-01":
                            self.assertEqual(len(atoms), 6)
                            self.assertEqual(atoms[-1], "B:D")
                        if move.id == "M1-07":
                            self.assertEqual(len(atoms), count + 1)
                            self.assertEqual(atoms[-1], "B:D")

    def test_branch_responds_to_completed_outcomes(self):
        m = self.memory()
        self.assertGreater(branch_probability(0, "hit", m, "a"), branch_probability(0, "parry", m, "a"))
        for x in (-1, 0, 1):
            for outcome in ("hit", "parry", "miss"):
                self.assertTrue(.15 <= branch_probability(x, outcome, m, "a") <= .8)

    def test_calendar_matches_duration(self):
        m = self.memory()
        for key in MOVES:
            atoms, choices = combo(key, Context(), m, random.Random(42))
            cal = Calendar()
            self.assertEqual(cal.reserve("x", 10, key, atoms, choices=choices), 0)
            self.assertAlmostEqual(max(t for t, _, _ in cal.impacts) + .18 + MOVES[key].recovery,
                                   10 + duration(key, atoms, choices))
            with self.assertRaises(ValueError):
                cal.reserve("x", 10, key, atoms)

    def test_far_spray_followup_rechecks_range(self):
        m, rng = self.memory(), random.Random(20)
        for d in (1100.0001, 1800):
            for _ in range(100):
                atoms, _ = combo("M2-05-F", Context(distance=d, pressure=100), m, rng, "hit")
                self.assertEqual(atoms, ["SPRAY"])
        results = [combo("M2-05-F", Context(distance=1100), m, rng, "hit")[0] for _ in range(100)]
        self.assertTrue(any("B:T" in atoms for atoms in results))

    def test_calendar_cancellation_and_spacing(self):
        cal = Calendar()
        self.assertEqual(cal.reserve("a", 0, "M2-01-F", ["B:T"]), 0)
        delay = cal.reserve("b", 0, "R-01", ["L", "R", "D"])
        self.assertIsNotNone(delay)
        self.assertLessEqual(delay, 1)
        for a in cal.impacts:
            for b in cal.impacts:
                if a[2] != b[2]:
                    self.assertGreaterEqual(abs(a[0] - b[0]) + 1e-9,
                                            .65 if a[1] != "N" or b[1] != "N" else .35)
        cal.cancel("a")
        self.assertTrue(all(x[2] != "a" for x in cal.impacts))
        cal.prune(20)
        self.assertFalse(cal.impacts)

    def test_future_branch_envelope(self):
        cal = Calendar()
        self.assertEqual(cal.reserve_branches("a", 0, "M2-05-F", ["SPRAY"]), 0)
        self.assertTrue(any(color == "B" for _, color, _ in cal.impacts))
        before = list(cal.impacts)
        cal.reserve("b", 0, "R-01", ["L", "R", "D"])
        for a in before:
            for b in cal.impacts:
                if a[2] != b[2]:
                    self.assertGreaterEqual(abs(a[0] - b[0]) + 1e-9, .65 if a[1] != "N" else .35)
        cal = Calendar()
        atoms = ["L", "R", "B:T"]
        cal.reserve_branches("c", 0, "M2-01-B", atoms)
        for choices in ([], [("observe", True)]):
            for t, color in impact_offsets("M2-01-B", atoms, choices):
                self.assertIn((t, color, "c"), cal.impacts)

    def test_phase_change_does_not_reset_inherited_cooldowns(self):
        s, c = Selector(self.memory()), Context(phase=2, distance=300)
        s.commit("M2-01-A", c, s.distribution(c))
        s.phase_changed()
        c.phase, c.now = 3, 1
        self.assertNotIn("M2-01-A", s.distribution(c))
        self.assertFalse(s.history)

    def test_lease_atomicity_interrupt_epoch(self):
        l = Leases()
        self.assertTrue(l.acquire("a", ["m", "d1", "d2"], 8, 0))
        self.assertFalse(l.acquire("a", ["d4"], 8, 0))
        self.assertFalse(l.acquire("b", ["d2", "d3"], 8, 0))
        self.assertEqual(l.interrupt_member("detached"), [])
        self.assertEqual(l.interrupt_member("d1"), ["a"])
        self.assertTrue(l.acquire("b", ["d2", "d3"], 8, 0))
        l.expire(1, 1)
        self.assertFalse(l.held)
        l.acquire("c", ["m"], 8, 1)
        l.expire(8, 1)
        self.assertFalse(l.held)

    def test_no_natural_qi_recovery(self):
        f = Fighter()
        f.lose_qi(40, 0)
        f.update(100)
        self.assertEqual(f.qi, 60)
        f.lose_qi(60, 101)
        f.update(103)
        self.assertEqual(f.qi, 50)
        self.assertEqual(f.state(103), "hanging_broken")
        f.lose_qi(50, 103)
        self.assertEqual(f.broken_until, 105)
        self.assertEqual(f.state(105), "ready")
        self.assertEqual(f.qi, 100)

    def test_ground_and_break_independent(self):
        f = Fighter()
        f.lose_qi(100, 0)
        self.assertTrue(f.impact(100, .2))
        self.assertEqual(f.state(1), "ground")
        self.assertEqual(f.state(3.1), "hanging_broken")
        self.assertEqual(f.state(4), "ready")
        self.assertFalse(f.impact(100, 5))
        self.assertTrue(f.impact(100, 6.1))

    def test_phase_transactions(self):
        e = Encounter()
        e.damage_batch(9999, 9999, 0)
        self.assertEqual((e.phase, e.master_hp, e.red_hp), (2, 4000, 1800))
        e.damage_batch(2000, 0, 1)
        self.assertEqual(e.phase, 3)
        e.master_hp += 500
        e.damage_batch(0, 0, 2)
        self.assertEqual(e.phase, 3)
        e.damage_batch(0, 1800, 3)
        self.assertEqual(e.phase, 4)
        e.damage_batch(9999, 0, 4)
        self.assertEqual(e.terminal, "master_dead")
        epoch = e.epoch
        e.damage_batch(9999, 9999, 5)
        self.assertEqual(e.epoch, epoch)

    def test_lethal_threshold_and_simultaneous_death(self):
        e = Encounter(phase=2, master_hp=4000, master_max=4000)
        e.damage_batch(5000, 0, 1)
        self.assertTrue(e.red_entered)
        self.assertEqual(e.terminal, "red_suicide")
        e = Encounter(phase=3, master_hp=10, red_hp=10)
        e.damage_batch(10, 10, 0)
        self.assertEqual(e.terminal, "both_dead")

    def test_red_heal_conservation(self):
        e = Encounter(phase=3, master_hp=1000, master_max=4000)
        total = e.master_hp + e.red_hp
        self.assertEqual(e.red_heal(0), 300)
        self.assertEqual(e.master_hp + e.red_hp, total)
        self.assertEqual(e.red_heal(19.9), 0)
        e.damage_batch(9999, 0, 20)
        self.assertEqual(e.red_heal(20), 0)

    def test_health_thresholds_and_target(self):
        h = HealthServices(master=1000, disciples=[0.] * 6)
        self.assertIsNone(h.perform(0))
        h.master = 1000.001
        self.assertEqual(h.perform(0), "summon")
        self.assertEqual(sum(x > 0 for x in h.disciples), 3)
        self.assertAlmostEqual(sum(h.disciples), 800)
        h = HealthServices(master=2250)
        self.assertIsNone(h.perform(0))
        h.master = 2249
        h.disciples = [100, 500, 30, 0, 0, 0]
        energy = h.energy()
        self.assertEqual(h.perform(0), "drain")
        self.assertEqual(h.disciples[1], 50)
        self.assertEqual(h.energy(), energy)
        h.master = 0
        self.assertIsNone(h.perform(20))

    def test_health_service_no_energy_loop(self):
        rng = random.Random(972)
        h = HealthServices()
        previous, summons = h.energy(), 0
        for i in range(10000):
            h.master = max(0., h.master - rng.random() * 10)
            j = rng.randrange(6)
            h.disciples[j] = max(0., h.disciples[j] - rng.random() * 120)
            before = h.energy()
            action = h.perform(i * .25)
            self.assertLessEqual(h.energy(), previous + 1e-9)
            if action == "summon":
                summons += 1
                self.assertGreaterEqual(before - h.energy(), 200 - 1e-9)
            previous = h.energy()
        self.assertLessEqual(summons, 25)

    def test_attack_fallback_finite(self):
        self.assertEqual(offense_probability(-100, 3), 1)
        self.assertAlmostEqual(offense_probability(100, 0), .88)
        self.assertAlmostEqual(offense_probability(-100, 0), .52)
        self.assertEqual(Selector(self.memory()).distribution(Context(distance=99999)), {})


PROFILES = {
    "novice": {"N": .3, "B": .25, "R": .25, "K": .2, "attacks": 1, "accuracy": .55},
    "expert": {"N": .9, "B": .9, "R": .9, "K": .85, "attacks": 2, "accuracy": .9},
    "blue_weak": {"N": .8, "B": .2, "R": .8, "K": .8, "attacks": 1, "accuracy": .8},
    "red_weak": {"N": .8, "B": .8, "R": .2, "K": .8, "attacks": 1, "accuracy": .8},
    "aggressive": {"N": .55, "B": .55, "R": .55, "K": .5, "attacks": 4, "accuracy": .8},
    "passive": {"N": .6, "B": .6, "R": .6, "K": .6, "attacks": 0, "accuracy": 0},
}


def response(profile, atom, rng):
    color = atom_color(atom)
    if rng.random() < profile[color]:
        return "parry" if color in ("N", "B") else "perfect_dodge"
    if color == "N" and rng.random() < .4:
        return "block"
    return "grab" if color == "K" else "hit"


def synthetic_attempt(phase, profile, seed, memory=None, battle_id=None, horizon=180.):
    rng = random.Random(seed)
    memory = memory or Learning()
    memory.begin(battle_id or f"s{seed}")
    selector, pressure = Selector(memory), Pressure()
    now, last_offense = 0., -3.
    counts, events = Counter(), 0
    pressure_samples, blue_followups = [], 0
    fallbacks, interruptions, cycles, max_length = 0, 0, 0, 0
    total_beats, completed_actions, empty_fallbacks = 0, 0, 0
    history = []
    while now < horizon:
        cycles += 1
        if cycles > 2000:
            raise AssertionError("watchdog: zero-time loop")
        pressure.advance(now)
        c = Context(phase=phase, distance=rng.choice([180., 350., 600., 1000., 1600.]),
                    now=now, pressure=pressure.value,
                    ready_disciples=rng.choice([1, 2, 3, 4, 5, 6]) if phase == 1 else 0)
        dist = selector.distribution(c)
        if not dist or rng.random() >= offense_probability(c.pressure, now - last_offense):
            fallbacks += 1
            empty_fallbacks += not bool(dist)
            now += .75
            continue
        key = choose(dist, rng)
        assert selector.eligible(MOVES[key], c)
        assert not (len(history) >= 2 and history[-2:] == [key, key])
        assert not (MOVES[key].danger and len(history) >= 2 and all(MOVES[k].danger for k in history[-2:]))
        selector.commit(key, c, dist)
        history.append(key)
        last_offense = now
        atoms, choices = prepare_combo(key, c, memory, rng)
        root = f"{battle_id or seed}/{cycles}"
        if rng.random() < .08:
            # Player-caused interrupt. Attack cooldown is already spent.
            interruptions += 1
            now += .4
            pressure.apply((root, "interrupt"), ["attack_hit"], now)
            memory.sample((root, "root"), key, 1.)
            counts[key] += 1
            continue
        scores = []
        t = impact_offsets(key, atoms, choices, c.ready_disciples)[0][0] + now
        i = 0
        while i < len(atoms):
            # Synthetic player's completed attack events, not raw button presses.
            for j in range(profile["attacks"]):
                outcome = "attack_hit" if rng.random() < profile["accuracy"] else "attack_miss"
                pressure.apply((root, i, "player", j), [outcome], t)
                events += 1
            outcome = response(profile, atoms[i], rng)
            pressure.apply((root, i, "boss"), [outcome], t)
            events += 1
            scores.append(RESPONSE_SCORE[outcome])
            pressure_samples.append(pressure.value)
            at_branch = (key == "M2-05-F" and i == 0) or (
                key.startswith("M2-01-") and key[-1] in "ABCD" and i == 1)
            if at_branch:
                decisions = decide_branch(key, pressure.value / 100, memory, rng, outcome,
                                          can_followup=c.distance <= 1100 and c.los and c.master_ready)
                choices += decisions
                decisions = dict(decisions)
                if decisions.get("blue_followup"):
                    atoms.append("B:T")
                    blue_followups += 1
                if decisions.get("early_stop"):
                    atoms = atoms[:2]
                if decisions.get("observe"):
                    t += .35
            if i + 1 < len(atoms):
                t += .85 if atom_color(atoms[i + 1]) != "N" else .5
            i += 1
        assert 1 <= len(atoms) <= 7
        max_length = max(max_length, len(atoms))
        total_beats += len(atoms)
        completed_actions += 1
        memory.sample((root, "root"), key, statistics.mean(scores))
        if dict(choices).get("blue_followup"):
            memory.sample((root, "blue"), "M2-05-F/blue", scores[-1])
        for choice, length in choices:
            if choice in ("prefix_length", "plain_length") and len(scores) >= length:
                memory.sample((root, "length"), f"{key}/length/{length}", statistics.mean(scores[:length]))
        now = t + .18 + MOVES[key].recovery + .2
        counts[key] += 1
    memory.finish("defeat")  # Fixed-horizon completed-attempt harness, not simulated player HP.
    return {"phase": phase, "seed": seed, "seconds": now, "decisions": cycles,
            "attacks": sum(counts.values()), "events": events, "fallbacks": fallbacks,
            "interruptions": interruptions, "max_combo_beats": max_length,
            "mean_combo_beats": total_beats / max(1, completed_actions),
            "empty_fallbacks": empty_fallbacks,
            "saturated_positive_fraction": sum(p >= 99.999 for p in pressure_samples) / max(1, len(pressure_samples)),
            "saturated_negative_fraction": sum(p <= -99.999 for p in pressure_samples) / max(1, len(pressure_samples)),
            "blue_followups": blue_followups,
            "mean_pressure": statistics.mean(pressure_samples) if pressure_samples else 0,
            "danger_fraction": sum(n for k, n in counts.items() if MOVES[k].danger) / max(1, sum(counts.values())),
            "counts": dict(counts)}


def fuzz_probabilities(n=100000):
    rng, memory = random.Random(20261112), Learning()
    memory.begin("fuzz")
    s, reached, nonempty = Selector(memory), set(), 0
    for i in range(n):
        c = Context(phase=rng.randrange(1, 5), distance=rng.uniform(0, 2300), now=i * .3,
                    pressure=rng.uniform(-100, 100), ready_disciples=rng.randrange(7),
                    master_ready=rng.random() > .1, red_ready=rng.random() > .1,
                    red_alive=rng.random() > .1, los=rng.random() > .1,
                    red_distance=rng.uniform(0, 2300),
                    low_player_qi=rng.random() < .3, punish_window=rng.random() < .3)
        dist = s.distribution(c, "wave" if i % 10 == 0 else "primary")
        if not dist:
            continue
        nonempty += 1
        assert abs(sum(dist.values()) - 1) < 1e-10
        assert all(v > 0 and math.isfinite(v) for v in dist.values())
        cap = 1 if len(dist) == 1 else .65 if len(dist) == 2 else .45
        assert max(dist.values()) <= cap + 1e-10
        key = choose(dist, rng)
        reached.add(key)
        s.commit(key, c, dist)
    assert reached == set(MOVES)
    return {"contexts": n, "nonempty": nonempty, "moves_reached": len(reached), "violations": 0}


def frequency_check(n=200000):
    m = Learning()
    m.begin("frequency")
    dist = Selector(m).distribution(Context(phase=3, distance=350, pressure=50))
    rng, counts = random.Random(1701), Counter()
    for _ in range(n):
        counts[choose(dist, rng)] += 1
    rows = []
    for key, probability in dist.items():
        error = abs(counts[key] / n - probability)
        bound = 6 * math.sqrt(probability * (1 - probability) / n) + 1 / n
        assert error < bound
        rows.append({"move": key, "expected": probability, "observed": counts[key] / n,
                     "error": error, "six_sigma_bound": bound})
    return {"draws": n, "max_absolute_error": max(x["error"] for x in rows), "rows": rows}


def calendar_stress(n=10000):
    rng, cal, mem = random.Random(783), Calendar(), Learning()
    mem.begin("calendar")
    accepted, rejected, delayed = 0, 0, 0
    keys = [k for k, m in MOVES.items() if 3 in m.phases]
    for i in range(n):
        now = i * .15
        cal.prune(now)
        key = rng.choice(keys)
        atoms, choices = combo(key, Context(phase=3), mem, rng)
        delay = cal.reserve(str(i), now, key, atoms, choices=choices)
        if delay is None:
            rejected += 1
        else:
            accepted += 1
            delayed += delay > 0
        if i % 7 == 0:
            cal.cancel(str(i))
        for a in cal.impacts:
            for b in cal.impacts:
                if a[2] != b[2]:
                    assert abs(a[0] - b[0]) + 1e-9 >= (.65 if a[1] != "N" or b[1] != "N" else .35)
    return {"requests": n, "accepted": accepted, "rejected": rejected, "delayed": delayed, "conflicts": 0}


def joint_scheduler_stress(n=20000):
    rng, cal, leases, mem = random.Random(8201), Calendar(), Leases(), Learning()
    mem.begin("joint")
    epoch, accepted, rejected, cancelled, epoch_clears = 0, 0, 0, 0, 0
    keys = [k for k, m in MOVES.items() if 3 in m.phases]
    for i in range(n):
        now = i * .1
        if i and i % 251 == 0:
            epoch += 1
            cal.impacts.clear()
            epoch_clears += 1
        old = set(leases.held)
        leases.expire(now, epoch)
        for key in old - set(leases.held):
            cal.cancel(key)
        cal.prune(now)
        if i % 17 == 0:
            for action in leases.interrupt_member(rng.choice(["master", "red"])):
                cal.cancel(action)
                cancelled += 1
        key = rng.choice(keys)
        actors = ["master", "red"] if MOVES[key].owner == "D" else ["red"] if MOVES[key].owner == "R" else ["master"]
        atoms, choices = prepare_combo(key, Context(phase=3), mem, rng)
        action = str(i)
        delay = cal.reserve_branches(action, now, key, atoms)
        longest = atoms + (["B:T"] if key == "M2-05-F" else [])
        bound = duration(key, longest, [("observe", True)]) + 1.
        if delay is None or not leases.acquire(action, actors, now + bound + (delay or 0), epoch):
            cal.cancel(action)  # Atomic rollback; no orphan reservation on lock failure.
            rejected += 1
        else:
            accepted += 1
        for a, (participants, _, _) in leases.held.items():
            for b, (other, _, _) in leases.held.items():
                assert a == b or not participants.intersection(other)
        assert all(action in leases.held for _, _, action in cal.impacts)
        for a in cal.impacts:
            for b in cal.impacts:
                if a[2] != b[2]:
                    assert abs(a[0] - b[0]) + 1e-9 >= (.65 if a[1] != "N" or b[1] != "N" else .35)
    leases.expire(now + 100, epoch + 1)
    cal.prune(now + 100)
    assert not leases.held and not cal.impacts
    return {"requests": n, "accepted": accepted, "rejected": rejected, "cancelled": cancelled,
            "epoch_clears": epoch_clears, "overlaps": 0, "orphan_reservations": 0, "leaked_locks": 0}


def sensitivity():
    rows = []
    for phase in (1, 2, 3, 4):
        for distance in (180, 350, 800, 1400):
            for pressure in (-80, 0, 80):
                for mode in ("neutral", "blue_weak", "red_weak", "mastered"):
                    mem = Learning()
                    if mode != "neutral":
                        for key, move in MOVES.items():
                            blue = any(a.startswith("B:") for a in move.atoms) or key in ("M1-07", "M2-01-C")
                            red = any(a.startswith("R:") for a in move.atoms)
                            weak = (mode == "blue_weak" and blue) or (mode == "red_weak" and red)
                            mem.saved[key] = Evidence(4 if weak else 32, 36 if weak else 8)
                    mem.begin("view")
                    dist = Selector(mem).distribution(Context(phase=phase, distance=distance, pressure=pressure))
                    for key, rate in dist.items():
                        rows.append({"phase": phase, "distance": distance, "pressure": pressure,
                                     "memory": mode, "move": key, "conditional_probability": rate,
                                     "decision_probability": offense_probability(pressure, 0) * rate})
    return rows


def write_csv(name, rows):
    with (HERE / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Invariants))
    (HERE / "test_results.txt").write_text(stream.getvalue(), encoding="utf-8")
    print(stream.getvalue())
    if not result.wasSuccessful():
        raise SystemExit(1)
    export(HERE / "move_catalog.json")
    fuzz, frequency, calendar = fuzz_probabilities(), frequency_check(), calendar_stress()
    joint = joint_scheduler_stress()
    attempts, aggregate = [], []
    for phase in (1, 2, 3, 4):
        for index, (name, profile) in enumerate(PROFILES.items()):
            group = [synthetic_attempt(phase, profile, phase * 100000 + index * 1000 + seed)
                     for seed in range(48)]
            for attempt in group:
                attempt["profile"] = name
            attempts.extend(group)
            aggregate.append({"phase": phase, "profile": name, "attempts": len(group),
                              "attacks": sum(x["attacks"] for x in group),
                              "mean_pressure": statistics.mean(x["mean_pressure"] for x in group),
                              "danger_fraction": statistics.mean(x["danger_fraction"] for x in group),
                              "mean_combo_beats": statistics.mean(x["mean_combo_beats"] for x in group),
                              "saturated_positive_fraction": statistics.mean(x["saturated_positive_fraction"] for x in group),
                              "max_combo_beats": max(x["max_combo_beats"] for x in group)})
    longitudinal = []
    for index, name in enumerate(("expert", "blue_weak", "red_weak")):
        mem = Learning()
        for battle in range(30):
            row = synthetic_attempt(3, PROFILES[name], 800000 + index * 1000 + battle, mem, f"{name}/{battle}")
            row["profile"], row["battle"] = name, battle + 1
            row["blue_multiplier_next"] = None
            mem.begin(f"probe/{battle}")
            row["blue_multiplier_next"] = mem.multiplier("M2-01-F")
            row["red_multiplier_next"] = mem.multiplier("R-04")
            mem.finish("abort")
            longitudinal.append(row)
    report = {"version": "boss-policy-1.0", "seed": 20261112,
              "unit_tests": result.testsRun, "unit_failures": len(result.failures) + len(result.errors),
              "fuzz": fuzz, "frequency": frequency, "calendar": calendar,
              "joint_scheduler": joint,
              "fixed_phase_attempts": len(attempts), "longitudinal_attempts": len(longitudinal),
              "total_decisions": sum(x["decisions"] for x in attempts + longitudinal),
              "total_attacks": sum(x["attacks"] for x in attempts + longitudinal),
              "total_events": sum(x["events"] for x in attempts + longitudinal),
              "max_combo_beats": max(x["max_combo_beats"] for x in attempts + longitudinal),
              "aggregate": aggregate, "longitudinal": longitudinal,
              "synthetic_attempts": attempts,
              "limitations": ["synthetic player policies", "fixed-phase sessions; transitions unit-tested separately",
                              "no Unreal, animation, collision, network or real player validation",
                              "calendar tested separately from session choice harness"]}
    (HERE / "simulation_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv("scenario_summary.csv", aggregate)
    write_csv("probability_scenarios.csv", sensitivity())
    write_csv("frequency_check.csv", frequency["rows"])
    print(json.dumps({k: v for k, v in report.items() if k not in ("aggregate", "longitudinal", "synthetic_attempts", "frequency")}, indent=2))


if __name__ == "__main__":
    run()
