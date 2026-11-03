"""MSBT text (LibMessageStudio binary text; the Mals/<language>.Product.<n>.sarc.zs archives hold them): read, write.

Header (0x20 bytes): "MsgStdBn", u16 BOM (FEFF), u16 0, u8 encoding (0 UTF-8, 1 UTF-16, 2 UTF-32), u8 version (3),
u16 section count, u16 0, u32 file size, padding. Each section: 4-byte magic, u32 size, 8 bytes 0, the data, padded
to 16 with 0xAB. Every TotK 1.2.1 file has LBL1 and TXT2 only, in UTF-16 (checked over USen; others are kept as raw
bytes and written back unchanged).

LBL1: u32 bucket count, per bucket u32 label count and u32 offset (from the section data), then the labels: u8
length, the name, u32 message index. A label goes into bucket hash % count, hash = h * 0x492 + byte over the name.
Within a bucket the labels are in message order.
TXT2: u32 message count, u32 offsets (from the section data), the messages, each ending in a NUL character. Inside a
message, U+000E starts a tag: u16 group, u16 type, u16 size in bytes, then that many bytes of parameters; U+000F
(u16 group, u16 type) closes one (no 1.2.1 file has a closing tag).

Text form of a message: the characters as they are, with tags written {{group.type}} or {{group.type:hex bytes}},
closing tags {{/group.type}}, and a literal { or \\ escaped with a backslash. What each tag means in TotK is not
documented here; docs/modding/formats.md lists the ones seen.
"""
import re
import struct

ENCODINGS = {0: 'utf-8', 1: 'utf-16-le', 2: 'utf-32-le'}
NAMES = {'utf-8': 0, 'utf-16': 1, 'utf-32': 2}
TAG = re.compile(r'\{\{(/?)(\d+)\.(\d+)(?::([0-9a-fA-F]*))?\}\}|\\([\\{])|([^\\{]+)|(.)', re.S)


class MsbtError(ValueError):
    pass


def label_hash(name, buckets):
    h = 0
    for b in name.encode('utf-8'):
        h = (h * 0x492 + b) & 0xFFFFFFFF
    return h % buckets


