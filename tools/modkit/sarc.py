"""SARC archives (.pack, .sarc, .blarc, .bfarc): read, and write back byte for byte.

Layout (little endian in TotK): SARC header (magic, u16 header size 0x14, u16 BOM FEFF, u32 file size, u32 data
start, u16 version 0x0100, u16 pad), SFAT (magic, u16 header size 0xC, u16 node count, u32 hash key 0x65), one 16-byte
node per member sorted by name hash (u32 hash, u32 attribute = 0x01000000 | name offset / 4, u32 data begin, u32 data
end, both relative to the data start), SFNT (magic, u16 header size 8, u16 pad), the names NUL-terminated and padded
to 4, then the member data.

The game's archives store names and data in node (hash) order, each member at the alignment its format needs
(alignment_for, inferred from the padding in every archive of the 1.2.1 RomFS), the data start at the largest
alignment among the members. Writing follows the same rules, so an archive read from the game and written back is
byte-identical (tests/modkit_test.py) and an edited or added member lands where the game's tools would put it.
"""
import struct

HASH_KEY = 0x65

# Member alignment by the first four bytes of the member, then by its extension. Everything else: 8.
ALIGN_BY_MAGIC = {
    b'BNTX': 0x1000, b'BNSH': 0x1000, b'BAHS': 0x1000, b'FRES': 0x2000, b'Gfx2': 0x100,
    b'FLAN': 0x10, b'FLYT': 0x10, b'FCPX': 0x10,
}
ALIGN_BY_EXT = {'bfotf': 0x10, 'bfttf': 0x10, 'glsl': 0x10, 'bfres': 0x2000,
                'hght': 4, 'mate': 4, 'extm': 4,   # TerrainArc/*.ta.zs members, packed without padding
                'skybin': 4}


def name_hash(name, key=HASH_KEY):
    h = 0
    for b in name.encode('utf-8'):
        h = (h * key + (b - 256 if b >= 0x80 else b)) & 0xFFFFFFFF   # bytes hashed as signed chars
    return h


def alignment_for(name, body):
    a = ALIGN_BY_MAGIC.get(bytes(body[:4]))
    if a is None:
        a = ALIGN_BY_EXT.get(name.rsplit('.', 1)[-1], 8)
    return a


def is_sarc(data):
    return data[:4] == b'SARC'


class Sarc:
    """files: name -> bytes. Add, replace or delete members, then write()."""

    def __init__(self, data=None):
        self.files = {}
        if data is not None:
            self._read(bytes(data))

    def _read(self, data):
        if data[:4] != b'SARC':
            raise ValueError('not a SARC archive')
        if data[6:8] != b'\xff\xfe':
            raise ValueError('big-endian SARC is not supported (TotK uses little endian)')
        header, size, start = struct.unpack_from('<HxxII', data, 4)
        if size != len(data):
            raise ValueError(f'SARC size field {size} != {len(data)}')
        if data[header:header + 4] != b'SFAT':
            raise ValueError('no SFAT')
        count = struct.unpack_from('<H', data, header + 6)[0]
        names = header + 12 + count * 16
        if data[names:names + 4] != b'SFNT':
            raise ValueError('no SFNT')
        names += 8
        for i in range(count):
            h, attr, lo, hi = struct.unpack_from('<4I', data, header + 12 + i * 16)
            if not attr >> 24:
                raise ValueError('SARC member without a name: not supported')
            off = names + (attr & 0xFFFFFF) * 4
            self.files[data[off:data.index(0, off, start)].decode('utf-8')] = data[start + lo:start + hi]

    def write(self):
        order = sorted(self.files, key=name_hash)
        hashes = [name_hash(n) for n in order]
        if len(set(hashes)) != len(hashes):
            raise ValueError('two member names with the same hash')
        table, name_at = bytearray(), {}
        for n in order:
            name_at[n] = len(table)
            table += n.encode('utf-8') + b'\0'
            table += bytes(-len(table) % 4)
        aligns = {n: alignment_for(n, self.files[n]) for n in order}
        start = 0x14 + 12 + 16 * len(order) + 8 + len(table)
        start += -start % max(aligns.values(), default=8)
        body, spans = bytearray(), {}
        for n in order:
            body += bytes(-len(body) % aligns[n])
            spans[n] = (len(body), len(body) + len(self.files[n]))
            body += self.files[n]
        out = bytearray(b'SARC' + struct.pack('<HHIIHH', 0x14, 0xFEFF, 0, start, 0x100, 0))
        out += b'SFAT' + struct.pack('<HHI', 12, len(order), HASH_KEY)
        for n, h in zip(order, hashes):
            out += struct.pack('<4I', h, 0x01000000 | name_at[n] // 4, *spans[n])
        out += b'SFNT' + struct.pack('<HH', 8, 0) + table
        out += bytes(start - len(out)) + body
        struct.pack_into('<I', out, 8, len(out))
        return bytes(out)
