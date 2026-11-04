"""GoF3's bosses as the rift's bosses (tools/gof3_wanted.py rift): hull + shield over a pirate fighter's."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
try:
    import gof3_wanted
except ImportError as e:   # (its Pillow import)
    gof3_wanted = None
    why = str(e)


@unittest.skipIf(gof3_wanted is None, 'gof3_wanted needs Pillow')
class RiftTests(unittest.TestCase):
    def test_bosses(self):
        bosses = [{'shape': '/assets/ships/vossk/120/x.ae4', 'hull': 5250.0, 'shield': 1732.5},
                  {'shape': '/assets/ships/terran/001/x.ae4', 'hull': 1404.26, 'shield': 0.0},
                  {'shape': '/assets/ships/void/999/x.ae4', 'hull': 9000.0, 'shield': 0.0}]
        r = gof3_wanted.rift(bosses, {'vossk_120', 'terran_001'}, 'gof3_ships', 481.25)
        self.assertEqual('rift', r['kind'])
        self.assertEqual([{'ship': 'gof3_ships:vossk_120', 'raiders': 14.51}, {'ship': 'gof3_ships:terran_001', 'raiders': 2.92}],
                         r['bosses'], 'hull + shield over the raider\'s; a hull the mod lacks left out')
        self.assertIsNone(gof3_wanted.rift(bosses[2:], {'vossk_120'}, 'gof3_ships', 481.25))

    def test_race(self):
        r = gof3_wanted.rift([{'shape': '/assets/ships/vossk/120/x.ae4', 'hull': 1.0, 'shield': 0.0, 'race': 7}], {'vossk_120'},
                             'gof3_ships', 1.0, {7: 8, 4: 1})
        self.assertEqual('pirate', r['bosses'][0]['race'], 'its race as on the Most Wanted boards')


if __name__ == '__main__':
    unittest.main()
