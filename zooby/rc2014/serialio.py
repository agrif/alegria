import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.chips

# old, MC68B50 serial card
# IO ports 0x80 - 0xBF
# https://rc2014.co.uk/modules/retired/serial-io/
class SerialIO(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    rx: am.lib.wiring.In(1)
    tx: am.lib.wiring.Out(1)

    rts: am.lib.wiring.Out(1)

    def elaborate(self, platform):
        m = am.Module()

        # original board also includes a MAX232 that makes no sense here
        m.submodules.acia = acia = zooby.chips.Mc6850()
        m.submodules.inverter = inverter = zooby.chips.Ti74x04()

        m.d.comb += [
            inverter.a[0].eq(self.bus.memory.iorq_n),

            acia.rx.eq(self.rx),
            self.rts.eq(~acia.rts_n),
            self.tx.eq(acia.tx),
            self.bus.int_n.eq(acia.irq_n),
            acia.cs0.eq(self.bus.m1_n),
            acia.cs2_n.eq(self.bus.memory.addr[6]),
            acia.cs1.eq(self.bus.memory.addr[7]),
            acia.rs.eq(self.bus.memory.addr[0]),
            acia.r_w_n.eq(self.bus.memory.wr_n),
            acia.e.eq(inverter.y[0]),
            acia.d_in.eq(self.bus.memory.data_wr),
            self.bus.memory.data_rd.eq(acia.d_out),
            self.bus.memory.data_rd_valid.eq(acia.d_out_valid),
        ]

        return m
