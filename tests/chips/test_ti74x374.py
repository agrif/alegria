# amaranth: UnusedElaboratable=no

import amaranth as am

from ..simulator import SimulatorTestCase
from ..truth import TruthTable

from zooby.chips import Ti74x374

class TestTi74x374(SimulatorTestCase):
    def setUp(self):
        self.dut = Ti74x374()
        self.traces = [
            {'control': [
                self.dut.oc_n,
                self.dut.clk,
            ]},
            self.dut.d,
            self.dut.q,
            self.dut.q_valid,
        ]

    def test_pins(self):
        self.dut.pins

    def test_truth(self):
        # any bit
        x = TruthTable.Many(range(2))
        # any data. or at least, a selection
        d = TruthTable.Many([0x00, 0xff, 0xaa, 0x55, 0x12, 0x34, 0xcd, 0xef])

        outputs = ['q', 'q_valid']
        table = TruthTable(
            # clk, tick way on the right so it changes most often
            ['oc_n', 'd', 'q', 'q_valid', 'clk', 'tick'],
            [0, d, 'd', 1, 0, 1],
            [0, d, 'q', 1, 1, x],
            [1, d, 0, 0, x, x],
        )

        p = am.Period(us=1)
        with self.simulate(self.dut, traces=self.traces) as sim:
            sim.add_clock(p)

            @sim.add_testbench
            async def bench(ctx):
                q = 0
                for row in table:
                    for k, v in row.items():
                        if k in outputs or k == 'tick':
                            continue
                        ctx.set(getattr(self.dut, k), row[k])

                    if row.tick:
                        await ctx.tick()
                        if ctx.get(self.dut.clk) == 0:
                            q = ctx.get(self.dut.d)
                    else:
                        await ctx.delay(p / 4)

                    for k in outputs:
                        expected = row[k]
                        if expected == 'd':
                            expected = row.d
                        if expected == 'q':
                            expected = q
                        self.assertEqual(ctx.get(getattr(self.dut, k)), expected)
