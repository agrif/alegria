import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.chips

# Digital IO v2
# IO ports 0x00-0x03 (selectable, by default just 0x00)
# https://rc2014.co.uk/modules/digital-io/
class DigitalIOv2(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    input: am.lib.wiring.In(8)
    output: am.lib.wiring.Out(8)

    def __init__(self, link_a0=True, link_a1=True, input_port=0, output_port=0, debug=False):
        if not input_port in range(4) or not output_port in range(4):
            raise ValueError('IO port must be 0, 1, 2, or 3')

        self.link_a0 = link_a0
        self.link_a1 = link_a1
        self.input_port = input_port
        self.output_port = output_port
        self.debug = debug

        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.decoder = decoder = zooby.chips.Ti74x138()
        m.submodules.input = input = zooby.chips.Ti74x245()
        m.submodules.output = output = zooby.chips.Ti74x374()

        # this is done on the board with diodes and a pull-down
        addr_or = self.bus.memory.addr[2:8].any()

        # these are configured with jumpers
        input_sel = decoder.y[4:][self.input_port]
        output_sel = decoder.y[:4][self.output_port]

        # original board doesn't have this but we'll add it
        # inputs are usually not synchronized, sync them here
        input_sync = am.Signal(8)
        m.submodules.input_sync = am.lib.cdc.FFSynchronizer(i=self.input, o=input_sync)

        m.d.comb += [
            decoder.a.eq(self.bus.memory.addr[0] * self.link_a0),
            decoder.b.eq(self.bus.memory.addr[1] * self.link_a1),
            decoder.c.eq(~self.bus.memory.wr),

            decoder.g1.eq(~self.bus.m1),
            decoder.g2b_n.eq(~self.bus.memory.iorq),
            decoder.g2a_n.eq(addr_or),

            input.oe_n.eq(input_sel),
            input.dir.eq(0),
            self.bus.memory.data_rd.eq(input.a_out),
            self.bus.memory.data_rd_valid.eq(input.a_out_valid),
            input.b_in.eq(input_sync),

            output.d.eq(self.bus.memory.data_wr),
            output.clk.eq(output_sel),
            output.oc_n.eq(0),
            self.output.eq(output.q),
        ]

        if self.debug:
            with m.If(~input_sel):
                m.d.comb += am.Print(am.Format('digitalio/r 0x{:02x}', self.bus.memory.data_rd))
            with m.If(~output_sel):
                m.d.comb += am.Print(am.Format('digitalio/w 0x{:02x}', self.bus.memory.data_wr))

        return m
