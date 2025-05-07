import importlib

import amaranth as am
import amaranth.lib.enum
import amaranth.lib.stream
import amaranth.lib.wiring

import zooby.cxxrtl
from .clock_divider import ClockDivider

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
        return stream

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
        return stream

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
        m.submodules.div = div = am.DomainRenamer(self.txdomain)(ClockDivider(max_divisor=self.max_divisor))
        m.d.comb += div.divisor.eq(divisor)

        # state, 1 in position n means output n + 1 bits
        # start + data_bits + parity? + stop
        state = am.Signal(1 + data.shape().width + 1 + 2)
        # busy if state bit set
        busy = state.any()

        # data to shift out, fill with 1s
        shift_reg = am.Signal.like(state, init=-1)

        # output shift register to tx while busy, and turn on divider
        with m.If(busy):
            m.d.comb += [
                div.en.eq(1),
                self.tx.eq(shift_reg[0]),
            ]

        # on divider pulse, shift state and the register to the right
        # and update parity
        # fill in empty bits of the shift register with 1s
        with m.If(div.pulse):
            domain += [
                state.eq(state >> 1),
                shift_reg[:-1].eq(shift_reg >> 1),
                shift_reg[-1].eq(1),
            ]

        # fiddly: change what the divider loads to on 1.5 stop bits
        with m.If(stop_bits.matches(StopBits.STOP_1_5) & state[1]):
            m.d.comb += div.divisor.eq(divisor >> 1)

        # we are only ready if we're not busy, or if it's the very last cycle
        m.d.comb += ready.eq(~busy | (state[0] & div.pulse))

        # if we're ready and data is available, read it in
        with m.If(ready & valid):
            parity_start = 1 + data_bits
            end = parity_start + parity.has_parity + stop_bits.bits

            # data mask
            mask = ((1 << data_bits) - 1)[:self.max_bits]

            domain += [
                # safe: end > 1
                state.eq(1 << (end - 1).as_unsigned()),

                # start bit
                shift_reg[0].eq(0),
                # data
                shift_reg[1:self.max_bits + 1].eq(data | ~mask),
                # parity done below
                # stop bits automatic since this register is full of 1s
            ]

            # parity bit
            with m.If(parity.has_parity):
                domain += shift_reg.bit_select(parity_start, 1).eq(parity.calculate(data & mask))

            # reload the clock divider
            m.d.comb += div.load.eq(1)

        return m
