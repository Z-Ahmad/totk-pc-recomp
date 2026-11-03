"""BYML (binary YAML; .byml, .bgyml, .bcett.byml): read into Python values, write back, convert to YAML or JSON.

TotK files are little endian ("YB"), version 7 (a few are 5 or 6; the layout is the same). Header: magic, u16
version, u32 offset of the key table, u32 offset of the string table, u32 offset of the root (0 for an empty file).

Nodes, by type byte:
  A0 string (u32 index into the string table)        D0 bool    D1 s32    D2 f32    D3 u32
  A1 binary (offset to u32 size + bytes)             D4 s64     D5 u64    D6 f64    (offset to 8 bytes)
  A2 aligned binary (offset to u32 size, u32 alignment, bytes)                       FF null
  C0 array (u24 count, count type bytes padded to 4, count u32 values)
  C1 dictionary (u24 count, entries of u24 key index, u8 type, u32 value; sorted by key)
  C2 key or string table (u24 count, count + 1 u32 offsets from the node, NUL-terminated strings)
  20 / 21 hash dictionary (u24 count, entries of u32 / u64 key and u32 value sorted by key, count type bytes padded
  to 4); version 7. Voice/BwavInfo/*.byml.zs and two files of Pack/Bootup.Nin_NX_NVN.pack.zs have them.

Python values: dict, list, str, bool, int (s32), float (f32), None, and the wrappers below for the other types.

Writing follows the layout of the game's files: header, key table, string table (both sorted by their UTF-8 bytes),
then every 64-bit value and binary in depth-first order, then every container in depth-first pre-order, 4-aligned.
Dictionary entries are stored sorted by key; children are visited in the dict's own order (read() keeps the order the
file stores containers in). Some files store each equal container once, others store every copy; read() reports which
(share_containers) and write() takes it. Over the whole 1.2.1 RomFS (loose files and archive members) that gives
470,733 files back byte for byte. 196 come back semantically equal and smaller: 195 map *_Static.bcett.byml.zs files
and Game/TravelerInfo/TravelerInfo.byml.zs, where the game's writer shares only some of the equal containers, by a
rule not worked out yet; this writer shares all of them (the game's reader follows offsets, so a shared node reads
like a copy). tests/modkit_test.py checks a sample; docs/modding/formats.md has the numbers.
"""
import math
import struct

# ---------------------------------------------------------------- value types


class UInt(int):
    """u32 (D3)."""


class Int64(int):
    """s64 (D4)."""


class UInt64(int):
    """u64 (D5)."""


class Double(float):
    """f64 (D6)."""


class Float(float):
    """f32 (D2). Plain Python floats are written as f32 too; this type only marks values read from a file."""


class AlignedBinary(bytes):
    """A2: bytes with an alignment."""

    def __new__(cls, data, alignment):
        obj = super().__new__(cls, data)
        obj.alignment = alignment
        return obj


class HashDict32(dict):
    """20: a dictionary keyed by u32 numbers (hashes) instead of key-table strings."""


class HashDict64(dict):
    """21: the same with u64 keys."""


INLINE = {0xA0, 0xD0, 0xD1, 0xD2, 0xD3, 0xFF}
LONG = {0xD4, 0xD5, 0xD6, 0xA1, 0xA2}
CONTAINERS = {0xC0, 0xC1, 0x20, 0x21}


class BymlError(ValueError):
    pass


# ---------------------------------------------------------------- reading

def _table(data, off, e):
    if not off:
        return []
    if data[off] != 0xC2:
        raise BymlError(f'expected a string table at 0x{off:x}')
    n = int.from_bytes(data[off + 1:off + 4], 'big' if e == '>' else 'little')
    offs = struct.unpack_from(f'{e}{n + 1}I', data, off + 4)
    return [data[off + offs[i]:data.index(0, off + offs[i])].decode('utf-8') for i in range(n)]


class Document:
    """A BYML file: its root (None for an empty file) and how it is stored."""

    def __init__(self, root, version=7, big_endian=False, share_containers=True):
        self.root, self.version, self.big_endian, self.share_containers = root, version, big_endian, share_containers

    def to_bytes(self):
        return write(self.root, self.version, self.big_endian, self.share_containers)

    def header(self):
        return {'version': self.version, 'big_endian': self.big_endian, 'share_containers': self.share_containers}


