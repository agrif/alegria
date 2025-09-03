import amaranth as am
import amaranth.lib.wiring

# Texas Instruments 74x245
# octal bus transciever with 3-state outputs
class Ti74x245(am.lib.wiring.Component):
    dir: am.lib.wiring.In(1)

    a_in: am.lib.wiring.In(8)
    a_out: am.lib.wiring.Out(8)
    a_out_valid: am.lib.wiring.Out(1)

    b_in: am.lib.wiring.In(8)
    b_out: am.lib.wiring.Out(8)
    b_out_valid: am.lib.wiring.Out(1)

    oe_n: am.lib.wiring.In(1, init=1)

    @property
    def pins(self):
        return {
            1: self.dir,
            2: (self.a_in[0], self.a_out[0]),
            3: (self.a_in[1], self.a_out[1]),
            4: (self.a_in[2], self.a_out[2]),
            5: (self.a_in[3], self.a_out[3]),
            6: (self.a_in[4], self.a_out[4]),
            7: (self.a_in[5], self.a_out[5]),
            8: (self.a_in[6], self.a_out[6]),
            9: (self.a_in[7], self.a_out[7]),
            # 10: gnd,
            11: (self.b_in[7], self.b_out[7]),
            12: (self.b_in[6], self.b_out[6]),
            13: (self.b_in[5], self.b_out[5]),
            14: (self.b_in[4], self.b_out[4]),
            15: (self.b_in[3], self.b_out[3]),
            16: (self.b_in[2], self.b_out[2]),
            17: (self.b_in[1], self.b_out[1]),
            18: (self.b_in[0], self.b_out[0]),
            19: self.oe_n,
            # 20: vcc,
        }

    def elaborate(self, platform):
        m = am.Module()

        with m.If(~self.oe_n):
            with m.If(self.dir):
                # A -> B
                m.d.comb += [
                    self.b_out.eq(self.a_in),
                    self.b_out_valid.eq(1),
                ]
            with m.Else():
                # B -> A
                m.d.comb += [
                    self.a_out.eq(self.b_in),
                    self.a_out_valid.eq(1),
                ]

        return m
