import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.chips

# old, MC68B50 serial card
# IO ports 0x80 - 0xBF
class Serial(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    rx: am.lib.wiring.In(1)
    tx: am.lib.wiring.Out(1)

    rts: am.lib.wiring.Out(1)

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.mc6850 = mc6850 = zooby.chips.Mc6850()

        m.d.comb += [
            mc6850.rx.eq(self.rx),
            self.rts.eq(~mc6850.rts_n),
            self.tx.eq(mc6850.tx),
            self.bus.int.eq(~mc6850.irq_n),
            mc6850.cs0.eq(~self.bus.m1),
            mc6850.cs2_n.eq(self.bus.memory.addr[6]),
            mc6850.cs1.eq(self.bus.memory.addr[7]),
            mc6850.rs.eq(self.bus.memory.addr[0]),
            mc6850.r_w_n.eq(~self.bus.memory.wr),
            mc6850.e.eq(self.bus.memory.iorq),
            mc6850.d_in.eq(self.bus.memory.data_wr),
            self.bus.memory.data_rd.eq(mc6850.d_out),
            self.bus.memory.data_rd_valid.eq(mc6850.d_out_valid),
        ]

        return m