def read(data):
    """The Document of BYML bytes."""
    data = bytes(data)
    if data[:2] == b'YB':
        e, bo = '<', 'little'
    elif data[:2] == b'BY':
        e, bo = '>', 'big'
    else:
        raise BymlError('not a BYML file')
    version, keys_at, strings_at, root_at = struct.unpack_from(e + 'HIII', data, 2)
    keys, strings = _table(data, keys_at, e), _table(data, strings_at, e)
    seen, shared = set(), [False]

    def value(t, raw):
        if t == 0xA0:
            return strings[raw]
        if t == 0xD0:
            return bool(raw)
        if t == 0xD1:
            return struct.unpack('<i', struct.pack('<I', raw))[0]
        if t == 0xD2:
            return Float(struct.unpack('<f', struct.pack('<I', raw))[0])
        if t == 0xD3:
            return UInt(raw)
        if t == 0xFF:
            return None
        if t == 0xD4:
            return Int64(struct.unpack_from(e + 'q', data, raw)[0])
        if t == 0xD5:
            return UInt64(struct.unpack_from(e + 'Q', data, raw)[0])
        if t == 0xD6:
            return Double(struct.unpack_from(e + 'd', data, raw)[0])
        if t == 0xA1:
            n = struct.unpack_from(e + 'I', data, raw)[0]
            return data[raw + 4:raw + 4 + n]
        if t == 0xA2:
            n, align = struct.unpack_from(e + 'II', data, raw)
            return AlignedBinary(data[raw + 8:raw + 8 + n], align)
        if t in CONTAINERS:
            if raw in seen:
                shared[0] = True
            seen.add(raw)
            return node(raw)
        raise BymlError(f'node type 0x{t:02x} is not supported')

    def node(off):
        t = data[off]
        n = int.from_bytes(data[off + 1:off + 4], bo)
        if t == 0xC0:
            types = data[off + 4:off + 4 + n]
            at = off + 4 + ((n + 3) & ~3)
            return [value(types[i], struct.unpack_from(e + 'I', data, at + 4 * i)[0]) for i in range(n)]
        if t == 0xC1:
            entries = []
            for i in range(n):
                at = off + 4 + 8 * i
                entries.append((keys[int.from_bytes(data[at:at + 3], bo)], data[at + 3],
                                struct.unpack_from(e + 'I', data, at + 4)[0]))
            # Keys in sorted order, except that the containers among them follow the order the file stores them in
            # (the order of the source the game's tools wrote it from); the writer walks them in this order.
            slots = [i for i, (_, t, _) in enumerate(entries) if t in CONTAINERS]
            moved = sorted((entries[i] for i in slots), key=lambda x: x[2])
            for i, x in zip(slots, moved):
                entries[i] = x
            return {k: value(t, raw) for k, t, raw in entries}
        if t in (0x20, 0x21):
            entry = e + ('II' if t == 0x20 else 'QI')
            size = struct.calcsize(entry)
            types = off + 4 + size * n
            out = HashDict32() if t == 0x20 else HashDict64()
            for i in range(n):
                key, raw = struct.unpack_from(entry, data, off + 4 + size * i)
                out[key] = value(data[types + i], raw)
            return out
        raise BymlError(f'node type 0x{t:02x} at 0x{off:x} is not supported')

    root = node(root_at) if root_at else None
    return Document(root, version, e == '>', shared[0])


# ---------------------------------------------------------------- writing

def _type(v):
    if v is None:
        return 0xFF
    if isinstance(v, bool):
        return 0xD0
    if isinstance(v, str):
        return 0xA0
    if isinstance(v, UInt64):
        return 0xD5
    if isinstance(v, Int64):
        return 0xD4
    if isinstance(v, UInt):
        return 0xD3
    if isinstance(v, int):
        return 0xD1
    if isinstance(v, Double):
        return 0xD6
    if isinstance(v, float):
        return 0xD2
    if isinstance(v, AlignedBinary):
        return 0xA2
    if isinstance(v, (bytes, bytearray)):
        return 0xA1
    if isinstance(v, list):
        return 0xC0
    if isinstance(v, HashDict64):
        return 0x21
    if isinstance(v, HashDict32):
        return 0x20
    if isinstance(v, dict):
        return 0xC1
    raise BymlError(f'cannot store {type(v).__name__} in BYML')


