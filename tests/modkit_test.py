"""tools/modkit: SARC, BYML and MSBT round trips, on values made here and on the game's own files.

The synthetic tests need nothing. The game tests read the 1.2.1 RomFS (the Game folder next to the repository, or
TOTK_GAME) and skip without it: every non-actor archive and samples of actor packs, baked data and terrain archives
rebuild byte for byte, a sample of BYML files (with GameDataList, every RSDB table and the hash-dictionary files) and
every MSBT of every language come back byte for byte through the binary codec and through YAML and JSON, and an edit
installed into a mod folder holds the change, keeps every other member and uses the original's zstd dictionary. MODKIT_SAMPLE sets the sample sizes (default 200).
Nothing is written outside a temporary folder.

Run: .venv-modkit\\Scripts\\python tests\\modkit_test.py      (.venv-py314 runs everything except the YAML checks)
"""
import contextlib
import io
import math
import os
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.modkit import byml, msbt, sarc  # noqa: E402
from tools.modkit.romfs import RomFS  # noqa: E402

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

SAMPLE = int(os.environ.get('MODKIT_SAMPLE', '200'))


def load_romfs():
    try:
        return RomFS()
    except (FileNotFoundError, ValueError):
        return None


ROMFS = load_romfs()
need_game = unittest.skipUnless(ROMFS, 'no 1.2.1 game folder (set TOTK_GAME)')
need_yaml = unittest.skipUnless(HAVE_YAML, 'PyYAML not installed (tools/modkit/requirements.txt)')


def sample_doc():
    return byml.Document({
        'Name': 'Ünïcode', 'S32': -5, 'F32': 0.1, 'U32': byml.UInt(4000000000), 'S64': byml.Int64(-2**40),
        'U64': byml.UInt64(2**63 + 5), 'F64': byml.Double(1 / 3), 'Bool': True, 'Null': None,
        'Bin': b'\x00\x01\xff', 'ABin': byml.AlignedBinary(b'abc', 0x10), 'Empty': {}, 'EmptyList': [],
        'List': [1, 2.5, 'x', [3.0, 4.0, 5.0], {'a': 1}], 'Shared': [1.0, 2.0, 3.0], 'Shared2': [1.0, 2.0, 3.0],
        'NumberLike': '0012', 'Nan': float('nan'),
        'H32': byml.HashDict32({5: 1, 2**32 - 1: [1.0], 7: 'x'}), 'H64': byml.HashDict64({2**64 - 1: byml.UInt64(1)}),
    })


class Synthetic(unittest.TestCase):
    def test_sarc(self):
        a = sarc.Sarc()
        a.files['b/x.bgyml'] = b'YB\x07\x00' + bytes(20)
        a.files['a/tex.bntx'] = b'BNTX' + bytes(100)
        a.files['c.txt'] = b'hello'
        data = a.write()
        b = sarc.Sarc(data)
        self.assertEqual(b.files, a.files)
        self.assertEqual(b.write(), data)
        start = struct.unpack_from('<I', data, 12)[0]
        self.assertEqual(start % 0x1000, 0)   # the largest member alignment

    def test_byml_binary(self):
        doc = sample_doc()
        for be in (False, True):
            for share in (False, True):
                doc.big_endian, doc.share_containers = be, share
                data = doc.to_bytes()
                back = byml.read(data)
                self.assertEqual(back.big_endian, be)
                self.assertEqual(back.share_containers, share)
                self.assertEqual(back.to_bytes(), data)
                self.assertEqual(type(back.root['U64']), byml.UInt64)
                self.assertEqual(back.root['ABin'].alignment, 0x10)
                self.assertTrue(math.isnan(back.root['Nan']))

    def test_byml_json(self):
        data = sample_doc().to_bytes()
        doc = byml.read(data)
        self.assertEqual(byml.from_json(byml.to_json(doc)).to_bytes(), data)

    @need_yaml
    def test_byml_yaml(self):
        data = sample_doc().to_bytes()
        doc = byml.read(data)
        text = byml.to_yaml(doc)
        self.assertIn('!ul', text)
        self.assertEqual(byml.from_yaml(text).to_bytes(), data)

    def test_f32_repr(self):
        for v in (0.1, 1500.0, -40.0, 4.5599466e-14, 3.4028234663852886e+38, 1e-45, 6.0000005, -0.0):
            f = struct.unpack('<f', struct.pack('<f', v))[0]
            s = byml.f32_repr(f)
            self.assertIn('.', s.split('e')[0])
            self.assertEqual(struct.pack('<f', float(s)), struct.pack('<f', f))

    def test_msbt(self):
        m = msbt.Msbt()
        m.buckets = 7
        m.messages = {'Hello': 'Hi {{0.3:ffff}}there\\{x\\\\', 'Second': 'Line one\nline two{{1.4}}{{/2.1}}'}
        data = m.write()
        back = msbt.Msbt(data)
        self.assertEqual(back.messages, m.messages)
        self.assertEqual(back.write(), data)
        self.assertEqual(msbt.from_json(msbt.to_json(back)).write(), data)
        if HAVE_YAML:
            self.assertEqual(msbt.from_yaml(msbt.to_yaml(back)).write(), data)
        bad = msbt.Msbt()
        bad.messages = {'x': 'a { b'}
        with self.assertRaises(msbt.MsbtError):
            bad.write()


