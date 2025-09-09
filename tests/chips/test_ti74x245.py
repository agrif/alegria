# amaranth: UnusedElaboratable=no

import amaranth as am

from alegria.chips import Ti74x245
from alegria.test import SimulatorTestCase, TruthTable

class TestTi74x245(SimulatorTestCase):
    def setUp(self):
        self.dut = Ti74x245()
        self.traces = [
            {'control': [
                self.dut.dir,
                self.dut.oe_n,
            ]},
            {'a': [
                self.dut.a_in,
                self.dut.a_out,
                self.dut.a_out_valid,
            ]},
            {'b': [
                self.dut.b_in,
                self.dut.b_out,
                self.dut.b_out_valid,
            ]},
        ]

    def test_pins(self):
        self.dut.pins

    def test_truth(self):
        # any bit
        x = TruthTable.Many(range(2))
        # any data. be slightly more conservative than range(256)
        d = TruthTable.Many([0x00, 0xff, 0xaa, 0x55, 0x12, 0x34, 0xcd, 0xef])

        outputs = ['a_out', 'a_out_valid', 'b_out', 'b_out_valid']
        table = TruthTable(
            [['oe_n', 'dir'], ['a_in', 'a_out', 'a_out_valid'], ['b_in', 'b_out', 'b_out_valid']],
            # B data to A bus
            [[0, 0], [d, 'b_in', 1], [d, 0, 0]],
            # A data to B bus
            [[0, 1], [d, 0, 0], [d, 'a_in', 1]],
            # isolation
            [[1, x], [d, 0, 0], [d, 0, 0]],
        )

        p = am.Period(us=1)
        with self.simulate(self.dut, traces=self.traces, deadline=10*p) as sim:
            @sim.add_testbench
            async def bench(ctx):
                for row in table:
                    sim.reset_deadline()
                    for k, v in row.items():
                        if k in outputs:
                            continue
                        ctx.set(getattr(self.dut, k), v)

                    await ctx.delay(p)
                    for k in outputs:
                        expected = row[k]
                        if isinstance(expected, str):
                            expected = row[expected]
                        self.assertEqual(ctx.get(getattr(self.dut, k)), expected)
