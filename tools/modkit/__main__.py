"""TotK 1.2.1 mod kit: read the game's RomFS, decode and encode its files, write edited files into a mod folder.

    .venv-modkit\\Scripts\\python -m tools.modkit <command> ...      (from the repository root)

A SPEC names a file: a RomFS path (Pack/Actor/Weapon_Sword_001.pack.zs) or a local file, optionally followed by
::member for a file inside a SARC archive, repeated for nested archives
(Mals/USen.Product.121.sarc.zs::ActorMsg/Name.msbt). Compressed files are decompressed on reading.

Commands:
  info                         the game folder, file count, zstd dictionaries
  search PATTERN               RomFS paths matching a glob (* crosses /; case-insensitive) or --regex
  extract SPEC [-o FILE]       the file's bytes, decompressed (--raw: as stored)
  ls SPEC                      the members of a SARC archive
  unpack SPEC -o DIR           every member of a SARC archive into DIR
  pack DIR -o FILE             a SARC archive of every file under DIR (names relative to DIR)
  show SPEC [--json]           a BYML or MSBT file as YAML (or JSON) on stdout
  decode SPEC -o FILE          the same into a file (.json writes JSON)
  encode FILE -o OUT           YAML or JSON (as decode writes it) back to BYML or MSBT bytes
  install FILE --to SPEC --mod NAME --mods DIR
                               write FILE (YAML/JSON text or the file's own bytes) into DIR/NAME/romfs/<path>,
                               inside the archive when SPEC has ::member, compressed with the original's dictionary.
                               An archive the mod already holds is edited in place, so several members can be
                               changed one after another.
  diff FILE [--to PATH]        what a mod's file changes against the game's (members, BYML values, messages); PATH
                               defaults to the part of FILE's path after romfs/
  roundtrip [PATTERN] [--log FILE]
                               decode and re-encode files (default every BYML and archive) and count how many come
                               back byte for byte
  survey [--out DIR]           the roguelike index of maps, chests, enemies and GameData flags (build/modkit/survey)

--game DIR (or TOTK_GAME) names the game folder with romfs/romfs.bin and romfs/index.json; the default is the Game
folder next to the repository. YAML needs PyYAML (tools/modkit/requirements.txt). See docs/modding/README.md.
"""
import argparse
import json
import sys
from pathlib import Path

from . import byml, msbt, sarc
from .romfs import ZSTD_MAGIC, RomFS

SEP = '::'


class Kit:
    def __init__(self, game):
        self.game = game
        self._romfs = None

    @property
    def romfs(self):
        if self._romfs is None:
            self._romfs = RomFS(self.game)
        return self._romfs

    def has_romfs(self):
        try:
            return self.romfs is not None
        except FileNotFoundError:
            return False

    def decompress(self, raw):
        if raw[:4] != ZSTD_MAGIC:
            return raw
        if self.has_romfs():
            return self.romfs.decompress(raw)
        import compression.zstd as zstd
        return zstd.decompress(raw)

    def read_base(self, path, raw=False):
        """A RomFS path or a local file."""
        local = Path(path)
        if local.is_file():
            data = local.read_bytes()
        elif self.has_romfs() and path in self.romfs:
            data = self.romfs.read_raw(path)
        else:
            sys.exit(f'modkit: {path}: no such local file or RomFS path (search with: python -m tools.modkit search)')
        return data if raw else self.decompress(data)

    def read(self, spec, raw=False):
        base, *members = spec.split(SEP)
        data = self.read_base(base, raw=raw and not members)
        for m in members:
            arc = sarc.Sarc(data)
            if m not in arc.files:
                sys.exit(f'modkit: {m}: not in the archive (list it with: python -m tools.modkit ls)')
            data = self.decompress(arc.files[m])
        return data


def kind_of(data):
    if data[:4] == b'SARC':
        return 'sarc'
    if data[:2] in (b'YB', b'BY'):
        return 'byml'
    if data[:8] == b'MsgStdBn':
        return 'msbt'
    return None