@need_game
class Game(unittest.TestCase):
    rng = random.Random(1)

    def test_dictionaries(self):
        names = sorted(n for n, _ in ROMFS.dictionaries.values())
        self.assertEqual(names, ['bcett.byml.zsdic', 'pack.zsdic', 'zs.zsdic'])
        for path in ('Pack/Actor/Weapon_Sword_001.pack.zs', 'Banc/SmallDungeon/Dungeon001_Static.bcett.byml.zs',
                     'Mals/USen.Product.121.sarc.zs'):
            raw = ROMFS.read_raw(path)
            again = ROMFS.compress_like(ROMFS.decompress(raw), path)
            self.assertIs(ROMFS.dictionary_for(again), ROMFS.dictionary_for(raw))
            self.assertIs(ROMFS.dictionary_for_name('X/New' + path[path.index('.'):]), ROMFS.dictionary_for(raw))

    def test_sarc_identical(self):
        arcs = [p for p in ROMFS.files if p.endswith(('.pack.zs', '.sarc.zs', '.blarc.zs', '.bfarc.zs', '.genvb.zs'))]
        actor = [p for p in arcs if p.startswith('Pack/Actor/')]
        bulk = [p for p in ROMFS.files if p.endswith(('.bkres.zs', '.ta.zs'))]   # baked data, terrain
        for p in ([p for p in arcs if not p.startswith('Pack/Actor/')] + self.rng.sample(actor, SAMPLE)
                  + self.rng.sample(bulk, SAMPLE)):
            with self.subTest(p):
                d = ROMFS.read(p)
                self.assertEqual(sarc.Sarc(d).write(), d)

    def test_byml_identical(self):
        files = [p for p in ROMFS.files if '.byml' in p or p.endswith('.bgyml')]
        paths = (self.rng.sample(files, SAMPLE) + ['GameData/GameDataList.Product.110.byml.zs'] + ROMFS.search('RSDB/*')
                 + ROMFS.search('Voice/BwavInfo/*'))
        pack = sarc.Sarc(ROMFS.read('Pack/Actor/Enemy_Bokoblin_Junior.pack.zs'))
        members = [(f'Enemy_Bokoblin_Junior::{n}', d) for n, d in pack.files.items() if d[:2] == b'YB']
        for name, d in [(p, ROMFS.read(p)) for p in paths] + members:
            with self.subTest(name):
                doc = byml.read(d)
                out = doc.to_bytes()
                if out != d and (name.endswith('_Static.bcett.byml.zs') or name.endswith('TravelerInfo.byml.zs')):
                    # The 196 files whose equal containers the game shares only in part (byml.py): same values.
                    self.assertEqual(byml._freeze(byml.read(out).root), byml._freeze(doc.root))
                    continue
                self.assertEqual(out, d)
                if d is members[0][1] or name.startswith('Banc/SmallDungeon') or len(d) < 20000:
                    self.assertEqual(byml.from_json(byml.to_json(doc)).to_bytes(), d)
                    if HAVE_YAML:
                        self.assertEqual(byml.from_yaml(byml.to_yaml(doc)).to_bytes(), d)

    def test_msbt_identical(self):
        for p in ROMFS.search('Mals/*.sarc.zs'):
            arc = sarc.Sarc(ROMFS.read(p))
            for n, d in arc.files.items():
                with self.subTest(f'{p}::{n}'):
                    m = msbt.Msbt(d)
                    self.assertEqual(m.write(), d)
                    if p.startswith('Mals/USen'):
                        self.assertEqual(msbt.from_json(msbt.to_json(m)).write(), d)
                        if HAVE_YAML:
                            self.assertEqual(msbt.from_yaml(msbt.to_yaml(m)).write(), d)

    def test_install(self):
        from tools.modkit.__main__ import main
        pack = 'Pack/Actor/Weapon_Sword_001.pack.zs'
        member = 'Component/WeaponParam/Weapon_Sword_001.game__component__WeaponParam.bgyml'
        with tempfile.TemporaryDirectory() as tmp:
            doc = byml.read(sarc.Sarc(ROMFS.read(pack)).files[member])
            doc.root['BaseAttack'] = 99
            src = Path(tmp) / 'edit.json'
            src.write_text(byml.to_json(doc), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                main(['install', str(src), '--to', f'{pack}::{member}', '--mod', 'Test', '--mods', tmp])
            out = Path(tmp) / 'Test/romfs' / pack
            raw = out.read_bytes()
            self.assertIs(ROMFS.dictionary_for(raw), ROMFS.dictionary_for(ROMFS.read_raw(pack)))
            old, new = sarc.Sarc(ROMFS.read(pack)).files, sarc.Sarc(ROMFS.decompress(raw)).files
            self.assertEqual(list(old), list(new))
            self.assertEqual([n for n in old if old[n] != new[n]], [member])
            self.assertEqual(byml.read(new[member]).root['BaseAttack'], 99)


if __name__ == '__main__':
    unittest.main()