class Msbt:
    """messages: label -> text form, in message (TXT2) order. buckets: the LBL1 bucket count."""

    def __init__(self, data=None):
        self.messages = {}
        self.encoding = 'utf-16'
        self.version = 3
        self.buckets = 101
        self.sections = ['LBL1', 'TXT2']
        self.raw_sections = {}
        if data is not None:
            self._read(bytes(data))

    @property
    def _codec(self):
        return ENCODINGS[NAMES[self.encoding]]

    @property
    def _unit(self):
        return {'utf-8': 1, 'utf-16': 2, 'utf-32': 4}[self.encoding]

    def _read(self, data):
        if data[:8] != b'MsgStdBn':
            raise MsbtError('not an MSBT file')
        if data[8:10] != b'\xff\xfe':
            raise MsbtError('big-endian MSBT is not supported (TotK uses little endian)')
        enc, self.version, count, size = struct.unpack_from('<BBHxxI', data, 0x0C)
        if enc not in ENCODINGS:
            raise MsbtError(f'unknown encoding {enc}')
        self.encoding = {0: 'utf-8', 1: 'utf-16', 2: 'utf-32'}[enc]
        if size != len(data):
            raise MsbtError('size field does not match the file')
        pos, sections = 0x20, {}
        self.sections = []
        for _ in range(count):
            magic = data[pos:pos + 4].decode('ascii')
            n = struct.unpack_from('<I', data, pos + 4)[0]
            sections[magic] = data[pos + 16:pos + 16 + n]
            self.sections.append(magic)
            pos = (pos + 16 + n + 15) & ~15
        if 'LBL1' not in sections or 'TXT2' not in sections:
            raise MsbtError('LBL1 or TXT2 missing')
        for magic in self.sections:
            if magic not in ('LBL1', 'TXT2'):
                self.raw_sections[magic] = sections[magic]
        labels = self._read_labels(sections['LBL1'])
        texts = self._read_texts(sections['TXT2'])
        if sorted(labels.values()) != list(range(len(texts))):
            raise MsbtError('labels do not name every message exactly once')
        by_index = {i: name for name, i in labels.items()}
        self.messages = {by_index[i]: texts[i] for i in range(len(texts))}

    def _read_labels(self, sec):
        self.buckets = struct.unpack_from('<I', sec, 0)[0]
        labels = {}
        for g in range(self.buckets):
            n, at = struct.unpack_from('<II', sec, 4 + 8 * g)
            for _ in range(n):
                length = sec[at]
                name = sec[at + 1:at + 1 + length].decode('utf-8')
                labels[name] = struct.unpack_from('<I', sec, at + 1 + length)[0]
                at += 1 + length + 4
        return labels

    def _read_texts(self, sec):
        count = struct.unpack_from('<I', sec, 0)[0]
        offsets = list(struct.unpack_from(f'<{count}I', sec, 4)) + [len(sec)]
        return [self._decode(sec[offsets[i]:offsets[i + 1]]) for i in range(count)]

    def _char(self, b, j):
        u = self._unit
        return int.from_bytes(b[j:j + u], 'little')

    def _decode(self, b):
        u, out, j = self._unit, [], 0
        nul = bytes(u)
        if not b.endswith(nul):
            raise MsbtError('message without its terminating NUL')
        b = b[:-u]
        run = bytearray()

        def flush():
            if run:
                text = bytes(run).decode(self._codec)
                out.append(text.replace('\\', '\\\\').replace('{', '\\{'))
                run.clear()
        while j < len(b):
            c = self._char(b, j)
            if c == 0x0E:
                flush()
                g, t, n = (self._char(b, j + u * k) for k in (1, 2, 3))
                data = b[j + 4 * u:j + 4 * u + n]
                out.append(f'{{{{{g}.{t}:{data.hex()}}}}}' if n else f'{{{{{g}.{t}}}}}')
                j += 4 * u + n
            elif c == 0x0F:
                flush()
                g, t = self._char(b, j + u), self._char(b, j + 2 * u)
                out.append(f'{{{{/{g}.{t}}}}}')
                j += 3 * u
            else:
                if c == 0:
                    raise MsbtError('NUL inside a message')
                run += b[j:j + u]
                j += u
        flush()
        return ''.join(out)

    def _encode(self, text):
        u, codec = self._unit, self._codec
        out = bytearray()

        def ch(v):
            return v.to_bytes(u, 'little')
        for m in TAG.finditer(text):
            close, g, t, data, esc, plain, stray = m.groups()
            if g is not None:
                if close:
                    out += ch(0x0F) + ch(int(g)) + ch(int(t))
                else:
                    raw = bytes.fromhex(data or '')
                    out += ch(0x0E) + ch(int(g)) + ch(int(t)) + ch(len(raw)) + raw
            elif esc is not None:
                out += esc.encode(codec)
            elif plain is not None:
                out += plain.encode(codec)
            else:
                raise MsbtError(f'stray {stray!r} in message text: write \\{stray} for a literal one')
        return bytes(out) + bytes(u)

    def write(self):
        names = list(self.messages)
        index = {n: i for i, n in enumerate(names)}
        buckets = [[] for _ in range(self.buckets)]
        for n in names:
            buckets[label_hash(n, self.buckets)].append(n)
        lbl = bytearray(struct.pack('<I', self.buckets))
        at = 4 + 8 * self.buckets
        body = bytearray()
        for b in buckets:
            lbl += struct.pack('<II', len(b), at + len(body))
            for n in b:
                e = n.encode('utf-8')
                if len(e) > 255:
                    raise MsbtError(f'label {n!r} is longer than 255 bytes')
                body += bytes([len(e)]) + e + struct.pack('<I', index[n])
        lbl += body
        texts = [self._encode(self.messages[n]) for n in names]
        txt = bytearray(struct.pack('<I', len(texts)))
        at = 4 + 4 * len(texts)
        for t in texts:
            txt += struct.pack('<I', at)
            at += len(t)
        for t in texts:
            txt += t
        sections = {'LBL1': bytes(lbl), 'TXT2': bytes(txt), **self.raw_sections}
        out = bytearray(b'MsgStdBn' + struct.pack('<HHBBHHI', 0xFEFF, 0, NAMES[self.encoding], self.version,
                                                  len(self.sections), 0, 0) + bytes(10))
        for magic in self.sections:
            s = sections[magic]
            out += magic.encode('ascii') + struct.pack('<I', len(s)) + bytes(8) + s
            out += b'\xab' * (-len(out) % 16)
        struct.pack_into('<I', out, 0x12, len(out))
        return bytes(out)

    def header(self):
        h = {'encoding': self.encoding, 'version': self.version, 'label_buckets': self.buckets}
        if self.sections != ['LBL1', 'TXT2']:
            h['sections'] = self.sections
            h['raw_sections'] = {k: v.hex() for k, v in self.raw_sections.items()}
        return h

    @classmethod
    def from_dict(cls, d):
        m = cls()
        m.encoding = d.get('encoding', 'utf-16')
        m.version = d.get('version', 3)
        m.buckets = d.get('label_buckets', 101)
        m.sections = d.get('sections', ['LBL1', 'TXT2'])
        m.raw_sections = {k: bytes.fromhex(v) for k, v in d.get('raw_sections', {}).items()}
        m.messages = {str(k): str(v) for k, v in (d.get('messages') or {}).items()}
        return m

    def to_dict(self):
        return {**self.header(), 'messages': dict(self.messages)}


def to_json(m):
    import json
    return json.dumps(m.to_dict(), ensure_ascii=False, indent=1) + '\n'


def from_json(text):
    import json
    return Msbt.from_dict(json.loads(text))


def to_yaml(m):
    from . import yamlio
    return yamlio.dump(m.to_dict())


def from_yaml(text):
    from . import yamlio
    return Msbt.from_dict(yamlio.load(text))