def to_text(data, as_json):
    k = kind_of(data)
    if k == 'byml':
        doc = byml.read(data)
        return byml.to_json(doc) if as_json else byml.to_yaml(doc)
    if k == 'msbt':
        m = msbt.Msbt(data)
        return msbt.to_json(m) if as_json else msbt.to_yaml(m)
    sys.exit('modkit: not a BYML or MSBT file' + (' (a SARC archive: use ls or unpack)' if k == 'sarc' else ''))


def from_text(text, as_json):
    """BYML or MSBT bytes of a decode output."""
    if as_json:
        doc = json.loads(text)
    else:
        from . import yamlio
        doc = yamlio.load(text)
    if isinstance(doc, dict) and 'messages' in doc:
        return msbt.Msbt.from_dict(doc).write()
    if isinstance(doc, dict) and 'root' in doc:
        if as_json:
            return byml.from_json(text).to_bytes()
        return byml.from_yaml(text).to_bytes()
    sys.exit('modkit: the text is neither a BYML document (root:) nor an MSBT one (messages:)')


def read_input(path):
    """The bytes FILE stands for: YAML/JSON text encoded, any other file as it is (decompressed)."""
    p = Path(path)
    if p.suffix.lower() in ('.yml', '.yaml', '.json'):
        return from_text(p.read_text(encoding='utf-8'), p.suffix.lower() == '.json')
    data = p.read_bytes()
    if data[:4] == ZSTD_MAGIC:
        sys.exit(f'modkit: {path} is compressed; pass the decompressed file (extract writes one)')
    return data


def write_out(path, data):
    if path in (None, '-'):
        if isinstance(data, str):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stdout.write(data)
        else:
            sys.stdout.buffer.write(data)
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        p.write_text(data, encoding='utf-8', newline='\n')
    else:
        p.write_bytes(data)
    print(f'wrote {p} ({p.stat().st_size:,} bytes)', file=sys.stderr)


def install(kit, src, spec, mod, mods):
    base, *members = spec.split(SEP)
    romfs = kit.romfs
    if base not in romfs:
        print(f'note: {base} is not in the RomFS: the mod adds it', file=sys.stderr)
    target = Path(mods) / mod / 'romfs' / base
    new = read_input(src)
    if members:
        # Start from the mod's own copy of the archive when it has one, so edits accumulate.
        if not target.is_file() and base not in romfs:
            sys.exit(f'modkit: {base}: no such archive in the RomFS or the mod (pack a new one with: pack)')
        outer = romfs.decompress(target.read_bytes()) if target.is_file() else romfs.read(base)
        chain = [outer]
        for m in members[:-1]:
            chain.append(kit.decompress(sarc.Sarc(chain[-1]).files[m]))
        for depth in range(len(members) - 1, -1, -1):
            arc = sarc.Sarc(chain[depth])
            old = arc.files.get(members[depth])
            if old is None:
                print(f'note: {members[depth]} is not in the archive: the mod adds it', file=sys.stderr)
            elif old[:4] == ZSTD_MAGIC:
                new = _recompress(kit, old, new)   # a compressed member stays compressed
            arc.files[members[depth]] = new
            new = arc.write()
    data = romfs.compress_like(new, base)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    size = len(romfs.decompress(data))
    orig = len(romfs.read(base)) if base in romfs else 0
    print(f'wrote {target} ({len(data):,} bytes stored, {size:,} decompressed; the original is {orig:,})')
    if size > orig:
        print('note: larger than the original: the port raises its resource size table entry at start '
              '(docs/mods.md); other loaders need a RESTBL entry')


