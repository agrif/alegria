# amaranth: UnusedElaboratable=no

import amaranth as am

from ..simulator import SimulatorTestCase
from ..truth import TruthTable

from zooby.chips import Ti74x04

class TestTi74x04(SimulatorTestCase):
    def setUp(self):
        self.dut = Ti74x04()
        self.traces = [
            self.dut.a,
            self.dut.y,
        ]

    def test_pins(self):
        self.dut.pins

    def test_truth(self):
        # one gate
        gate = TruthTable.Many([
            # [a, y]
            [1, 0],
            [0, 1],
        ])

        table = TruthTable(
            [TruthTable.Group(i, ['a', 'y']) for i in range(6)],
            [gate for _ in range(6)],
        )
        p = am.Period(us=1)
        with self.simulate(self.dut, traces=self.traces) as sim:
            @sim.add_testbench
            async def bench(ctx):
                for row in table:
                    for i, pins in row.items():
                        for k, v in pins.items():
                            if k == 'y':
                                continue
                            ctx.set(getattr(self.dut, k)[i], v)

                    await ctx.delay(p)
                    for i, pins in row.items():
                        self.assertEqual(ctx.get(self.dut.y[i]), pins.y)
