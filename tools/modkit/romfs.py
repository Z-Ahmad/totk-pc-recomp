"""Read files out of the merged 1.2.1 RomFS image and (de)compress them with the game's zstd dictionaries.

The image is the one the setup leaves in the install folder: <game>/romfs/romfs.bin and <game>/romfs/index.json
({status, romfs_size, romfs_sha256, files: [{path, offset, size}]}, written by tools/extract.py). Read only.

Most files end in .zs: one zstd frame, compressed with one of the dictionaries in Pack/ZsDic.pack.zs (a SARC of
zs.zsdic, bcett.byml.zsdic and pack.zsdic; the frame header names the dictionary by id). The approach is the one of
tools/make_romfs_patches.py.
"""
import compression.zstd as zstd
import fnmatch
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DICT_PACK = 'Pack/ZsDic.pack.zs'
ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
NO_DICTIONARY = ('.bntx.zs', '.ta.zs', '.vsts.zs', '.bars.zs', '.rsizetable.zs')


def default_game_dir():
    """--game, else TOTK_GAME, else the folder named Game next to the repository (or next to the main checkout of a
    worktree), else None."""
    env = os.environ.get('TOTK_GAME')
    if env:
        return Path(env)
    for base in (ROOT.parent, ROOT.parent.parent):
        if (base / 'Game/romfs/index.json').is_file():
            return base / 'Game'
    return None


class RomFS:
    def __init__(self, game_dir=None):
        game_dir = Path(game_dir) if game_dir else default_game_dir()
        if not game_dir or not (game_dir / 'romfs/index.json').is_file():
            raise FileNotFoundError('no game folder with romfs/index.json: pass --game or set TOTK_GAME')
        self.game_dir = game_dir
        manifest = json.loads((game_dir / 'romfs/index.json').read_text(encoding='utf-8'))
        if manifest.get('status') != 'pass':
            raise ValueError(f'{game_dir}/romfs/index.json does not record a verified extraction')
        self.files = {f['path']: f for f in manifest['files']}
        self.image_path = game_dir / 'romfs/romfs.bin'
        self._image = None
        self._dicts = None

    def __contains__(self, path):
        return path in self.files

    def search(self, pattern, regex=False):
        """Paths matching a glob (case-insensitive, * crosses /) or a regex (search, not full match)."""
        if regex:
            r = re.compile(pattern, re.IGNORECASE)
            return sorted(p for p in self.files if r.search(p))
        r = re.compile(fnmatch.translate(pattern), re.IGNORECASE)
        return sorted(p for p in self.files if r.match(p))

    def read_raw(self, path):
        """The bytes of a file as stored (compressed when it ends in .zs)."""
        f = self.files[path]
        if self._image is None:
            self._image = open(self.image_path, 'rb')
        self._image.seek(f['offset'])
        data = self._image.read(f['size'])
        if len(data) != f['size']:
            raise IOError(f'{path}: short read')
        return data

    def read(self, path):
        """The bytes of a file, decompressed when stored as a zstd frame."""
        return self.decompress(self.read_raw(path))

    @property
    def dictionaries(self):
        """dictionary id -> (member name in Pack/ZsDic.pack.zs, ZstdDict)."""
        if self._dicts is None:
            from . import sarc
            pack = sarc.Sarc(zstd.decompress(self.read_raw(DICT_PACK)))
            self._dicts = {}
            for name, data in pack.files.items():
                d = zstd.ZstdDict(data)
                self._dicts[d.dict_id] = (name, d)
        return self._dicts

    def dictionary_for(self, raw):
        """The ZstdDict a zstd frame was compressed with, or None."""
        dict_id = zstd.get_frame_info(raw).dictionary_id
        if not dict_id:
            return None
        return self.dictionaries[dict_id][1]

    def decompress(self, raw):
        if raw[:4] != ZSTD_MAGIC:
            return raw
        return zstd.decompress(raw, zstd_dict=self.dictionary_for(raw))

    def compress_like(self, data, path, level=19):
        """data compressed the way the game file at path is: the same dictionary (or none), a zstd frame. A path the
        RomFS does not have (an added file) takes the dictionary its name calls for (see dictionary_for_name)."""
        if path in self.files:
            raw = self.read_raw(path)
            if raw[:4] != ZSTD_MAGIC:
                return data
            d = self.dictionary_for(raw)
        else:
            if not path.endswith('.zs'):
                return data
            d = self.dictionary_for_name(path)
        out = zstd.compress(data, level=level, zstd_dict=d)
        if zstd.decompress(out, zstd_dict=d) != data:
            raise AssertionError('zstd round trip failed')
        return out

    def dictionary_for_name(self, path):
        """The dictionary for a .zs file the RomFS does not have, by the rule the game's files follow (measured over
        every .zs file of 1.2.1 by frame_dictionary_id): *.bcett.byml.zs bcett.byml.zsdic, *.pack.zs pack.zsdic (all
        but Pack/ZsDic.pack.zs itself), *.bntx.zs, *.ta.zs, *.vsts.zs, *.bars.zs and the size table none, everything
        else zs.zsdic (all but two files, System/Resource/HeapDef and one .atbl.byml.zs)."""
        names = {name: d for name, d in self.dictionaries.values()}
        if path.endswith('.bcett.byml.zs'):
            return names['bcett.byml.zsdic']
        if path.endswith('.pack.zs'):
            return names['pack.zsdic']
        if path.endswith(NO_DICTIONARY):
            return None
        return names['zs.zsdic']

    def frame_dictionary_id(self, path):
        """The dictionary id in the zstd frame header of a RomFS file (0: none), read from its first bytes."""
        f = self.files[path]
        if self._image is None:
            self._image = open(self.image_path, 'rb')
        self._image.seek(f['offset'])
        head = self._image.read(min(18, f['size']))
        if head[:4] != ZSTD_MAGIC:
            return 0
        descriptor = head[4]
        size = (0, 1, 2, 4)[descriptor & 3]
        at = 5 if descriptor & 0x20 else 6   # single-segment frames have no window byte
        return int.from_bytes(head[at:at + size], 'little')

    def close(self):
        if self._image:
            self._image.close()
            self._image = None

    __del__ = close
