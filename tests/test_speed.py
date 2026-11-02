"""Performance changes must retain full content checks and exact texture dimensions."""
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_cache as cache


class BundleTests(unittest.TestCase):
    def test_identical_member_reused_without_rewriting(self):
        with tempfile.TemporaryDirectory() as d:
            archive = io.BytesIO()
            data = b'unchanged contents' * 1000
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z: z.writestr('member', data)
            destination = Path(d) / 'member'
            with zipfile.ZipFile(archive) as z:
                expected = cache.materialize_member(z, 'member', destination)
                with patch.object(cache.os, 'replace', side_effect=AssertionError('unchanged member rewritten')):
                    self.assertEqual(expected, cache.materialize_member(z, 'member', destination))
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
            self.assertEqual(data, destination.read_bytes())

    def test_same_size_changed_corrupted_shorter_and_longer_members_are_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, 'w') as z: z.writestr('member', b'NEW!')
            destination = Path(d) / 'member'
            with zipfile.ZipFile(blob) as z:
                for before in (b'OLD!', b'OLD', b'OLD!!', b''):
                    destination.write_bytes(before)
                    actual = cache.materialize_member(z, 'member', destination)
                    self.assertEqual(b'NEW!', destination.read_bytes())
                    self.assertEqual(hashlib.sha256(b'NEW!').hexdigest(), actual)

    def test_member_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / 'member'
            destination.write_bytes(b'previous')
            archive = types.SimpleNamespace(open=lambda *_: (_ for _ in ()).throw(ValueError('damaged member')))
            with self.assertRaises(ValueError): cache.materialize_member(archive, 'member', destination)
            self.assertEqual(b'previous', destination.read_bytes())

    def test_nested_apk_can_spill_to_disk_and_reuses_verified_member_hash(self):
        import tempfile as temporary
        spec = importlib.util.spec_from_file_location('bundle_speed_cli', ROOT / 'import.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as z: z.writestr('assets/game.jet', b'game data')
        with tempfile.TemporaryDirectory() as d:
            bundle = Path(d) / 'game.xapk'
            with zipfile.ZipFile(bundle, 'w') as z: z.writestr('base.apk', inner.getvalue())
            real = temporary.SpooledTemporaryFile
            streams = []
            def spool(**kwargs):
                stream = real(max_size=1); streams.append(stream); return stream
            verified = {}
            with patch.object(temporary, 'SpooledTemporaryFile', side_effect=spool):
                sources = module.from_bundle(str(bundle), str(Path(d) / 'sources'), verified)
            self.assertTrue(streams[0]._rolled)
            self.assertEqual(b'game data', Path(sources[0][1]).read_bytes())
            with patch.object(cache, 'file_hash', side_effect=AssertionError('verified member was reread')):
                self.assertEqual(hashlib.sha256(b'game data').hexdigest(), module.source_hash(sources[0][1], verified))


class TextureHeaderTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('texture_speed_test', ROOT / 'tools/ae4_texture.py')
        self.module = importlib.util.module_from_spec(spec)
        # Header inspection uses neither the optional decoder nor Pillow.
        with patch.dict(sys.modules, {'texture2ddecoder': types.SimpleNamespace(), 'PIL': types.SimpleNamespace(Image=object())}):
            spec.loader.exec_module(self.module)

    def test_uncompressed_dimensions_read_only_header(self):
        header = bytearray(32)
        header[:4] = b'ET4A'
        struct.pack_into('<H', header, 0x1a, 2048)
        struct.pack_into('<H', header, 0x1e, 1024)
        class HeaderOnly(io.BytesIO):
            def read(self, size=-1):
                if size != 32: raise AssertionError('read texture pixels for dimensions')
                return super().read(size)
        with patch('builtins.open', return_value=HeaderOnly(header)):
            self.assertEqual((2048, 1024), self.module.dimensions('texture'))

    def test_packed_header_uses_existing_legacy_unpacker(self):
        header = bytearray(32); header[:4] = b'ET4A'
        struct.pack_into('<H', header, 0x1a, 64); struct.pack_into('<H', header, 0x1e, 32)
        with patch('builtins.open', return_value=io.BytesIO(self.module.MAGIC + b'packed bytes')):
            with patch.object(self.module, 'unpack', return_value=header) as unpack:
                self.assertEqual((64, 32), self.module.dimensions('texture'))
                unpack.assert_called_once_with(self.module.MAGIC + b'packed bytes')

    def test_invalid_header_is_rejected(self):
        with patch('builtins.open', return_value=io.BytesIO(b'wrong file header')):
            with self.assertRaises(AssertionError): self.module.dimensions('texture')


if __name__ == '__main__': unittest.main()
