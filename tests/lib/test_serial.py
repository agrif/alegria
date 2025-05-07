import amaranth as am
from parameterized import parameterized, parameterized_class

from ..simulator import SimulatorTestCase

from zooby.lib.serial import *

# serial helpers
class SerialTestCase(SimulatorTestCase):
    TEST_DATA = [0x000, 0x1ff, 0x0aa, 0x155, 0x134, 0x0cd]

    TEST_PARAMS = [
        {'divisor': div, 'data_bits': bits, 'stop_bits': stop, 'parity': parity}
        for div in [1, 3, 16]
        for bits in [7, 8, 9]
        for stop in StopBits
        for parity in Parity
    ]

    @classmethod
    def parameterized_class(cls, f):
        def name(cls, num, params_dict):
            return '_'.join([
                cls.__name__,
                str(num),
                'd' + parameterized.to_safe_name(params_dict['divisor']),
                'b' + parameterized.to_safe_name(params_dict['data_bits']),
                parameterized.to_safe_name(params_dict['stop_bits'].name),
                parameterized.to_safe_name(params_dict['parity'].name),
            ])
        return parameterized_class(cls.TEST_PARAMS, class_name_func=name)(f)

    def tx_traces(self, tx):
        return [
            tx.tx,
            tx.stream,
            {'config': [
                tx.divisor,
                tx.data_bits,
                tx.stop_bits,
                tx.parity,
            ]},
        ]

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

@SerialTestCase.parameterized_class
class TestSerial(SerialTestCase):
    def test_tx(self):
        dut = Tx(max_divisor=16, max_bits=9)
        with self.simulate(dut, traces=self.tx_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                ctx.set(dut.divisor, self.divisor)
                ctx.set(dut.data_bits, self.data_bits)
                ctx.set(dut.stop_bits, self.stop_bits)
                ctx.set(dut.parity, self.parity)

                await ctx.tick().repeat(3)

                for v in self.TEST_DATA:
                    await self.stream_put(ctx, dut.stream, v)

            @sim.add_testbench
            async def read(ctx):
                for v in self.TEST_DATA:
                    value = await self.serial_read(ctx, dut.tx)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value, v & mask)
