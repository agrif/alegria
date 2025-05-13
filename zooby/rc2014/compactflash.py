import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.chips
import zooby.lib.compactflash

# Compact Flash Module v1
# IO ports 0x10-0x17 (primary) and 0x90-0x97
# https://rc2014.co.uk/modules/compact-flash-module/compact-flash-module-v1/
class CompactFlashv1(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    card: am.lib.wiring.Out(zooby.lib.compactflash.CompactFlashConnector())
    busy: am.lib.wiring.Out(1)

    def __init__(self, debug=False):
        self._debug = debug
        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.decoder = decoder = zooby.chips.Ti74x138()

        # hard trace on the board
        sel = decoder.y[2]

        m.d.comb += [
            decoder.a.eq(self.bus.memory.addr[3]),
            decoder.b.eq(self.bus.memory.addr[4]),
            decoder.c.eq(self.bus.memory.addr[5]),

            decoder.g1.eq(self.bus.m1_n),
            decoder.g2b_n.eq(self.bus.memory.iorq_n),
            decoder.g2a_n.eq(self.bus.memory.addr[6]),

            self.bus.memory.data_rd.eq(self.card.data_rd),
            self.bus.memory.data_rd_valid.eq(self.card.data_rd_valid),
            self.card.data_wr.eq(self.bus.memory.data_wr),
            self.card.addr.eq(self.bus.memory.addr[:3]),

            self.card.cs0_n.eq(sel),
            self.card.ata_sel_n.eq(0),
            self.card.cs1_n.eq(1),
            self.card.iord_n.eq(self.bus.memory.rd_n),
            self.card.iowr_n.eq(self.bus.memory.wr_n),
            self.card.we_n.eq(1),
            self.card.csel_n.eq(0),
            self.card.reset_n.eq(~am.ResetSignal()),
            self.card.h.eq(1),
            self.busy.eq(~self.card.dasp_n),
            self.card.pdiag_n.eq(1),
        ]

        if self._debug:
            cs = self.card.cs0_n & self.card.cs1_n
            with m.If(~cs & ~self.card.iord_n):
                m.d.comb += am.Print(am.Format('compactflash/r cs={}{} 0x{:01x} 0x{:02x}', self.card.cs1_n, self.card.cs0_n, self.card.addr, self.card.data_rd))
            with m.If(~cs & ~self.card.iowr_n):
                m.d.comb += am.Print(am.Format('compactflash/w cs={}{} 0x{:01x} 0x{:02x}', self.card.cs1_n, self.card.cs0_n, self.card.addr, self.card.data_wr))

        return m
