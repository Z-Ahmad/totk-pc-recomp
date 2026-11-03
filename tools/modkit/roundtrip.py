"""Decode and re-encode RomFS files and count how many come back byte for byte: SARC archives (and every member in
them), BYML and MSBT.

    .venv-modkit\\Scripts\\python -m tools.modkit roundtrip [PATTERN] [--log FILE]

PATTERN is a glob over RomFS paths (default: every BYML file and every archive, about 157,000 files and 460,000
members: some 7 minutes). Each file is one of: identical; equal (re-encoded differently, the same values when decoded
again); DIFFERENT; error. --log lists every file that is not identical.
"""
import collections
import sys
import time

from . import byml, msbt, sarc

ARCHIVES = ('.pack.zs', '.sarc.zs', '.blarc.zs', '.bfarc.zs')


def check(romfs, name, data, res, log):
    if data[:2] in (b'YB', b'BY'):
        doc = byml.read(data)
        out = doc.to_bytes()
        if out == data:
            res['byml identical'] += 1
        elif byml._freeze(byml.read(out).root) == byml._freeze(doc.root):
            res['byml equal'] += 1
            log(f'equal\t{name}\t{len(data)}\t{len(out)}')
        else:
            res['byml DIFFERENT'] += 1
            log(f'DIFFERENT\t{name}')
    elif data[:8] == b'MsgStdBn':
        ok = msbt.Msbt(data).write() == data
        res['msbt ' + ('identical' if ok else 'DIFFERENT')] += 1
        if not ok:
            log(f'DIFFERENT\t{name}')
    elif data[:4] == b'SARC':
        arc = sarc.Sarc(data)
        ok = arc.write() == data
        res['sarc ' + ('identical' if ok else 'DIFFERENT')] += 1
        if not ok:
            log(f'DIFFERENT\t{name}')
        for member, body in arc.files.items():
            run(romfs, f'{name}::{member}', lambda: romfs.decompress(body), res, log)


def run(romfs, name, get, res, log):
    try:
        check(romfs, name, get(), res, log)
    except Exception as e:   # noqa: BLE001 - a file the codecs reject is counted and listed, the run goes on
        res['error'] += 1
        log(f'error\t{name}\t{e}')


def main(romfs, pattern=None, log_path=None):
    if pattern:
        paths = romfs.search(pattern)
    else:
        paths = sorted(p for p in romfs.files if '.byml' in p or p.endswith('.bgyml') or p.endswith(ARCHIVES))
    out = open(log_path, 'w', encoding='utf-8') if log_path else None

    def log(line):
        if out:
            print(line, file=out, flush=True)
    res, t0 = collections.Counter(), time.time()
    for i, p in enumerate(paths):
        run(romfs, p, lambda: romfs.read(p), res, log)
        if i % 10000 == 9999:
            print(f'{i + 1:,} / {len(paths):,} files, {time.time() - t0:.0f} s', file=sys.stderr)
    print(f'{len(paths):,} files, {time.time() - t0:.0f} s')
    for k, v in sorted(res.items()):
        print(f'{v:>10,}  {k}')
    if out:
        out.close()
    return 1 if res['byml DIFFERENT'] or res['msbt DIFFERENT'] or res['sarc DIFFERENT'] or res['error'] else 0
