import amaranth as am
import amaranth.lib.wiring

# Texas Instruments 74x374
# octal D-type edge-triggered flip-flops
class Ti74x374(am.lib.wiring.Component):
    # a concession to fpgas: clk is a clock enable
    # normally a load happens on the rising edge of clk
    # this is hard for fpgas when clk is, well, not a clock. which is often.
    # here, loads happen when ~clk and on the rising edge of sync.clk
    # this works ok, usually.

    oc_n: am.lib.wiring.In(1, init=1)
    clk: am.lib.wiring.In(1, init=1)

    q: am.lib.wiring.Out(8)
    q_valid: am.lib.wiring.Out(1)
    d: am.lib.wiring.In(8)

    @property
    def pins(self):
        return {
            1: self.oc_n,
            2: self.q[0],
            3: self.d[0],
            4: self.d[1],
            5: self.q[1],
            6: self.q[2],
            7: self.d[2],
            8: self.d[3],
            9: self.q[3],
            # 10: gnd,
            11: self.clk,
            12: self.q[4],
            13: self.d[4],
            14: self.d[5],
            15: self.q[5],
            16: self.q[6],
            17: self.d[6],
            18: self.d[7],
            19: self.q[7],
            # 20: vcc,
        }

    def elaborate(self, platform):
        m = am.Module()

        q_reg = am.Signal(8)

        # output control
        with m.If(~self.oc_n):
            m.d.comb += [
                self.q.eq(q_reg),
                self.q_valid.eq(1),
            ]

        # store
        with m.If(~self.clk):
            m.d.sync += q_reg.eq(self.d)

        return m