def _recompress(kit, old, new):
    import compression.zstd as zstd
    d = kit.romfs.dictionary_for(old)
    return zstd.compress(new, level=19, zstd_dict=d)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m tools.modkit', description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='\n'.join(__doc__.splitlines()[2:]))
    ap.add_argument('--game', help='game folder with romfs/romfs.bin and romfs/index.json')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('info')
    p = sub.add_parser('search')
    p.add_argument('pattern')
    p.add_argument('--regex', action='store_true')
    p.add_argument('--sizes', action='store_true', help='print the stored size too')
    p = sub.add_parser('extract')
    p.add_argument('spec')
    p.add_argument('-o', '--out')
    p.add_argument('--raw', action='store_true', help='the bytes as stored, still compressed')
    p = sub.add_parser('ls')
    p.add_argument('spec')
    p = sub.add_parser('unpack')
    p.add_argument('spec')
    p.add_argument('-o', '--out', required=True)
    p = sub.add_parser('pack')
    p.add_argument('dir')
    p.add_argument('-o', '--out', required=True)
    for name in ('show', 'decode'):
        p = sub.add_parser(name)
        p.add_argument('spec')
        p.add_argument('--json', action='store_true')
        p.add_argument('-o', '--out', required=name == 'decode')
    p = sub.add_parser('encode')
    p.add_argument('file')
    p.add_argument('-o', '--out', required=True)
    p = sub.add_parser('install')
    p.add_argument('file')
    p.add_argument('--to', required=True, help='RomFS path, ::member for a file inside an archive')
    p.add_argument('--mod', required=True, help='the mod folder name')
    p.add_argument('--mods', required=True, help='the mods folder (the one next to totk.exe for the game to load it)')
    p = sub.add_parser('diff')
    p.add_argument('file')
    p.add_argument('--to')
    p = sub.add_parser('roundtrip')
    p.add_argument('pattern', nargs='?')
    p.add_argument('--log')
    p = sub.add_parser('survey')
    p.add_argument('--out')
    p.add_argument('--merged', action='store_true')
    a = ap.parse_args(argv)
    kit = Kit(a.game)

    if a.cmd == 'info':
        r = kit.romfs
        print(f'game: {r.game_dir}\nfiles: {len(r.files):,}')
        for i, (name, _) in sorted(r.dictionaries.items()):
            print(f'dictionary {i}: {name}')
    elif a.cmd == 'search':
        for path in kit.romfs.search(a.pattern, a.regex):
            print(f"{kit.romfs.files[path]['size']:>12,}  {path}" if a.sizes else path)
    elif a.cmd == 'extract':
        write_out(a.out, kit.read(a.spec, raw=a.raw))
    elif a.cmd == 'ls':
        arc = sarc.Sarc(kit.read(a.spec))
        for name, data in arc.files.items():
            print(f'{len(data):>10,}  {name}')
    elif a.cmd == 'unpack':
        arc = sarc.Sarc(kit.read(a.spec))
        out = Path(a.out)
        for name, data in arc.files.items():
            t = out / name
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(data)
        print(f'{len(arc.files)} files into {out}')
    elif a.cmd == 'pack':
        arc = sarc.Sarc()
        root = Path(a.dir)
        for f in sorted(root.rglob('*')):
            if f.is_file():
                arc.files[f.relative_to(root).as_posix()] = f.read_bytes()
        write_out(a.out, arc.write())
    elif a.cmd in ('show', 'decode'):
        as_json = a.json or (a.out or '').lower().endswith('.json')
        write_out(a.out, to_text(kit.read(a.spec), as_json))
    elif a.cmd == 'encode':
        write_out(a.out, read_input(a.file))
    elif a.cmd == 'install':
        install(kit, a.file, a.to, a.mod, a.mods)
    elif a.cmd == 'diff':
        from . import diff
        to = a.to
        if not to:
            parts = Path(a.file).resolve().as_posix().split('/romfs/', 1)
            if len(parts) != 2:
                sys.exit('modkit: FILE is not under a romfs folder: pass --to <RomFS path>')
            to = parts[1]
        out = []
        diff.file_diff(kit, kit.read(to), kit.read(a.file), to, out)
        sys.stdout.reconfigure(encoding='utf-8')
        print('\n'.join(out) if out else 'no change')
    elif a.cmd == 'roundtrip':
        from . import roundtrip
        return roundtrip.main(kit.romfs, a.pattern, a.log)
    elif a.cmd == 'survey':
        from . import survey
        return survey.main((['--game', a.game] if a.game else []) + (['--out', a.out] if a.out else [])
                           + (['--merged'] if a.merged else []))


if __name__ == '__main__':
    sys.exit(main())
