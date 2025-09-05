# amaranth: UnusedElaboratable=no

import amaranth as am

from alegria.chips import Ti74x138
from alegria.test import SimulatorTestCase, TruthTable

class TestTi74x138(SimulatorTestCase):
    def setUp(self):
        self.dut = Ti74x138()
        self.traces = [
            {'enable': [
                self.dut.g1,
                self.dut.g2a_n,
                self.dut.g2b_n,
            ]},
            {'select': self.dut.select},
            self.dut.y,
        ]

    def test_pins(self):
        self.dut.pins

    def test_select(self):
        self.dut.select

    def test_truth(self):
        # any bit
        x = TruthTable.Many(range(2))

        table = TruthTable(
            [['g1', 'g2a_n', 'g2b_n'], ['c', 'b', 'a'], 'y'],
            [[x, 1, x], [x, x, x], 0xff],
            [[x, x, 1], [x, x, x], 0xff],
            [[0, x, x], [x, x, x], 0xff],

            [[1, 0, 0], [0, 0, 0], ~(1 << 0) & 0xff],
            [[1, 0, 0], [0, 0, 1], ~(1 << 1) & 0xff],
            [[1, 0, 0], [0, 1, 0], ~(1 << 2) & 0xff],
            [[1, 0, 0], [0, 1, 1], ~(1 << 3) & 0xff],
            [[1, 0, 0], [1, 0, 0], ~(1 << 4) & 0xff],
            [[1, 0, 0], [1, 0, 1], ~(1 << 5) & 0xff],
            [[1, 0, 0], [1, 1, 0], ~(1 << 6) & 0xff],
            [[1, 0, 0], [1, 1, 1], ~(1 << 7) & 0xff],
        )

        p = am.Period(us=1)
        with self.simulate(self.dut, traces=self.traces) as sim:
            @sim.add_testbench
            async def bench(ctx):
                for row in table:
                    for k, v in row.items():
                        if k == 'y':
                            continue
                        ctx.set(getattr(self.dut, k), v)

                    await ctx.delay(p)
                    self.assertEqual(ctx.get(self.dut.y), row.y)
