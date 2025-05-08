import importlib

import amaranth as am
import amaranth.lib.data
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

class RxData(am.lib.data.StructLayout):
    def __init__(self, max_bits):
        self.max_bits = max_bits
        super().__init__({
            'data': max_bits,
            'error': RxError,
        })

class RxError(am.lib.data.Struct):
    framing: 1
    overrun: 1
    parity: 1

class Rx(am.lib.wiring.Component):
    def __init__(self, max_bits=8, max_divisor=127, rxdomain='sync'):
        self.max_bits = max_bits
        self.max_divisor = max_divisor
        self.rxdomain = rxdomain

        super().__init__({
            'rx': am.lib.wiring.In(1, init=1),

            'data': am.lib.wiring.Out(RxData(max_bits)),
            'valid': am.lib.wiring.Out(1),
            'ready': am.lib.wiring.In(1),

            'divisor': am.lib.wiring.In(range(max_divisor + 1), init=1),
            'data_bits': am.lib.wiring.In(range(max_bits + 1), init=min(8, max_bits)),
            'stop_bits': am.lib.wiring.In(StopBits),
            'parity': am.lib.wiring.In(Parity),

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

        # get all of our external signals into the rxdomain
        if self.rxdomain == 'sync':
            domain = m.d.sync

            data = self.data
            valid = self.valid
            ready = self.ready

            divisor = self.divisor
            data_bits = self.data_bits
            stop_bits = self.stop_bits
            parity = self.parity
        else:
            raise RuntimeError('rxdomain not implemented')

        # clock divider
        m.submodules.div = div = am.DomainRenamer(self.rxdomain)(ClockDivider(max_divisor=self.max_divisor))
        m.d.comb += div.divisor.eq(divisor)

        # state, 1 in position n means read n + 1 bits
        # do not include start bit, that is detected before this is set
        # data_bits + parity? + stop
        state = am.Signal(self.max_bits + 1 + 2)
        # busy if state bit set
        busy = state.any()

        # data to shift in
        shift_reg = am.Signal.like(state)

        # turn on divider while busy
        with m.If(busy):
            m.d.comb += div.en.eq(1)

        # on divider pulse, shift state and register to the right
        # read rx into low bit on register
        with m.If(div.pulse):
            domain += [
                state.eq(state >> 1),
                shift_reg[:-1].eq(shift_reg >> 1),
                shift_reg[-1].eq(self.rx),
            ]

        # fiddly: change what the divider loads to on 1.5 stop bits
        with m.If(stop_bits.matches(StopBits.STOP_1_5) & state[1]):
            # subtle math: we must get past the end of this bit
            # but we must go at least one more
            # 1 -> 1 or 0
            # 2 -> 2
            # 3 -> 3
            # 4 -> 3
            # n -> n / 2 + n / 4
            with m.If(divisor[2:].any()):
                # divisor > 3
                m.d.comb += div.divisor.eq((divisor >> 1) + (divisor >> 2))
            with m.Else():
                # divisor <= 3
                # this should be the same as what it already is
                # but we'll set it here explicitly anyway
                m.d.comb += div.divisor.eq(divisor)

        # if rx is high and we're not busy, keep the divider loaded with
        # a half bit period so we can detect start bits
        # also do this on the very last cycle of a decode
        with m.If((self.rx & ~busy) | (state[0] & div.pulse)):
            m.d.comb += [
                div.divisor.eq(divisor >> 1),
                div.load.eq(1),
            ]

        # if rx is low and we're not busy, turn on the divider to count
        # half a start bit
        with m.If(~self.rx & ~busy):
            m.d.comb += div.en.eq(1)

            # if we hit a divider pulse, we found a start bit, so
            # start decoding
            with m.If(div.pulse):
                # skip the start bit, we're already on it
                end = data_bits + parity.has_parity + stop_bits.bits
                # safe: end > 1
                domain += state.eq(1 << (end - 1).as_unsigned())

        # if state[0], then this is the last bit
        with m.If(state[0] & div.pulse):
            # find where the data bits begin
            # safe: this number is always positive
            data_start = 1 + (2 - stop_bits.bits) + (1 - parity.has_parity) + (self.max_bits - data_bits)
            data_start = data_start.as_unsigned()

            # where is the parity bit?
            parity_start = data_start + data_bits

            mask = ((1 << data_bits) - 1)[:self.max_bits]
            rx_data = shift_reg.bit_select(data_start, self.max_bits) & mask

            # if this stop bit or the previous is low, it's a framing error
            framing_error = ~self.rx | ((stop_bits != StopBits.STOP_1) & ~shift_reg[-1])

            # check the parity bit
            parity_error = parity.has_parity & (shift_reg.bit_select(parity_start, 1) != parity.calculate(rx_data))

            # overrun occurs during load, but we store it here
            overrun_error = am.Signal(1)

            # if we have room in the output
            with m.If(~valid):
                domain += [
                    data.data.eq(rx_data),
                    data.error.framing.eq(framing_error),
                    data.error.parity.eq(parity_error),
                    data.error.overrun.eq(overrun_error),
                    valid.eq(1),
                    overrun_error.eq(0),
                ]
            with m.Else():
                domain += overrun_error.eq(1)

        # handle output stream reads
        with m.If(valid & ready):
            domain += valid.eq(0)

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
            'data_bits': am.lib.wiring.In(range(max_bits + 1), init=min(8, max_bits)),
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
        state = am.Signal(1 + self.max_bits + 1 + 2)
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
