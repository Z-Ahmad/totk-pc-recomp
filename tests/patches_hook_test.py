"""recomp/patches.py `hook` lines: parsing, the checks and the runtime header. No game files.

Run: .venv\\Scripts\\python tests\\patches_hook_test.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'recomp'))
import patches  # noqa: E402

MODS = [('main', 0x7000000000, 0x472b000), ('subsdk0', 0x7004800000, 0x6a9000)]


def load(text):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'patches.txt'
        path.write_text(text)
        return patches.load(path, MODS)


class HookLines(unittest.TestCase):
    def test_parsed(self):
        t = load('set a ENV_A 0\nset b ENV_B 1\nhook b main 8f26c8 my_hook  # comment\n')
        self.assertEqual(t.hooks, {'main': {0x8f26c8: (1, 'my_hook')}})
        self.assertEqual(t.hooks_for('main', 0x7000000000), {0x70008f26c8: (1, 'my_hook')})
        self.assertEqual(t.hooks_for('subsdk0', 0x7004800000), {})

    def test_header_lists_hooks(self):
        text = patches.header_text(load('set a ENV_A 0\nhook a main 10 h1\nhook a subsdk0 20 h2\n'), 'MARKER')
        self.assertIn('#define RT_PATCH_HOOKS(X) X(0, "main", 0x10, h1) X(0, "subsdk0", 0x20, h2)', text)

    def test_header_without_hooks(self):
        self.assertIn('#define RT_PATCH_HOOKS(X) \n', patches.header_text(load('set a ENV_A 0\n'), 'MARKER'))

    def test_errors(self):
        for text, why in (('hook a main 10 h\n', 'unknown set'),
                          ('set a E 0\nhook a nosuch 10 h\n', 'not in the layout'),
                          ('set a E 0\nhook a main 10 2bad\n', 'not a C function name'),
                          ('set a E 0\nhook a main 10 h\nhook a main 10 g\n', 'hooked twice'),
                          ('set a E 0\nhook a main 10\n', 'cannot parse')):
            with self.subTest(why=why), self.assertRaisesRegex(patches.PatchError, why):
                load(text)


if __name__ == '__main__':
    unittest.main()
