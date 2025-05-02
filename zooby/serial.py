import amaranth as am
import amaranth.lib.wiring

import zooby.bus

# old, MC68B50 serial card
class Serial(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    def elaborate(self, platform):
        m = am.Module()

        # A7 -> CS1
        # A6 -> /CS2
        # A0 -> RS (low control, high data)
        # M1 -> CS0
        # clk -> clk
        # int -> /irq
        # wr -> read high, write low
        # iorq -> inverter -> E
        # data -> data

        # active for 0b10xx_xxxx, that is, 0x80 - 0xbf

        # control write
        # [0:2] counter divide
        # [2:5] word select
        # [5:7] transmit control
        # [7:8] receive interrupt enable
        # control read
        # [0:1] receive data full
        # [1:2] transmit data empty
        # [2:3] /DCD
        # [3:4] /CTS
        # [4:5] framing error
        # [5:6] receiver overrun
        # [6:7] parity error
        # [7:8] /IRQ

        select = am.Signal(1)
        m.d.comb += select.eq(self.bus.memory.addr[7] | ~self.bus.memory.addr[6] | ~self.bus.m1)

        enable = am.Signal(1)
        m.d.comb += enable.eq(self.bus.memory.iorq)

        rs = am.Signal(1)
        m.d.comb += rs.eq(self.bus.memory.addr[0])

        with m.If(select & enable):
            with m.If(self.bus.memory.wr):
                with m.If(rs):
                    #m.d.sync += am.Print(am.Format('acia/w byte 0x{:02x}', self.bus.memory.data_wr))
                    m.d.sync += am.Print(am.Format('{:c}', self.bus.memory.data_wr), end='')
                with m.Else():
                    divide = self.bus.memory.data_wr[0:2]
                    word = self.bus.memory.data_wr[2:5]
                    transmit = self.bus.memory.data_wr[5:7]
                    ie = self.bus.memory.data_wr[7]
                    #m.d.sync += am.Print(am.Format('acia/w divide 0b{:02b} word 0b{:03b} transmit 0b{:02b} ie 0b{:01b}', divide, word, transmit, ie))
            with m.Else():
                with m.If(rs):
                    #m.d.sync += am.Print(am.Format('acia/r byte 0x{:02x}', self.bus.memory.data_rd))
                    pass
                with m.Else():
                    #m.d.sync += am.Print(am.Format('acia/r status 0b{:08b}', self.bus.memory.data_rd))
                    m.d.comb += self.bus.memory.data_rd.eq(0b0000_0010)

        return m