def _freeze(v):
    """A hashable key that tells apart values the file stores differently (type and bits)."""
    t = _type(v)
    if t == 0xC0:
        return (t, tuple(_freeze(x) for x in v))
    if t == 0xC1:
        return (t, tuple((k, _freeze(x)) for k, x in sorted(v.items(), key=lambda kv: kv[0].encode())))
    if t in (0x20, 0x21):
        return (t, tuple((k, _freeze(x)) for k, x in sorted(v.items())))
    if t in (0xD2, 0xD6):
        return (t, struct.pack('<d', v))
    if t == 0xA2:
        return (t, bytes(v), v.alignment)
    return (t, v)


def _u32_of(t, v):
    if t == 0xD0:
        return int(v)
    if t == 0xD1:
        return v & 0xFFFFFFFF
    if t == 0xD2:
        return struct.unpack('<I', struct.pack('<f', v))[0]
    if t == 0xD3:
        return v
    if t == 0xFF:
        return 0
    raise AssertionError(t)


def _children(d):
    """The values of a dictionary in the order the writer visits them: by key, except that the containers among them
    keep the dictionary's own order (read() gives them the order the file stores them in). Arrays: in order; hash
    dictionaries: by key."""
    if isinstance(d, list):
        return d
    if isinstance(d, (HashDict32, HashDict64)):
        return [x for _, x in sorted(d.items())]
    items = sorted(d.items(), key=lambda kv: kv[0].encode())
    containers = iter([x for x in d.values() if _type(x) in CONTAINERS])
    return [next(containers) if _type(x) in CONTAINERS else x for _, x in items]


