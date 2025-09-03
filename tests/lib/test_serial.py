import amaranth as am
from parameterized import parameterized, parameterized_class

from ..simulator import SimulatorTestCase

from alegria.lib.serial import *

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

    def rx_traces(self, rx):
        return [
            rx.rx,
            rx.stream,
            {'config': [
                rx.divisor,
                rx.data_bits,
                rx.stop_bits,
                rx.parity,
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

    async def serial_write(self, ctx, tx, data, parity_error=False, stops=[1, 1]):
        divisor = self.divisor
        data_bits = self.data_bits
        stop_bits = self.stop_bits
        parity = self.parity

        # start bit
        ctx.set(tx, 0)
        await ctx.tick().repeat(divisor)

        # data bits
        parity_count = 0
        for _ in range(data_bits):
            bit = data & 1
            data = data >> 1

            parity_count += bit
            ctx.set(tx, bit)
            await ctx.tick().repeat(divisor)

        # parity bit
        parity_count += parity_error
        if parity == Parity.ODD:
            ctx.set(tx, parity_count % 2)
            await ctx.tick().repeat(divisor)
        elif parity == Parity.EVEN:
            ctx.set(tx, 1 - parity_count % 2)
            await ctx.tick().repeat(divisor)

        # stop bits
        stop_waits = [divisor]
        if stop_bits == StopBits.STOP_1_5:
            stop_waits.append(max(divisor // 2, 1))
        elif stop_bits == StopBits.STOP_2:
            stop_waits.append(divisor)
        for bit, wait in zip(stops, stop_waits):
            ctx.set(tx, bit)
            await ctx.tick().repeat(wait)

        # back to high for sure
        ctx.set(tx, 1)

@SerialTestCase.parameterized_class
class TestSerial(SerialTestCase):
    def set_up_tx(self):
        return Tx(max_divisor=16, max_bits=9)

    def set_up_rx(self):
        return Rx(max_divisor=16, max_bits=9)

    def test_tx(self):
        dut = self.set_up_tx()
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

    def test_rx(self):
        dut = self.set_up_rx()
        with self.simulate(dut, traces=self.rx_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for v in self.TEST_DATA:
                    await self.serial_write(ctx, dut.rx, v)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(dut.divisor, self.divisor)
                ctx.set(dut.data_bits, self.data_bits)
                ctx.set(dut.stop_bits, self.stop_bits)
                ctx.set(dut.parity, self.parity)

                for v in self.TEST_DATA:
                    value = await self.stream_get(ctx, dut.stream)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value.data, v & mask)
                    self.assertFalse(value.error.framing)
                    self.assertFalse(value.error.parity)
                    self.assertFalse(value.error.overrun)

    def test_rx_parity(self):
        dut = self.set_up_rx()
        with self.simulate(dut, traces=self.rx_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            # odd bits set, then even bits set
            parity_data = [0xf8, 0xf8, 0xf9, 0xf9]

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for i, v in enumerate(parity_data):
                    await self.serial_write(ctx, dut.rx, v, parity_error=i % 2)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(dut.divisor, self.divisor)
                ctx.set(dut.data_bits, self.data_bits)
                ctx.set(dut.stop_bits, self.stop_bits)
                ctx.set(dut.parity, self.parity)

                for i, v in enumerate(parity_data):
                    value = await self.stream_get(ctx, dut.stream)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value.data, v & mask)
                    self.assertFalse(value.error.framing)
                    self.assertEqual(value.error.parity, (i % 2) * (self.parity != Parity.NONE))
                    self.assertFalse(value.error.overrun)

    def test_rx_framing(self):
        rst = am.Signal()
        dut = am.ResetInserter(rst)(self.set_up_rx())
        with self.simulate(dut, traces=self.rx_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            stop_patterns = [[0, 0], [1, 0], [0, 1], [1, 1]]

            @sim.add_testbench
            async def write(ctx):
                for stops in stop_patterns:
                    await ctx.tick().repeat(3)
                    await self.serial_write(ctx, dut.rx, 0x01, stops=stops)

                    # reset in between, as missing stop bits look like starts
                    # careful, rx is synchronized
                    await ctx.tick().repeat(10)
                    ctx.set(rst, 1)
                    await ctx.tick()
                    ctx.set(rst, 0)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(dut.divisor, self.divisor)
                ctx.set(dut.data_bits, self.data_bits)
                ctx.set(dut.stop_bits, self.stop_bits)
                ctx.set(dut.parity, self.parity)

                for stops in stop_patterns:
                    expected = stops != [1, 1]
                    if self.stop_bits == StopBits.STOP_1:
                        expected = not stops[0]
                    value = await self.stream_get(ctx, dut.stream)

                    self.assertEqual(value.data, 0x01)
                    self.assertEqual(value.error.framing, int(expected))
                    self.assertFalse(value.error.parity)
                    self.assertFalse(value.error.overrun)

    def test_rx_overrun(self):
        dut = self.set_up_rx()
        with self.simulate(dut, traces=self.rx_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for v in self.TEST_DATA:
                    await self.serial_write(ctx, dut.rx, v)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(dut.divisor, self.divisor)
                ctx.set(dut.data_bits, self.data_bits)
                ctx.set(dut.stop_bits, self.stop_bits)
                ctx.set(dut.parity, self.parity)

                await ctx.tick().repeat(3)

                last_v = self.TEST_DATA[0]
                for i, v in enumerate(self.TEST_DATA):
                    if i % 3 == 0:
                        # over-estimate
                        wait_bits = 1 + self.data_bits + 1
                        if self.parity != Parity.NONE:
                            wait_bits += 1
                        if self.stop_bits != StopBits.STOP_1:
                            wait_bits += 1

                        wait_bits *= self.divisor

                        # wait for two words and some extra
                        await ctx.tick().repeat(wait_bits * 2 + wait_bits // 2)

                        last_v = v
                        continue

                    value = await self.stream_get(ctx, dut.stream)
                    mask = (1 << self.data_bits) - 1

                    if i % 3 == 1:
                        self.assertEqual(value.data, last_v & mask)
                        self.assertFalse(value.error.framing)
                        self.assertFalse(value.error.parity)
                        self.assertFalse(value.error.overrun)
                    elif i % 3 == 2:
                        self.assertEqual(value.data, v & mask)
                        self.assertFalse(value.error.framing)
                        self.assertFalse(value.error.parity)
                        self.assertTrue(value.error.overrun)

    def test_tx_rx(self):
        dut = am.Module()
        dut.submodules.tx = tx = self.set_up_tx()
        dut.submodules.rx = rx = self.set_up_rx()

        dut.d.comb += rx.rx.eq(tx.tx)

        with self.simulate(dut, traces=self.tx_traces(tx) + self.rx_traces(rx)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                ctx.set(tx.divisor, self.divisor)
                ctx.set(tx.data_bits, self.data_bits)
                ctx.set(tx.stop_bits, self.stop_bits)
                ctx.set(tx.parity, self.parity)

                await ctx.tick().repeat(3)

                for v in self.TEST_DATA:
                    await self.stream_put(ctx, tx.stream, v)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(rx.divisor, self.divisor)
                ctx.set(rx.data_bits, self.data_bits)
                ctx.set(rx.stop_bits, self.stop_bits)
                ctx.set(rx.parity, self.parity)

                for v in self.TEST_DATA:
                    value = await self.stream_get(ctx, rx.stream)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value.data, v & mask)
                    self.assertFalse(value.error.framing)
                    self.assertFalse(value.error.parity)
                    self.assertFalse(value.error.overrun)

    def test_rx_tx(self):
        dut = am.Module()
        dut.submodules.rx = rx = self.set_up_rx()
        dut.submodules.tx = tx = self.set_up_tx()

        dut.d.comb += [
            tx.data.eq(rx.data.data),
            tx.valid.eq(rx.valid),
            rx.ready.eq(tx.ready),
        ]

        with self.simulate(dut, traces=self.rx_traces(rx) + self.tx_traces(tx)) as sim:
            sim.add_clock(am.Period(Hz=115200 * 64))

            @sim.add_testbench
            async def write(ctx):
                ctx.set(rx.divisor, self.divisor)
                ctx.set(rx.data_bits, self.data_bits)
                ctx.set(rx.stop_bits, self.stop_bits)
                ctx.set(rx.parity, self.parity)

                await ctx.tick().repeat(3)

                for v in self.TEST_DATA:
                    await self.serial_write(ctx, rx.rx, v)

            @sim.add_testbench
            async def middle_no_error(ctx):
                for v in self.TEST_DATA:
                    error, = await ctx.tick().sample(rx.data.error).until(rx.valid)
                    self.assertFalse(error.framing)
                    self.assertFalse(error.parity)
                    self.assertFalse(error.overrun)

            @sim.add_testbench
            async def read(ctx):
                ctx.set(tx.divisor, self.divisor)
                ctx.set(tx.data_bits, self.data_bits)
                ctx.set(tx.stop_bits, self.stop_bits)
                ctx.set(tx.parity, self.parity)

                for v in self.TEST_DATA:
                    value = await self.serial_read(ctx, tx.tx)
                    mask = (1 << self.data_bits) - 1
                    self.assertEqual(value, v & mask)
