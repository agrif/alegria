import amaranth as am
import amaranth.lib.data
import amaranth.lib.enum
import amaranth.lib.wiring

# Motorola MC6850 ACIA
# https://www.cpcwiki.eu/imgs/3/3f/MC6850.pdf

class Mc6850(am.lib.wiring.Component):
    # pin 1 vss
    rx: am.lib.wiring.In(1)
    # pin 3 rxclk
    # pin 4 txclk
    rts_n: am.lib.wiring.Out(1, init=1)
    tx: am.lib.wiring.Out(1)
    irq_n: am.lib.wiring.Out(1, init=1)
    cs0: am.lib.wiring.In(1, init=1)
    cs2_n: am.lib.wiring.In(1)
    cs1: am.lib.wiring.In(1, init=1)
    rs: am.lib.wiring.In(1)
    # pin 12 vcc
    r_w_n: am.lib.wiring.In(1)
    e: am.lib.wiring.In(1)

    # pins 15-22 d
    d_in: am.lib.wiring.In(8)
    d_out: am.lib.wiring.Out(8)
    d_out_valid: am.lib.wiring.Out(1)

    dcd_n: am.lib.wiring.In(1)
    cts_n: am.lib.wiring.In(1)

    class Control(am.lib.data.Struct):
        class CounterDivide(am.lib.enum.Enum, shape=2):
            DIV_1 = 0b00
            DIV_16 = 0b01
            DIV_64 = 0b10
            RESET = 0b11

        class Word(am.lib.enum.Enum, shape=3):
            FORMAT_7E2 = 0b000
            FORMAT_7O2 = 0b001
            FORMAT_7E1 = 0b010
            FORMAT_7O1 = 0b011
            FORMAT_8N2 = 0b100
            FORMAT_8N1 = 0b101
            FORMAT_8E1 = 0b110
            FORMAT_8O1 = 0b111

        class TransmitControl(am.lib.enum.Enum, shape=2):
            RTS = 0b00
            RTS_TRANSMIT_INTERRUPT_ENABLE = 0b01
            NONE = 0b10
            RTS_BREAK = 0b11

        counter_divide: CounterDivide
        word: Word
        transmit_control: TransmitControl
        receive_interrupt_enable: 1

    # needed for debug, cxxrtl does not support enums
    class ControlRaw(am.lib.data.Struct):
        counter_divide: 2
        word: 3
        transmit_control: 2
        receive_interrupt_enable: 1

    class Status(am.lib.data.Struct):
        # receive data register full
        rdrf: 1
        # transmit data register empty
        tdre: 1
        # data carrier detect
        dcd_n: 1
        # clear to send
        cts_n: 1
        # framing error
        fe: 1
        # receiver overrun
        ovrn: 1
        # parity error
        pe: 1
        # interrupt request
        irq_n: 1

    def __init__(self, txdomain='sync', rxdomain='sync', debug=False):
        self.txdomain = txdomain
        self.rxdomain = rxdomain
        self.debug = debug

        self.control = am.Signal(self.Control)
        self.status = am.Signal(self.Status)

        super().__init__()

    def trace(self, m, fmt, *args, **kwargs):
        if self.debug:
            m.d.sync += am.Print(am.Format('mc6850/' + fmt, *args, **kwargs))

    def elaborate(self, platform):
        m = am.Module()

        chipselect = self.cs0 & self.cs1 & ~self.cs2_n

        # some state to detect writes on e falling edge
        prev_was_write = am.Signal()
        prev_rs = am.Signal.like(self.rs)
        prev_d_in = am.Signal.like(self.d_in)
        m.d.sync += prev_was_write.eq(0)

        # FIXME actual status
        m.d.comb += self.status.tdre.eq(1)

        with m.If(chipselect & self.e & self.r_w_n):
            # read
            with m.If(self.rs):
                # read rx register
                self.trace(m, 'r rx 0x{:02x}', self.d_out)
                # FIXME
                m.d.comb += [
                    self.d_out.eq(0),
                    self.d_out_valid.eq(1),
                ]
            with m.Else():
                # read status register
                self.trace(m, 'r status {}', self.status)
                # FIXME this has side-effects
                m.d.comb += [
                    self.d_out.eq(self.status),
                    self.d_out_valid.eq(1),
                ]

        with m.If(chipselect & self.e & ~self.r_w_n):
            # write should occur when e goes low, while r_w_n low
            # so store d_in for later
            m.d.sync += [
                prev_was_write.eq(1),
                prev_rs.eq(self.rs),
                prev_d_in.eq(self.d_in),
            ]


        with m.If(prev_was_write & ~self.e):
            # falling edge on e after write
            with m.If(prev_rs):
                # write tx register
                self.trace(m, 'w tx 0x{:02x}', prev_d_in)
                # FIXME this has side effects
                m.d.sync += am.Print(am.Format('{:c}', prev_d_in), end='')
            with m.Else():
                # write control register
                self.trace(m, 'w control {}', self.ControlRaw(prev_d_in))
                # FIXME this might have side effects?
                m.d.sync += self.control.eq(prev_d_in)

        return m
