import amaranth as am

from ..simulator import SimulatorTestCase

from zooby.lib.serial import *

# serial helpers
class SerialTestCase(SimulatorTestCase):
    TESTDATA = [0x00, 0xff, 0xaa, 0x55, 0x34, 0xcd]

    async def serial_read_err(self, ctx, cfg, rx):
        divisor = ctx.get(cfg.divisor)
        data_bits = ctx.get(cfg.data_bits)
        stop_bits = ctx.get(cfg.stop_bits)
        parity = ctx.get(cfg.parity)

        # wait for a start bit
        # using .until(rx == 0) eats 1 clock at the end, which is no bueno
        while ctx.get(rx):
            await ctx.tick()

        # find middle of start bit
        if divisor // 2 > 0:
            await ctx.tick().repeat(divisor // 2)
        start = ctx.get(rx)
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
            if parity_bit != expected:
                parity_error = True

        # read stop bits
        framing_error = False
        stop_waits = [divisor]
        if stop_bits == StopBits.STOP_1_5:
            stop_waits.append(divisor - (divisor // 4))
        elif stop_bits == StopBits.STOP_2:
            stop_waits.append(divisor)
        for wait in stop_waits:
            await ctx.tick().repeat(wait)
            if not ctx.get(rx):
                framing_error = True

        return (value, parity_error, framing_error)

    async def serial_read(self, ctx, cfg, rx):
        value, parity_error, framing_error = await self.serial_read_err(ctx, cfg, rx)
        if value is None:
            self.fail('start bit not found')
        if parity_error:
            self.fail('bad parity bit')
        if framing_error:
            self.fail('bad stop bits')
        return value

class TestTx(SerialTestCase):
    def setUp(self):
        self.dut = Tx()
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
                ctx.set(self.dut.divisor, 4)
                await ctx.tick().repeat(3)

                for v in self.TESTDATA:
                    await self.stream_put(ctx, self.dut.stream, v)

            @sim.add_testbench
            async def read(ctx):
                for v in self.TESTDATA:
                    value = await self.serial_read(ctx, self.dut, self.dut.tx)
                    self.assertEqual(value, v)
