import amaranth as am
import amaranth.lib.data
import amaranth.lib.enum
import amaranth.lib.wiring

import alegria.lib.serial

# Motorola MC6850 ACIA
# https://www.jameco.com/Jameco/Products/ProdDS/43633.pdf
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

        m.submodules.rx = rx = alegria.lib.serial.Rx(rxdomain=self.rxdomain)
        m.submodules.tx = tx = alegria.lib.serial.Tx(txdomain=self.txdomain)

        m.d.comb += [
            rx.rx.eq(self.rx),
            self.tx.eq(tx.tx),
        ]

        chipselect = self.cs0 & self.cs1 & ~self.cs2_n

        # some state to detect writes on e falling edge
        prev_was_write = am.Signal()
        prev_rs = am.Signal.like(self.rs)
        prev_d_in = am.Signal.like(self.d_in)
        m.d.sync += prev_was_write.eq(0)

        # hold on to rx data, since rx submodule isn't guaranteed to
        rx_data = am.Signal(8)

        # FIXME actual status
        m.d.comb += self.status.rdrf.eq(rx.valid)
        m.d.comb += self.status.tdre.eq(~tx.valid)
        m.d.comb += self.status.irq_n.eq(self.irq_n)
        m.d.comb += self.irq_n.eq(~(self.control.receive_interrupt_enable & rx.valid))
        m.d.comb += self.rts_n.eq(self.control.transmit_control == self.Control.TransmitControl.NONE)
        m.d.comb += rx.rts.eq(~self.rts_n)
        m.d.comb += tx.divisor.eq(64)
        m.d.comb += rx.divisor.eq(64)

        # memory reads
        with m.If(chipselect & self.e & self.r_w_n):
            with m.If(self.rs):
                # read rx register
                self.trace(m, 'r rx 0x{:02x}', self.d_out)
                with m.If(rx.valid):
                    m.d.comb += [
                        self.d_out.eq(rx.data),
                        self.d_out_valid.eq(1),
                        rx.ready.eq(1),
                    ]
                    m.d.sync += rx_data.eq(rx.data)
                with m.Else():
                    m.d.comb += [
                        self.d_out.eq(rx_data),
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

        # memory writes
        with m.If(chipselect & self.e & ~self.r_w_n):
            # write should occur when e goes low, while r_w_n low
            # so store d_in for later
            m.d.sync += [
                prev_was_write.eq(1),
                prev_rs.eq(self.rs),
                prev_d_in.eq(self.d_in),
            ]


        # detect e falling edge and perform writes
        with m.If(prev_was_write & ~self.e):
            # falling edge on e after write
            with m.If(prev_rs):
                # write tx register
                self.trace(m, 'w tx 0x{:02x}', prev_d_in)
                # FIXME this has side effects, maybe
                with m.If(~tx.valid):
                    m.d.sync += [
                        tx.data.eq(prev_d_in),
                        tx.valid.eq(1),
                    ]
            with m.Else():
                # write control register
                self.trace(m, 'w control {}', self.ControlRaw(prev_d_in))
                # FIXME this might have side effects?
                m.d.sync += self.control.eq(prev_d_in)

        # shuffle tx data to tx
        with m.If(tx.valid & tx.ready):
            m.d.sync += tx.valid.eq(0)

        return m
