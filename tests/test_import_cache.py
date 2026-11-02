"""Run with python -m unittest discover -s tests -v; no game assets or Blender needed.

Exercise real importer orchestration and cache records, with tiny deterministic conversion fixtures.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_cache as cache


def load_importer(path):
    spec = importlib.util.spec_from_file_location('gof3_importer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CacheTests(unittest.TestCase):
    def test_markers_reject_legacy_corrupt_and_changed_fingerprints(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.done'
            self.assertFalse(cache.done(d, 'a'))
            for text in ('2026-10-24\n', '{', '[]', '{"schema": 2, "fingerprint": "a"}'):
                p.write_text(text)
                self.assertFalse(cache.done(d, 'a'))
            cache.mark(d, 'a', skipped=['missing material'])
            self.assertTrue(cache.done(d, 'a'))
            self.assertFalse(cache.done(d, 'b'))
            self.assertEqual(['missing material'], cache.record(d)['skipped'])

    def test_recipe_tracks_transitive_imports_and_subprocess_scripts(self):
        files = cache.recipe(ROOT, ['convert_weapons.py'])
        for name in ('convert_weapons.py', 'ae4_weapon_textures.py', 'ae4_weapon_to_fbx.py',
                     'ae4_to_gltf.py', 'ae4unpack.py', 'ship_overrides.json', 'build_cache.py'):
            self.assertIn('tools/' + name, files)
        self.assertNotIn('tools/build_gof3_systems.py', files)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'importer'
        self.repo.mkdir()
        shutil.copy2(ROOT / 'import.py', self.repo / 'import.py')
        shutil.copytree(ROOT / 'tools', self.repo / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        self.m = load_importer(self.repo / 'import.py')
        self.work, self.out = self.root / 'work', self.root / 'mod'
        self.archive = self.root / 'main.1.obb'
        self.archive.write_bytes(b'AAAA')
        self.jet = self.root / 'game.jet'
        self.jet.write_bytes(b'PDB!')
        self.calls = []
        self.fail_hull = False
        self.fail_variant = False
        self.fail_loadout = False
        self.skipped = False
        self.hull = 'ship_terran_000'
        self.scheme = 'gold'
        self.blender_identity = 'Blender 4.5.3'

    def extract(self, path, _, dest):
        self.calls.append('extract:' + Path(path).name)
        p = Path(dest)
        p.mkdir(parents=True)
        (p / 'data.pdb').write_bytes(Path(path).read_bytes())
        folder = p / 'assets/ships/terran/000'
        folder.mkdir(parents=True)
        (folder / (self.hull + '_lod_000_body.ae4model')).write_bytes(b'model')
        return True

    def run_conversion(self, cmd, logf, env):
        name = next(Path(v).name for v in cmd if str(v).endswith('.py'))
        self.calls.append(name)
        Path(logf).parent.mkdir(parents=True, exist_ok=True)
        Path(logf).write_text('  skipped gold: missing material\n' if name == 'convert_weapons.py' and self.skipped else '')
        if name == 'ae4_pdb_arming.py':
            Path(cmd[-1]).write_text('{}')
        elif name == 'ae4_resolve.py':
            Path(cmd[-1]).write_text(json.dumps({'schemes': [f'ship_body_{self.scheme}.ae4material']}))
        elif name == 'ae4_ship_to_fbx.py':
            folder = Path(cmd[-1])
            (folder / (self.hull + '.blend')).write_bytes(b'hull')
        elif name == 'ae4_scheme_variant.py':
            folder = Path(cmd[-2]).parent / (self.hull + '_' + self.scheme)
            folder.mkdir()
            (folder / (folder.name + '.blend')).write_bytes(b'variant')
            if self.fail_variant: return False
        elif name == 'ae4_to_gltf.py':
            p = Path(cmd[-1])
            if self.fail_hull and p.stem == self.hull: return False
            p.with_suffix('.glb').write_bytes(b'glb')
        elif name == 'convert_weapons.py':
            folder = Path(cmd[-1]) / 'weapon_generic_000'
            folder.mkdir(parents=True)
            (folder / 'weapon.blend').write_bytes(b'weapon')
        elif name == 'build_loadouts.py':
            folder = Path(cmd[-2])
            folder.mkdir()
            records = {}
            for blend in sorted(Path(cmd[-3]).glob('ship_*/*.blend')):
                records[blend.stem] = {'record': blend.stem}
                if self.fail_loadout: records[blend.stem]['error'] = blend.stem + '.error.log'
                else: (folder / (blend.stem + '.glb')).write_bytes(b'loadout')
            (folder / 'manifest.json').write_text(json.dumps(records))
        elif name == 'build_gof3_mod.py':
            folder = Path(cmd[2])
            records = json.loads((Path(env['GOF3_LOADOUTS']) / 'manifest.json').read_text())
            (folder / 'ships.json').write_text(json.dumps(sorted(records)))
            (folder / 'mod.json').write_text('{"id": "gof3_ships"}')
            (folder / 'payload.bin').write_bytes(b'constant converted payload')
        return True

    def build(self, *args):
        self.calls = []
        argv = ['import.py', str(self.archive), str(self.jet), '--work', str(self.work), '--out', str(self.out), '--jobs', '1', *args]
        import tinextract
        with contextlib.ExitStack() as stack:
            for name, value in (('check_python', lambda: None), ('find_blender', lambda _: 'blender'),
                                ('blender_version', lambda _: self.blender_identity), ('lock_work', lambda _: None), ('run', self.run_conversion)):
                stack.enter_context(patch.object(self.m, name, value))
            stack.enter_context(patch.object(tinextract, 'extract', self.extract))
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.m.main()
        return json.loads(Path(str(self.out) + '.build-manifest.json').read_text())

    def edit(self, name):
        with (self.repo / 'tools' / name).open('a') as f: f.write('\n# converter changed\n')

    def test_unchanged_resume_skips_conversion_and_matches_clean_payload(self):
        first = self.build()
        expected = {p.name: p.read_bytes() for p in self.out.iterdir() if p.name != 'build-manifest.json'}
        resumed = self.build()
        self.assertEqual(['build_gof3_mod.py'], self.calls)
        self.assertEqual(first['stages'], resumed['stages'])
        self.assertEqual(expected, {p.name: p.read_bytes() for p in self.out.iterdir() if p.name != 'build-manifest.json'})
        shutil.rmtree(self.work)
        clean = self.build()
        self.assertEqual(first['stages'], clean['stages'])
        self.assertEqual(expected, {p.name: p.read_bytes() for p in self.out.iterdir() if p.name != 'build-manifest.json'})

    def test_provenance_stays_outside_the_game_mod(self):
        manifest = self.build()
        self.assertFalse((self.out / 'build-manifest.json').exists())
        self.assertEqual(manifest, json.loads((self.work / 'build-manifest.json').read_text()))
        self.assertIn('tools/build_gof3_mod.py', manifest['importer']['files'])
        self.assertEqual('Blender 4.5.3', manifest['runtime']['blender'])

    def test_legacy_markers_are_rebuilt(self):
        self.build()
        for marker in self.work.rglob('.done'):
            marker.write_text('2026-10-24\n')
        self.build()
        self.assertIn('extract:main.1.obb', self.calls)
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('convert_weapons.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)

    def test_extractor_change_invalidates_extraction_and_downstream(self):
        self.build()
        self.edit('tinextract.py')
        self.build()
        self.assertIn('extract:main.1.obb', self.calls)
        self.assertIn('extract:game.jet', self.calls)
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('convert_weapons.py', self.calls)

    def test_conversion_table_change_preserves_extraction(self):
        self.build()
        table = self.repo / 'tools/ship_overrides.json'
        table.write_text(table.read_text() + '\n')
        self.build()
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertNotIn('extract:main.1.obb', self.calls)
        self.assertNotIn('ae4_pdb_arming.py', self.calls)

    def test_data_reader_change_rebuilds_dependent_stages(self):
        self.build()
        self.edit('ae4_pdb_arming.py')
        self.build()
        self.assertIn('ae4_pdb_arming.py', self.calls)
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)
        self.assertNotIn('extract:main.1.obb', self.calls)

    def test_same_size_source_replacement_reextracts_and_invalidates_downstream(self):
        first = self.build()
        self.archive.write_bytes(b'BBBB')
        second = self.build()
        self.assertIn('extract:main.1.obb', self.calls)
        self.assertNotIn('extract:game.jet', self.calls)
        for name in ('ae4_pdb_arming.py', 'ae4_ship_to_fbx.py', 'convert_weapons.py', 'build_loadouts.py'):
            self.assertIn(name, self.calls)
        self.assertNotEqual({s['name']: s['sha256'] for s in first['sources']},
                            {s['name']: s['sha256'] for s in second['sources']})

    def test_ship_converter_change_preserves_extraction_data_and_weapons(self):
        self.build()
        self.edit('ae4_ship_textures.py')
        self.build()
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)
        for name in ('extract:main.1.obb', 'ae4_pdb_arming.py', 'convert_weapons.py'):
            self.assertNotIn(name, self.calls)

    def test_weapon_helper_change_preserves_ships_and_rebuilds_loadouts(self):
        self.build()
        self.edit('ae4_weapon_to_fbx.py')
        self.build()
        self.assertIn('convert_weapons.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)
        self.assertNotIn('ae4_ship_to_fbx.py', self.calls)

    def test_loadout_helper_change_only_rebuilds_loadouts_and_mod(self):
        self.build()
        self.edit('ae4_loadout_gltf.py')
        self.build()
        self.assertEqual(['build_loadouts.py', 'build_gof3_mod.py'], self.calls)

    def test_final_builder_change_preserves_all_conversion_caches(self):
        first = self.build()
        self.edit('engine_meshes.py')
        second = self.build('--max-texture', '2048', '--no-icons')
        self.assertEqual(['build_gof3_mod.py'], self.calls)
        self.assertNotEqual(first['stages']['mod'], second['stages']['mod'])
        self.assertEqual(2048, second['options']['max_texture'])
        self.assertFalse(second['options']['icons'])

    def test_blender_patch_version_invalidates_blender_outputs(self):
        self.build()
        self.blender_identity = 'Blender 4.5.4'
        self.build()
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('convert_weapons.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)
        self.assertNotIn('extract:main.1.obb', self.calls)
        self.assertNotIn('ae4_pdb_arming.py', self.calls)

    def test_failed_final_build_removes_previous_provenance(self):
        self.build()
        original = self.run_conversion
        def failing(cmd, logf, env):
            if any(str(arg).endswith('build_gof3_mod.py') for arg in cmd): return False
            return original(cmd, logf, env)
        self.run_conversion = failing
        with self.assertRaises(SystemExit): self.build()
        self.assertFalse(Path(str(self.out) + '.build-manifest.json').exists())
        self.assertFalse((self.work / 'build-manifest.json').exists())

    def test_fbx_option_invalidates_blender_outputs(self):
        self.build()
        self.build('--fbx')
        self.assertIn('ae4_ship_to_fbx.py', self.calls)
        self.assertIn('convert_weapons.py', self.calls)
        self.assertIn('build_loadouts.py', self.calls)
        self.assertNotIn('ae4_pdb_arming.py', self.calls)

    def test_failed_hull_is_cleaned_up_and_successful_retry_rebuilds_loadouts(self):
        self.fail_hull = True
        first = self.build()
        self.assertEqual([self.hull], first['failed_hulls'])
        self.assertFalse((self.work / 'converted' / self.hull).exists())
        self.fail_hull = False
        second = self.build()
        self.assertEqual([], second['failed_hulls'])
        self.assertIn('build_loadouts.py', self.calls)

    def test_failed_variant_is_retried_and_invalidates_loadouts_on_recovery(self):
        self.fail_variant = True
        first = self.build()
        self.assertTrue(first['warnings'])
        self.assertFalse((self.work / 'converted' / self.hull / '.done').exists())
        self.fail_variant = False
        second = self.build()
        self.assertEqual([], second['warnings'])
        self.assertIn('build_loadouts.py', self.calls)

    def test_loadout_errors_are_not_marked_complete(self):
        self.fail_loadout = True
        first = self.build()
        self.assertTrue(first['failed_loadouts'])
        self.assertFalse((self.work / 'loadouts/.done').exists())
        self.fail_loadout = False
        second = self.build()
        self.assertEqual([], second['failed_loadouts'])
        self.assertIn('build_loadouts.py', self.calls)

    def test_skipped_weapon_notes_survive_cache_reuse(self):
        self.skipped = True
        first = self.build()
        self.skipped = False
        second = self.build()
        self.assertEqual(first['skipped_weapons'], second['skipped_weapons'])
        self.assertTrue(second['skipped_weapons'])

    def test_old_variant_is_removed_when_converter_drops_it(self):
        self.build()
        old = self.work / 'converted' / (self.hull + '_gold')
        self.assertTrue(old.exists())
        self.scheme = 'dragon'
        self.edit('ae4_ship_textures.py')
        self.build()
        self.assertFalse(old.exists())

    def test_same_size_apk_member_is_refreshed(self):
        apk = self.root / 'game.apk'
        def replace(data):
            with zipfile.ZipFile(apk, 'w') as z: z.writestr('assets/game.jet', data)
        replace(b'OLD!')
        unpacked = str(self.root / 'sources')
        path = self.m.from_bundle(str(apk), unpacked)[0][1]
        replace(b'NEW!')
        self.assertEqual(path, self.m.from_bundle(str(apk), unpacked)[0][1])
        self.assertEqual(b'NEW!', Path(path).read_bytes())

    def test_conflicting_same_size_apks_are_rejected(self):
        paths = []
        for name, data in (('one.apk', b'AAAA'), ('two.apk', b'BBBB')):
            path = self.root / name
            with zipfile.ZipFile(path, 'w') as z: z.writestr('assets/game.jet', data)
            paths.append(str(path))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            self.m.find_sources(paths + [str(self.archive)], str(self.work))

    def test_conflicting_same_size_sources_are_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        conflict = other / self.archive.name
        conflict.write_bytes(b'BBBB')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            self.m.find_sources([str(self.archive), str(conflict), str(self.jet)], str(self.work))


if __name__ == '__main__':
    unittest.main()
