"""What a mod's file changes against the game's: archive members added, removed and changed, and inside BYML and
MSBT files the values that differ, one line per path.

    .venv-modkit\\Scripts\\python -m tools.modkit diff <mods>/<mod>/romfs/<path> [--to <RomFS path>]

The RomFS path defaults to the part of the file's path after romfs/.
"""
from . import byml, msbt, sarc


def _short(v, limit=80):
    s = repr(v)
    return s if len(s) <= limit else s[:limit - 3] + '...'


def value_diff(a, b, path, out):
    """Lines for every path where the decoded values a (game) and b (mod) differ."""
    if isinstance(a, dict) and isinstance(b, dict) and type(a) is type(b):
        for k in a:
            if k not in b:
                out.append(f'- {path}/{k}: {_short(a[k])}')
        for k in b:
            if k not in a:
                out.append(f'+ {path}/{k}: {_short(b[k])}')
            else:
                value_diff(a[k], b[k], f'{path}/{k}', out)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            if i >= len(b):
                out.append(f'- {path}/{i}: {_short(a[i])}')
            elif i >= len(a):
                out.append(f'+ {path}/{i}: {_short(b[i])}')
            else:
                value_diff(a[i], b[i], f'{path}/{i}', out)
    elif byml._freeze(a) != byml._freeze(b):
        out.append(f'~ {path}: {_short(a)} -> {_short(b)}')


def file_diff(kit, a, b, name, out):
    if a == b:
        return
    if a[:4] == b'SARC' and b[:4] == b'SARC':
        fa, fb = sarc.Sarc(a).files, sarc.Sarc(b).files
        for m in fa:
            if m not in fb:
                out.append(f'- {name}::{m} (removed)')
        for m in fb:
            if m not in fa:
                out.append(f'+ {name}::{m} (added, {len(fb[m]):,} bytes)')
            elif fa[m] != fb[m]:
                file_diff(kit, kit.decompress(fa[m]), kit.decompress(fb[m]), f'{name}::{m}', out)
    elif a[:2] in (b'YB', b'BY') and b[:2] in (b'YB', b'BY'):
        da, db = byml.read(a), byml.read(b)
        lines = []
        value_diff(da.root, db.root, '', lines)
        out.append(f'~ {name}' + ('' if lines else ' (same values, stored differently)'))
        out.extend('    ' + line for line in lines)
    elif a[:8] == b'MsgStdBn' and b[:8] == b'MsgStdBn':
        ma, mb = msbt.Msbt(a).messages, msbt.Msbt(b).messages
        out.append(f'~ {name}')
        for k in ma:
            if k not in mb:
                out.append(f'    - {k}')
            elif ma[k] != mb[k]:
                out.append(f'    ~ {k}: {_short(ma[k])} -> {_short(mb[k])}')
        out.extend(f'    + {k}: {_short(mb[k])}' for k in mb if k not in ma)
    else:
        out.append(f'~ {name} ({len(a):,} -> {len(b):,} bytes; format not decoded)')
