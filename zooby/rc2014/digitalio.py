import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.chips

class _DigitalIOCommon(am.lib.wiring.Component):
    def __init__(self, debug=False):
        self._debug = debug
        super().__init__()

    def _elaborate_decoder(self, platform, m, decoder):
        raise NotImplementedError()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.decoder = decoder = zooby.chips.Ti74x138()
        m.submodules.input = input = zooby.chips.Ti74x245()
        m.submodules.output = output = zooby.chips.Ti74x374()

        input_sel, output_sel = self._elaborate_decoder(platform, m, decoder)

        # original board doesn't have this but we'll add it
        # inputs are usually not synchronized, sync them here
        input_sync = am.Signal(8)
        m.submodules.input_sync = am.lib.cdc.FFSynchronizer(i=self.input, o=input_sync)

        m.d.comb += [
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

        if self._debug:
            with m.If(~input_sel):
                m.d.comb += am.Print(am.Format('digitalio/r 0x{:02x}', self.bus.memory.data_rd))
            with m.If(~output_sel):
                m.d.comb += am.Print(am.Format('digitalio/w 0x{:02x}', self.bus.memory.data_wr))

        return m

# Digital IO v1
# IO ports 0x00, 0x04, .., 0x7c (default)
# https://rc2014.co.uk/modules/other-modules/digital-io-v1-0/
class DigitalIOv1(_DigitalIOCommon):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    input: am.lib.wiring.In(8)
    output: am.lib.wiring.Out(8)

    def __init__(self, link0=0, link1=1, link7=7, debug=False):
        if not all(link in range(16) for link in [link0, link1, link7]):
            raise ValueError('links must be an address bit (0-15)')

        self.link0 = link0
        self.link1 = link1
        self.link7 = link7

        super().__init__(debug=debug)

    def _elaborate_decoder(self, platform, m, decoder):
        # these are hard traces
        input_sel = decoder.y[4]
        output_sel = decoder.y[0]

        m.d.comb += [
            decoder.a.eq(self.bus.memory.addr[self.link0]),
            decoder.b.eq(self.bus.memory.addr[self.link1]),
            decoder.c.eq(self.bus.memory.wr_n),

            decoder.g1.eq(self.bus.m1_n),
            decoder.g2b_n.eq(self.bus.memory.iorq_n),
            decoder.g2a_n.eq(self.bus.memory.addr[self.link7]),
        ]

        return (input_sel, output_sel)

# Digital IO v2
# IO ports 0x00 (default, selectable from 0x00-0x03)
# https://rc2014.co.uk/modules/digital-io/
class DigitalIOv2(_DigitalIOCommon):
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

        super().__init__(debug=debug)

    def _elaborate_decoder(self, platform, m, decoder):
        # this is done on the board with diodes and a pull-down
        addr_or = self.bus.memory.addr[2:8].any()

        # these are configured with jumpers
        input_sel = decoder.y[4:][self.input_port]
        output_sel = decoder.y[:4][self.output_port]

        m.d.comb += [
            decoder.a.eq(self.bus.memory.addr[0] * self.link_a0),
            decoder.b.eq(self.bus.memory.addr[1] * self.link_a1),
            decoder.c.eq(self.bus.memory.wr_n),

            decoder.g1.eq(self.bus.m1_n),
            decoder.g2b_n.eq(self.bus.memory.iorq_n),
            decoder.g2a_n.eq(addr_or),
        ]

        return (input_sel, output_sel)
