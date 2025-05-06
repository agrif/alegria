import importlib

import amaranth as am
import amaranth.lib.enum
import amaranth.lib.wiring

import zooby.cxxrtl

# helper to add blackbox files to platform
def _use_blackbox(platform):
    if isinstance(platform, zooby.cxxrtl.CxxRtlPlatform):
        for name in ['cxxrtl_serial.v', 'cxxrtl_serial.cpp']:
            platform.add_file('cxxrtl/' + name, importlib.resources.files().joinpath('serial', name).read_text())
        return True
    return False

class StopBitsView(am.lib.enum.EnumView):
    @property
    def bits(self):
        return am.Mux(self == StopBits.STOP_1, 1, 2)

class StopBits(am.lib.enum.Enum, shape=2, view_class=StopBitsView):
    STOP_1 = 0b00
    # FIXME this is currently also 2 bits
    STOP_1_5 = 0b01
    STOP_2 = 0b10

class ParityView(am.lib.enum.EnumView):
    @property
    def has_parity(self):
        return self != Parity.NONE

    def calculate(self, data):
        return data.xor() ^ (self == Parity.EVEN)

class Parity(am.lib.enum.Enum, shape=2, view_class=ParityView):
    NONE = 0b00
    ODD = 0b01
    EVEN = 0b10

class Rx(am.lib.wiring.Component):
    def __init__(self, max_bits=8, rxdomain='sync'):
        self.max_bits = max_bits
        self.rxdomain = rxdomain

        super().__init__({
            'rx': am.lib.wiring.In(1, init=1),

            'data': am.lib.wiring.Out(max_bits),
            'valid': am.lib.wiring.Out(1),
            'ready': am.lib.wiring.In(1),

            # used for simulation
            'rts': am.lib.wiring.In(1, init=1),
        })

    @property
    def stream(self):
        stream = am.lib.stream.Signature(self.data.shape()).create()
        stream.payload = self.data
        stream.valid = self.valid
        stream.ready = self.ready

    def elaborate(self, platform):
        m = am.Module()

        # use a blackbox in cxxrtl simulation
        if _use_blackbox(platform):
            return am.Instance(
                'cxxrtl_serial_rx',
                p_MAX_BITS=self.max_bits,
                i_clk=am.ClockSignal(),
                o_data=self.data,
                o_valid=self.valid,
                i_ready=self.ready,
                i_rts=self.rts,
            )

        # FIXME

        return m

class Tx(am.lib.wiring.Component):
    def __init__(self, max_bits=8, max_divisor=127, txdomain='sync'):
        self.max_bits = max_bits
        self.max_divisor = max_divisor
        self.txdomain = txdomain

        super().__init__({
            'tx': am.lib.wiring.Out(1, init=1),

            'data': am.lib.wiring.In(max_bits),
            'valid': am.lib.wiring.In(1),
            'ready': am.lib.wiring.Out(1),

            'divisor': am.lib.wiring.In(range(max_divisor + 1), init=1),
            'data_bits': am.lib.wiring.In(range(max_bits + 1), init=max_bits),
            'stop_bits': am.lib.wiring.In(StopBits),
            'parity': am.lib.wiring.In(Parity),
        })

    @property
    def stream(self):
        stream = am.lib.stream.Signature(self.data.shape()).flip().create()
        stream.payload = self.data
        stream.valid = self.valid
        stream.ready = self.ready

    def elaborate(self, platform):
        m = am.Module()

        # use a blackbox in cxxrtl simulation
        if _use_blackbox(platform):
            return am.Instance(
                'cxxrtl_serial_tx',
                p_MAX_BITS=self.max_bits,
                i_clk=am.ClockSignal(),
                i_data=self.data,
                i_valid=self.valid,
                o_ready=self.ready,
            )

        # get all of our external signals into the txdomain
        if self.txdomain == 'sync':
            domain = m.d.sync

            data = self.data
            valid = self.valid
            ready = self.ready

            divisor = self.divisor
            data_bits = self.data_bits
            stop_bits = self.stop_bits
            parity = self.parity
        else:
            raise RuntimeError('txdomain not implemented')

        # clock divider
        clock_div = am.Signal(am.Signal(range(self.max_divisor)).shape().width + 1)
        clock_div_en = am.Signal(1)
        clock_div_next = clock_div - clock_div_en
        clock_div_overflow = am.Signal(1)
        clock_div_reload = am.Signal(1)

        # overflow bit taken on dec, to get it one clock early
        m.d.comb += clock_div_overflow.eq(clock_div_next[-1])

        # register clock_div_next into clock_div
        domain += clock_div.eq(clock_div_next)

        # if the divider oveflows next cycle, reload it
        m.d.comb += clock_div_reload.eq(clock_div_overflow)

        # reload to overflow in divisor cycles
        with m.If(clock_div_reload):
            domain += clock_div.eq(divisor - 1)

        # state, 1 in position n means output n + 1 bits
        # start + data_bits + parity? + stop
        state = am.Signal(1 + data.shape().width + 1 + 2)
        # busy if state bit set
        busy = state.any()

        # enable the clock divider only when busy
        m.d.comb += clock_div_en.eq(busy)

        # data to shift out
        shift_reg = am.Signal.like(state)

        # on divider overflow, shift state and the register to the right
        # and update parity
        with m.If(clock_div_overflow):
            domain += [
                state.eq(state >> 1),
                shift_reg.eq(shift_reg >> 1),
            ]

        # output shift register to tx while busy
        with m.If(busy):
            m.d.comb += self.tx.eq(shift_reg[0])

        # we are only ready if we're not busy, or if it's the very last cycle
        m.d.comb += ready.eq(~busy | (state[0] & clock_div_overflow))

        # if we're ready and data is available, read it in
        with m.If(ready & valid):
            parity_start = 1 + data_bits
            stop_start = parity_start + parity.has_parity
            end = stop_start + stop_bits.bits

            masked_data = data & ((1 << data_bits) - 1)

            domain += [
                # safe: end > 1
                state.eq(1 << (end - 1).as_unsigned()),

                # start bit
                shift_reg[0].eq(0),
                # data
                shift_reg[1:].eq(masked_data),
                # parity bit
                shift_reg.bit_select(parity_start, 1).eq(parity.calculate(masked_data)),
                # stop bits
                shift_reg.bit_select(stop_start, 2).eq(-1),
            ]

            # reload the clock divider
            m.d.comb += clock_div_reload.eq(1)

        return m

if __name__ == '__main__':
    import amaranth.sim

    dut = Tx()
    async def bench(ctx):
        ctx.set(dut.divisor, 2)
        ctx.set(dut.parity, Parity.NONE)
        ctx.set(dut.stop_bits, StopBits.STOP_1)
        for _ in range(3):
            await ctx.tick()

        ctx.set(dut.data, 0xaa)
        ctx.set(dut.valid, 1)
        for _ in range(70):
            consumed = ctx.get(dut.ready) and ctx.get(dut.valid)
            await ctx.tick()
            if consumed:
                ctx.set(dut.data, 0)
                ctx.set(dut.valid, 0)

    sim = am.sim.Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(bench)
    with sim.write_vcd('tx.vcd'):
        sim.run()
