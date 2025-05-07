import amaranth as am
from parameterized import parameterized_class

from ..simulator import SimulatorTestCase

from zooby.lib.serial import *

# serial helpers
class SerialTestCase(SimulatorTestCase):
    TESTDATA = [0x000, 0x1ff, 0x0aa, 0x155, 0x134, 0x0cd]

    async def serial_read_err(self, ctx, rx, assertions=True):
        divisor = self.divisor
        data_bits = self.data_bits
        stop_bits = self.stop_bits
        parity = self.parity

        # wait for a start bit
        # using .until(rx == 0) eats 1 clock at the end, which is no bueno
        while ctx.get(rx):
            await ctx.tick()

        # find middle of start bit
        if divisor // 2 > 0:
            await ctx.tick().repeat(divisor // 2)
        start = ctx.get(rx)
        if assertions:
            self.assertEqual(start, 0)
        if start:
            return (None, False, False)

        # read data bits
        bits = []
        for _ in range(data_bits):
            await ctx.tick().repeat(divisor)
            bits.append(ctx.get(rx))
        value = sum((1 << i) if b else 0 for i, b in enumerate(bits))

        # read parity bit
        parity_error = False
        if parity != Parity.NONE:
            await ctx.tick().repeat(divisor)
            parity_bit = ctx.get(rx)
            expected = sum(bits) % 2
            if parity == Parity.EVEN:
                expected = 1 - expected
            if assertions:
                self.assertEqual(parity_bit, expected)
            if parity_bit != expected:
                parity_error = True

        # read stop bits
        framing_error = False
        stop_waits = [divisor]
        if stop_bits == StopBits.STOP_1_5:
            stop_waits.append(divisor // 2 + divisor // 4)
        elif stop_bits == StopBits.STOP_2:
            stop_waits.append(divisor)
        for wait in stop_waits:
            await ctx.tick().repeat(max(wait, 1))
            stop = ctx.get(rx)
            if assertions:
                self.assertEqual(stop, 1)
            if not stop:
                framing_error = True

        return (value, parity_error, framing_error)

    async def serial_read(self, ctx, rx, assertions=True):
        value, _, _ = await self.serial_read_err(ctx, rx, assertions=True)
        return value

@parameterized_class([
    {'divisor': div, 'data_bits': bits, 'stop_bits': stop, 'parity': parity}
    for div in [1, 3, 16]
    for bits in [7, 8, 9]
    for stop in StopBits
    for parity in Parity
])
class TestTx(SerialTestCase):
    def setUp(self):
        self.dut = Tx(max_divisor=16, max_bits=9)
        self.traces = [
            self.dut.tx,
            self.dut.stream,
            {'config': [
                self.dut.divisor,
                self.dut.data_bits,
                self.dut.stop_bits,
                self.dut.parity,
            ]},
        ]

    def test_tx(self):
        with self.simulate(self.dut, traces=self.traces) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                ctx.set(self.dut.divisor, self.divisor)
                ctx.set(self.dut.data_bits, self.data_bits)
                ctx.set(self.dut.stop_bits, self.stop_bits)
                ctx.set(self.dut.parity, self.parity)

                await ctx.tick().repeat(3)

                for v in self.TESTDATA:
                    await self.stream_put(ctx, self.dut.stream, v)

            @sim.add_testbench
            async def read(ctx):
                for v in self.TESTDATA:
                    value = await self.serial_read(ctx, self.dut.tx)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value, v & mask)