class _Writer:
    def __init__(self, root, version, big_endian=False, share_containers=False):
        self.root, self.version = root, version
        self.share_containers = share_containers
        self.e, self.bo = ('>', 'big') if big_endian else ('<', 'little')
        self.keys, self.strings = set(), set()
        if root is not None:
            self._collect(root)
        self.keys = sorted(self.keys, key=lambda s: s.encode())
        self.strings = sorted(self.strings, key=lambda s: s.encode())
        self.key_index = {k: i for i, k in enumerate(self.keys)}
        self.string_index = {s: i for i, s in enumerate(self.strings)}

    def _collect(self, v):
        t = _type(v)
        if t == 0xA0:
            self.strings.add(v)
        elif t == 0xC0:
            for x in v:
                self._collect(x)
        elif t == 0xC1:
            for k, x in v.items():
                self.keys.add(k)
                self._collect(x)
        elif t in (0x20, 0x21):
            for x in v.values():
                self._collect(x)

    def _table(self, strings):
        if not strings:
            return b''
        encoded = [s.encode('utf-8') + b'\0' for s in strings]
        out = bytearray(b'\xc2' + len(strings).to_bytes(3, self.bo))
        at = 4 + 4 * (len(strings) + 1)
        for e in encoded:
            out += struct.pack(self.e + 'I', at)
            at += len(e)
        out += struct.pack(self.e + 'I', at)
        for e in encoded:
            out += e
        return bytes(out)

    def write(self):
        if self.root is not None and _type(self.root) not in CONTAINERS:
            raise BymlError('the root must be a dictionary or an array')
        out = bytearray(16)
        keys_at = strings_at = 0
        if self.keys:
            keys_at = len(out)
            out += self._table(self.keys)
            out += bytes(-len(out) % 4)
        if self.strings:
            strings_at = len(out)
            out += self._table(self.strings)
            out += bytes(-len(out) % 4)
        root_at = 0
        if self.root is not None:
            # 64-bit values and binaries, depth-first, one per reference (a shared container's once). A binary is not
            # padded after, the game's files run the next value on unaligned.
            self.long_at = {}
            for v in self._walk_long(self.root, set()):
                t = _type(v)
                if t == 0xA2:
                    out += bytes(-(len(out) + 8) % max(v.alignment, 4))
                self.long_at[id(v)] = len(out)
                if t == 0xD4:
                    out += struct.pack(self.e + 'q', v)
                elif t == 0xD5:
                    out += struct.pack(self.e + 'Q', v)
                elif t == 0xD6:
                    out += struct.pack(self.e + 'd', v)
                elif t == 0xA1:
                    out += struct.pack(self.e + 'I', len(v)) + v
                else:
                    out += struct.pack(self.e + 'II', len(v), v.alignment) + v
            out += bytes(-len(out) % 4)
            # Containers, depth-first pre-order, each distinct one stored once.
            self.node_at = {}
            order = []
            self._place(self.root, out_len=[len(out)], order=order)
            for v in order:
                out += self._container(v)
            root_at = self.node_at[self._key(self.root)]
        struct.pack_into(self.e + '2sHIII', out, 0, b'BY' if self.e == '>' else b'YB', self.version, keys_at, strings_at, root_at)
        return bytes(out)

    def _walk_long(self, v, seen):
        t = _type(v)
        if t in LONG:
            yield v
            return
        if t not in CONTAINERS:
            return
        k = self._key(v)
        if k in seen:
            return
        seen.add(k)
        for x in _children(v):
            yield from self._walk_long(x, seen)

    @staticmethod
    def _size(v):
        n, t = len(v), _type(v)
        if t == 0xC0:
            return 4 + ((n + 3) & ~3) + 4 * n
        if t == 0xC1:
            return 4 + 8 * n
        return 4 + (8 if t == 0x20 else 12) * n + ((n + 3) & ~3)

    def _key(self, v):
        return _freeze(v) if self.share_containers else id(v)

    def _place(self, v, out_len, order):
        f = self._key(v)
        if f in self.node_at:
            return
        self.node_at[f] = out_len[0]
        out_len[0] += self._size(v)
        order.append(v)
        for x in _children(v):
            if _type(x) in CONTAINERS:
                self._place(x, out_len, order)

    def _ref(self, x):
        t = _type(x)
        if t == 0xA0:
            return t, self.string_index[x]
        if t in LONG:
            return t, self.long_at[id(x)]
        if t in CONTAINERS:
            return t, self.node_at[self._key(x)]
        return t, _u32_of(t, x)

    def _container(self, v):
        if isinstance(v, list):
            refs = [self._ref(x) for x in v]
            out = bytearray(b'\xc0' + len(v).to_bytes(3, self.bo))
            out += bytes(t for t, _ in refs)
            out += bytes(-len(out) % 4)
            for _, r in refs:
                out += struct.pack(self.e + 'I', r)
            return out
        t = _type(v)
        if t in (0x20, 0x21):
            refs = [(k, self._ref(x)) for k, x in sorted(v.items())]
            out = bytearray(bytes([t]) + len(v).to_bytes(3, self.bo))
            for k, (_, r) in refs:
                out += struct.pack(self.e + ('II' if t == 0x20 else 'QI'), k, r)
            out += bytes(tt for _, (tt, _) in refs)
            out += bytes(-len(out) % 4)
            return out
        out = bytearray(b'\xc1' + len(v).to_bytes(3, self.bo))
        for k in sorted(v, key=lambda s: s.encode()):
            t, r = self._ref(v[k])
            out += self.key_index[k].to_bytes(3, self.bo) + bytes([t]) + struct.pack(self.e + 'I', r)
        return out


def write(root, version=7, big_endian=False, share_containers=False):
    return _Writer(root, version, big_endian, share_containers).write()


# ---------------------------------------------------------------- text forms

def f32_repr(v):
    """The shortest decimal that reads back as the same f32."""
    if math.isnan(v) or math.isinf(v):
        return repr(v)
    bits = struct.pack('<f', v)
    for p in range(1, 18):
        s = f'{v:.{p}g}'
        try:
            if struct.pack('<f', float(s)) == bits:
                break
        except OverflowError:   # rounded up past the largest f32
            pass
    s = repr(float(s))   # the same number without an exponent where Python would not use one (1500.0, not 1.5e+03)
    # YAML 1.1 reads a number as a float only with a '.' in it (-4.0e+01, not -4e+01).
    mantissa, _, exponent = s.partition('e')
    if '.' not in mantissa:
        mantissa += '.0'
    return mantissa + ('e' + exponent if exponent else '')


