"""YAML text of BYML and MSBT documents (needs PyYAML: tools/modkit/requirements.txt).

BYML values map to YAML like this:
  dictionary / array            mapping / sequence (arrays of scalars on one line)
  string, bool, null            plain YAML scalars (strings that look like numbers are quoted)
  s32 / f32                     plain integer / plain number with a fraction or exponent (1.0, not 1)
  u32 / s64 / u64 / f64         !u 5, !l -5, !ul 5, !f64 0.5
  binary / aligned binary       !!binary <base64> / !abin {align: 8, data: <hex>}
A document is a mapping: version, big_endian, share_containers (how the file is stored; keep them as they are) and
root.
"""
import base64
import math

import yaml

from . import byml

Dumper = getattr(yaml, 'CSafeDumper', yaml.SafeDumper)
Loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


class _Dumper(Dumper):
    pass


class _Loader(Loader):
    pass


def _float_text(v):
    if math.isnan(v):
        return '.nan'
    if math.isinf(v):
        return '.inf' if v > 0 else '-.inf'
    return byml.f32_repr(v)


def _scalar_list(v):
    return all(not isinstance(x, (dict, list, bytes)) for x in v)


_Dumper.add_representer(byml.Float, lambda d, v: d.represent_scalar('tag:yaml.org,2002:float', _float_text(v)))
_Dumper.add_representer(float, lambda d, v: d.represent_scalar('tag:yaml.org,2002:float', _float_text(v)))
_Dumper.add_representer(byml.UInt, lambda d, v: d.represent_scalar('!u', str(int(v))))
_Dumper.add_representer(byml.Int64, lambda d, v: d.represent_scalar('!l', str(int(v))))
_Dumper.add_representer(byml.UInt64, lambda d, v: d.represent_scalar('!ul', str(int(v))))
_Dumper.add_representer(byml.Double, lambda d, v: d.represent_scalar('!f64', repr(float(v))))
_Dumper.add_representer(bytes, lambda d, v: d.represent_scalar('tag:yaml.org,2002:binary',
                                                               base64.b64encode(v).decode(), style='|'))
_Dumper.add_representer(byml.AlignedBinary, lambda d, v: d.represent_mapping(
    '!abin', {'align': v.alignment, 'data': bytes(v).hex()}, flow_style=True))
_Dumper.add_representer(list, lambda d, v: d.represent_sequence('tag:yaml.org,2002:seq', v,
                                                                flow_style=bool(v) and _scalar_list(v) and len(v) <= 16))
_Dumper.add_representer(str, lambda d, v: d.represent_scalar('tag:yaml.org,2002:str', v,
                                                              style='|' if '\n' in v and v.strip() == v else None))
_Dumper.add_representer(dict,lambda d, v: d.represent_mapping('tag:yaml.org,2002:map', v.items()))


def _int(loader, node):
    v = loader.construct_yaml_int(node)
    if not -2**31 <= v < 2**31:
        raise yaml.constructor.ConstructorError(None, None, f'{v} does not fit s32: tag it !u, !l or !ul', node.start_mark)
    return v


_Loader.add_constructor('tag:yaml.org,2002:int', _int)


def _float(loader, node):
    v = loader.construct_yaml_float(node)
    return byml.Float(math.nan if math.isnan(v) else v)   # PyYAML's .nan has the sign bit set


_Loader.add_constructor('tag:yaml.org,2002:float', _float)
_Loader.add_constructor('!u', lambda l, n: byml.UInt(int(l.construct_scalar(n), 0)))
_Loader.add_constructor('!l', lambda l, n: byml.Int64(int(l.construct_scalar(n), 0)))
_Loader.add_constructor('!ul', lambda l, n: byml.UInt64(int(l.construct_scalar(n), 0)))
_Loader.add_constructor('!f64', lambda l, n: byml.Double(float(l.construct_scalar(n))))


def _abin(loader, node):
    m = loader.construct_mapping(node)
    return byml.AlignedBinary(bytes.fromhex(m['data']), m['align'])


_Loader.add_constructor('!abin', _abin)
_Dumper.add_representer(byml.HashDict32, lambda d, v: d.represent_mapping('!h32', v.items()))
_Dumper.add_representer(byml.HashDict64, lambda d, v: d.represent_mapping('!h64', v.items()))


def _hashdict(cls):
    def construct(loader, node):
        out = cls()
        yield out
        for knode, vnode in node.value:   # keys are u32 / u64 numbers, past the s32 range plain integers have
            try:
                k = int(loader.construct_scalar(knode), 0)
            except ValueError:
                raise yaml.constructor.ConstructorError(None, None, 'hash dictionary keys are numbers', knode.start_mark)
            out[k] = loader.construct_object(vnode, deep=True)
    return construct


_Loader.add_constructor('!h32', _hashdict(byml.HashDict32))
_Loader.add_constructor('!h64', _hashdict(byml.HashDict64))


def dump(data):
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False)


def load(text):
    return yaml.load(text, Loader=_Loader)


def dump_byml(doc):
    return dump({**doc.header(), 'root': doc.root})


def load_byml(text):
    d = load(text)
    return byml.Document(d['root'], d.get('version', 7), d.get('big_endian', False), d.get('share_containers', True))
