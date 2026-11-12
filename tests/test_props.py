"""GoF3's other ships: the converter finding odd hulls and their light maps (tools/structures.py body_nodes, light_map), the
UFOs' turrets (tools/gof3_props.py), the missions spawning UFOs and bombers (tools/gof3_missions.py) and the capital ships'
table (tools/capitals.py)."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
try:
    import structures, gof3_props, gof3_missions, capitals
except ImportError as e:   # (numpy, Pillow, texture2ddecoder)
    structures = None
    why = str(e)


class _R:
    class p: recs = []
    def name(self, r): return None
    def fields(self, r): return {}


class _D:   # no GoF3 data: every text its fallback
    R = _R()


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').close()


def _walk(steps):
    for s in steps:
        yield s
        for k in ('steps', 'then', 'else'):
            if isinstance(s.get(k), list): yield from _walk(s[k])


@unittest.skipIf(structures is None, 'the converter needs numpy, Pillow and texture2ddecoder')
class BodyAndLightTests(unittest.TestCase):
    def test_body_nodes(self):
        with tempfile.TemporaryDirectory() as d:
            scene = {0: {'name': 'terran_ufo_000_lod_000_body'}, 1: {'name': 'terran_ufo_000_lod_001_body'}, 2: {'name': 'x_helper'}}
            for n in ('terran_ufo_000_lod_000_body', 'terran_ufo_000_lod_001_body'): _touch(f'{d}/{n}.ae4meshgroup')
            self.assertEqual(('terran_ufo_000_lod_000_body', []), structures.body_nodes(scene, d, 'structure_terran_ufo_000'),
                             'a hull without "structure_" in its name')
        with tempfile.TemporaryDirectory() as d:
            n = 'structure_nivelian_largeship_003_lod_000_body_part0'
            scene = {i: {'name': n + str(i)} for i in (3, 1, 4, 2)}
            for i in (1, 2, 3, 4): _touch(f'{d}/{n}{i}.ae4meshgroup')
            self.assertEqual((n + '1', [n + '2', n + '3', n + '4']), structures.body_nodes(scene, d, 'x'), 'a hull in parts')
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual((None, []), structures.body_nodes({0: {'name': 'a_lod_000_body'}}, d, 'a'),
                             'only nodes with a meshgroup beside the scene')

    def test_light_map(self):
        with tempfile.TemporaryDirectory() as d:
            multi, helios = f'{d}/materials/multi', f'{d}/textures/textures_helios'
            _touch(f'{multi}/structure_terran_largeship_000_light_ao.tga.ae4texture')
            _touch(f'{helios}/structure_terran_largeship_004_light_ao.tga.ae4texture')
            _touch(f'{multi}/structure_terran_bomber_000_lod_light_ao.tga.ae4texture')
            said = []
            lm = lambda names, light=None: structures.light_map(d, names, 'terran', light, said.append)
            self.assertEqual(f'{multi}/structure_terran_largeship_000_light_ao.tga.ae4texture', lm(['structure_terran_largeship_000']))
            self.assertEqual(f'{helios}/structure_terran_largeship_004_light_ao.tga.ae4texture', lm(['structure_terran_largeship_004']),
                             'in another folder of the race')
            self.assertEqual(f'{multi}/structure_terran_bomber_000_lod_light_ao.tga.ae4texture', lm(['structure_terran_bomber_000']),
                             'its _lod one when that is all there is')
            self.assertEqual(f'{multi}/structure_terran_largeship_000_light_ao.tga.ae4texture',
                             lm(['structures_terran_x', 'structure_terran_largeship_000']), 'the next name')
            self.assertEqual([], said)
            self.assertEqual(f'{multi}/structure_terran_default_light_ao.tga.ae4texture', lm(['structure_terran_largeship_006']))
            self.assertEqual(1, len(said), 'the default is said')
            self.assertEqual('given.tga', lm(['structure_terran_largeship_006'], 'given.tga'), 'an explicit one wins')


@unittest.skipIf(structures is None, 'gof3_props needs numpy')
class PropsTests(unittest.TestCase):
    def test_turret_mounts(self):
        info = {'min': [-10, -4, -10], 'max': [10, 6, 10],
                'helpers': {'u_turret_000': ([0, 6, 1], 1.0, [0, 1, 0]), 'u_turret_001': ([0, -4, 1], 1.0, [0, -1, 0]),
                            'u_engine_000': ([0, 0, 9], 1.0)}}
        m = gof3_props.turret_mounts(info, 0.5)
        self.assertEqual(2, len(m))
        self.assertTrue(all(x['slotType'] == 2 for x in m))
        self.assertNotIn('upsideDown', m[0]); self.assertTrue(m[1]['upsideDown'], 'the one below hangs')
        self.assertEqual(capitals.game([0, 6, 1], 0.5), m[0]['position_engine'], 'at the capped model\'s scale')
        m = gof3_props.turret_mounts({'min': [-10, -4, -10], 'max': [10, 6, 10], 'helpers': {}}, 1.0)
        self.assertEqual([capitals.game([0, 6, 0]), capitals.game([0, -4, 0])], [x['position_engine'] for x in m],
                         'without helpers (the Terran UFO): top and bottom of the middle')
        self.assertTrue(m[1]['upsideDown'])


@unittest.skipIf(structures is None, 'gof3_missions imports gof3_props')
class MissionTests(unittest.TestCase):
    def test_blackout_bombers(self):
        steps = list(_walk(_find_steps(gof3_missions.blackout(_D(), 'gof3_ships'))))
        ships = {s['ship'] for s in steps if s.get('type') == 'spawn' and str(s.get('name', '')).startswith('Bomber')}
        self.assertEqual({f'gof3_ships:{gof3_props.bomber_id(r)}' for r in gof3_props.BOMBERS}, ships, 'GoF3 bombers, every race')
        self.assertTrue(any(s.get('type') == 'set' and s.get('variable') == 'bomberrace' and 'random(1, 3)' in s['value'] for s in steps))
        named = [s for s in steps if s.get('type') == 'spawn' and s.get('name') == 'Bomber 1']
        self.assertEqual(3, len(named), 'one spawn per race behind the race\'s if')

    def test_ufo_guards(self):
        for build, race in ((gof3_missions.hijack, 'vossk'), (gof3_missions.the_trap, 'pirates')):
            steps = list(_walk(_find_steps(build(_D(), 'gof3_ships'))))
            spawns = [s for s in steps if s.get('type') == 'spawn']
            self.assertIn(f'gof3_ships:{gof3_props.ufo_id(race)}', {s['ship'] for s in spawns})
            self.assertTrue(any(s.get('type') == 'waituntil' and 'alive("UFO") == 0' in s['condition'] for s in steps))


class CapitalTableTests(unittest.TestCase):
    def test_table(self):
        if structures is None: self.skipTest(why)
        keys = [(r, n) for r, n, *_ in capitals.CAPITALS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), len({name for *_, name, _ in capitals.CAPITALS}), 'every name once')
        self.assertTrue(set(capitals.LIGHT_FROM) <= set(keys) and capitals.FLAT <= set(keys))
        self.assertFalse(set(capitals.LIGHT_FROM) & capitals.FLAT)
        self.assertTrue(all(role in ('battleship', 'frigate', 'freighter') for _, _, role, _, _ in capitals.CAPITALS))


def _find_steps(o):
    """The steps list of a mission's file, wherever its builder put it."""
    if isinstance(o, dict):
        if isinstance(o.get('steps'), list): return o['steps']
        for v in o.values():
            r = _find_steps(v)
            if r: return r
    if isinstance(o, list):
        for v in o:
            r = _find_steps(v)
            if r: return r
    return []


if __name__ == '__main__':
    unittest.main()
