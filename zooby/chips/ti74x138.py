import amaranth as am
import amaranth.lib.wiring

class Ti74x138(am.lib.wiring.Component):
    a: am.lib.wiring.In(1)
    b: am.lib.wiring.In(1)
    c: am.lib.wiring.In(1)

    g2a_n: am.lib.wiring.In(1)
    g2b_n: am.lib.wiring.In(1)
    g1: am.lib.wiring.In(1)

    # note: active low, but datasheet just calls it 'Y'
    y: am.lib.wiring.Out(8, init=-1)

    @property
    def pins(self):
        return [
            self.a,
            self.b,
            self.c,
            self.g2a_n,
            self.g2b_n,
            self.g1,
            self.y[7],
            None, # ground
            self.y[6],
            self.y[5],
            self.y[4],
            self.y[3],
            self.y[2],
            self.y[1],
            self.y[0],
            None, # vcc
        ]

    @property
    def select(self):
        return am.Cat(self.a, self.b, self.c)

    def elaborate(self, platform):
        m = am.Module()

        enable = am.Signal(1)
        m.d.comb += enable.eq(self.g1 & ~self.g2a_n & ~self.g2b_n)

        with m.If(enable):
            m.d.comb += self.y.bit_select(self.select, 1).eq(0)

        return m