def to_json_value(v):
    """A JSON-safe form: the types JSON cannot tell apart become one-key objects ({"!u": 5}, {"!l": ..}, {"!ul": ..},
    {"!f64": ..}, {"!f32": "nan"}, {"!bin": hex}, {"!abin": hex, "align": n})."""
    t = _type(v)
    if t in (0x20, 0x21):
        return {'!h32' if t == 0x20 else '!h64': {str(k): to_json_value(x) for k, x in v.items()}}
    if t == 0xC1:
        return {k: to_json_value(x) for k, x in v.items()}
    if t == 0xC0:
        return [to_json_value(x) for x in v]
    if t == 0xD3:
        return {'!u': int(v)}
    if t == 0xD4:
        return {'!l': int(v)}
    if t == 0xD5:
        return {'!ul': int(v)}
    if t == 0xD6:
        return {'!f64': float(v) if math.isfinite(v) else repr(float(v))}
    if t == 0xD2:
        if not math.isfinite(v):
            return {'!f32': repr(float(v))}
        return _JsonF32(v)
    if t == 0xA1:
        return {'!bin': bytes(v).hex()}
    if t == 0xA2:
        return {'!abin': bytes(v).hex(), 'align': v.alignment}
    return v


class _JsonF32(float):
    def __repr__(self):
        return f32_repr(self)


def from_json_value(v):
    if isinstance(v, dict):
        if len(v) == 1:
            (k, x), = v.items()
            if k == '!u':
                return UInt(x)
            if k == '!l':
                return Int64(x)
            if k == '!ul':
                return UInt64(x)
            if k == '!f64':
                return Double(float(x))
            if k == '!f32':
                return Float(float(x))
            if k == '!bin':
                return bytes.fromhex(x)
            if k in ('!h32', '!h64'):
                cls = HashDict32 if k == '!h32' else HashDict64
                return cls((int(kk), from_json_value(xx)) for kk, xx in x.items())
        if set(v) == {'!abin', 'align'}:
            return AlignedBinary(bytes.fromhex(v['!abin']), v['align'])
        return {k: from_json_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [from_json_value(x) for x in v]
    if isinstance(v, float):
        return Float(v)
    return v


def to_json(doc):
    """JSON text of a Document: {"version", "big_endian", "share_containers", "root"}. f32 values are written in
    their shortest form; a JSON number with a fraction or exponent reads back as f32, one without as s32."""
    import json

    def emit(v, indent):
        pad, inner = ' ' * indent, ' ' * (indent + 1)
        if isinstance(v, _JsonF32):
            return f32_repr(v)
        if isinstance(v, dict):
            if not v:
                return '{}'
            if all(k in ('!u', '!l', '!ul', '!f64', '!f32', '!bin', '!abin', 'align') for k in v):   # a typed scalar
                return json.dumps(v, ensure_ascii=False)
            items = [f'{inner}{json.dumps(k, ensure_ascii=False)}: {emit(x, indent + 1)}' for k, x in v.items()]
            return '{\n' + ',\n'.join(items) + '\n' + pad + '}'
        if isinstance(v, list):
            if not v:
                return '[]'
            return '[\n' + ',\n'.join(inner + emit(x, indent + 1) for x in v) + '\n' + pad + ']'
        return json.dumps(v, ensure_ascii=False)
    return emit({**doc.header(), 'root': to_json_value(doc.root)}, 0) + '\n'


def from_json(text):
    import json
    d = json.loads(text)
    return Document(from_json_value(d['root']), d.get('version', 7), d.get('big_endian', False),
                    d.get('share_containers', True))


def to_yaml(doc):
    from . import yamlio
    return yamlio.dump_byml(doc)


def from_yaml(text):
    from . import yamlio
    return yamlio.load_byml(text)
