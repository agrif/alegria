import unittest

from .truth import TruthTable

class TestMany(unittest.TestCase):
    def test_iter(self):
        m = TruthTable.Many(range(3))
        self.assertEqual(list(iter(m)), [0, 1, 2])

    def test_len(self):
        m = TruthTable.Many(range(3))
        self.assertEqual(len(m), 3)

class TestGroup(unittest.TestCase):
    def test_iter(self):
        g = TruthTable.Group('foo', range(3))
        self.assertEqual(list(iter(g)), [0, 1, 2])

    def test_len(self):
        g = TruthTable.Group('foo', range(3))
        self.assertEqual(len(g), 3)

    def test_name(self):
        g = TruthTable.Group('foo', range(3))
        self.assertEqual(g.name, 'foo')

class TestRow(unittest.TestCase):
    def test_index(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(r['a'], 0)
        self.assertEqual(r['b'], 1)
        self.assertEqual(r['c'], 2)
        with self.assertRaises(KeyError):
            r['d']

    def test_attr(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(r.a, 0)
        self.assertEqual(r.b, 1)
        self.assertEqual(r.c, 2)
        with self.assertRaises(AttributeError):
            r.d

    def test_iter(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(list(iter(r)), ['a', 'b', 'c'])

    def test_len(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(len(r), 3)

    def test_eq(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(r, TruthTable.Row(a=0, b=1, c=2))
        self.assertNotEqual(r, TruthTable.Row(a=0, b=1, c=3))
        self.assertEqual(r, dict(a=0, b=1, c=2))
        self.assertNotEqual(r, dict(a=0, b=1, c=3))

    def test_eq_nested(self):
        r = TruthTable.Row(a=0, b=1, c=TruthTable.Row(d=2))
        self.assertEqual(r, TruthTable.Row(a=0, b=1, c=TruthTable.Row(d=2)))
        self.assertNotEqual(r, TruthTable.Row(a=0, b=1, c=TruthTable.Row(d=3)))
        self.assertEqual(r, TruthTable.Row(a=0, b=1, c=dict(d=2)))
        self.assertNotEqual(r, TruthTable.Row(a=0, b=1, c=dict(d=3)))
        self.assertEqual(r, dict(a=0, b=1, c=dict(d=2)))
        self.assertNotEqual(r, dict(a=0, b=1, c=dict(d=3)))

    def test_get(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(r.get('a'), 0)
        self.assertEqual(r.get('a', 42), 0)
        self.assertEqual(r.get('d'), None)
        self.assertEqual(r.get('d', 42), 42)

    def test_items_keys_values(self):
        r = TruthTable.Row(a=0, b=1, c=2)
        self.assertEqual(list(r.items()), [('a', 0), ('b', 1), ('c', 2)])
        self.assertEqual(list(r.keys()), ['a', 'b', 'c'])
        self.assertEqual(list(r.values()), [0, 1, 2])

class TestTruth(unittest.TestCase):
    def test_simple(self):
        t = TruthTable(
            ['a', 'b', 'c'],
            [0, 1, 2],
            [3, 4, 5],
        )

        rows = list(t)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], TruthTable.Row(a=0, b=1, c=2))
        self.assertEqual(rows[1], TruthTable.Row(a=3, b=4, c=5))

    def test_many(self):
        x = TruthTable.Many(range(2))
        t = TruthTable(
            ['a', 'b', 'c'],
            [0, x, 1],
            [x, 0, x],
        )

        self.assertEqual(list(t), [
            TruthTable.Row(a=0, b=0, c=1),
            TruthTable.Row(a=0, b=1, c=1),
            TruthTable.Row(a=0, b=0, c=0),
            TruthTable.Row(a=0, b=0, c=1),
            TruthTable.Row(a=1, b=0, c=0),
            TruthTable.Row(a=1, b=0, c=1),
        ])

    def test_structure(self):
        t = TruthTable(
            [['a', 'b'], 'c', ['d']],
            [[0, 1], 2, [3]],
        )
        self.assertEqual(list(t), [
            TruthTable.Row(a=0, b=1, c=2, d=3)
        ])

        t = TruthTable(
            [['a', 'b'], 'c', ['d']],
            [[0, 1], 2, 3],
        )
        with self.assertRaises(RuntimeError):
            list(t)

        t = TruthTable(
            [['a', 'b'], 'c', 'd'],
            [[0, 1], 2, [3]],
        )
        with self.assertRaises(RuntimeError):
            list(t)

    def test_many_structure(self):
        x = TruthTable.Many([[0, 0], [0, 1]])
        t = TruthTable(
            [['a', 'b'], 'c'],
            [x, 0],
        )
        self.assertEqual(list(t), [
            TruthTable.Row(a=0, b=0, c=0),
            TruthTable.Row(a=0, b=1, c=0),
        ])

        x = TruthTable.Many([[0, 0], [0, 1]])
        t = TruthTable(
            ['a', 'b', 'c'],
            [x, 0],
        )
        with self.assertRaises(RuntimeError):
            list(t)

    def test_structure_many(self):
        x = TruthTable.Many(range(2))
        t = TruthTable(
            [['a', 'b'], 'c'],
            [[x, 0], 1],
        )

        self.assertEqual(list(t), [
            TruthTable.Row(a=0, b=0, c=1),
            TruthTable.Row(a=1, b=0, c=1),
        ])

    def test_nested_many(self):
        x = TruthTable.Many(range(2))
        y = TruthTable.Many([[0, 0], [1, x]])
        t = TruthTable(
            [[['a', 'b'], 'c'], 'd'],
            [[y, 2], 3],
        )

        self.assertEqual(list(t), [
            TruthTable.Row(a=0, b=0, c=2, d=3),
            TruthTable.Row(a=1, b=0, c=2, d=3),
            TruthTable.Row(a=1, b=1, c=2, d=3),
        ])

    def test_group(self):
        t = TruthTable(
            ['a', TruthTable.Group('rest', ['b', 'c'])],
            [0, [1, 2]],
            [3, [4, 5]],
        )

        self.assertEqual(list(t), [
            TruthTable.Row(a=0, rest=TruthTable.Row(b=1, c=2)),
            TruthTable.Row(a=3, rest=TruthTable.Row(b=4, c=5)),
        ])

    def test_nested_group(self):
        t = TruthTable(
            ['a', TruthTable.Group('rest', ['b', TruthTable.Group('foo', ['c'])])],
            [0, [1, [2]]],
            [3, [4, [5]]],
        )

        self.assertEqual(list(t), [
            TruthTable.Row(a=0, rest=TruthTable.Row(b=1, foo=TruthTable.Row(c=2))),
            TruthTable.Row(a=3, rest=TruthTable.Row(b=4, foo=TruthTable.Row(c=5))),
        ])
