import amaranth as am
import amaranth.lib.wiring

# Texas Instruments 74x138
# 3-line to 8-line decoder/demultiplexer
class Ti74x138(am.lib.wiring.Component):
    a: am.lib.wiring.In(1)
    b: am.lib.wiring.In(1)
    c: am.lib.wiring.In(1)

    g2a_n: am.lib.wiring.In(1)
    g2b_n: am.lib.wiring.In(1)
    g1: am.lib.wiring.In(1, init=1)

    # note: active low, but datasheet just calls it 'Y'
    y: am.lib.wiring.Out(8, init=-1)

    @property
    def pins(self):
        return {
            1: self.a,
            2: self.b,
            3: self.c,
            4: self.g2a_n,
            5: self.g2b_n,
            6: self.g1,
            7: self.y[7],
            # 8: gnd,
            9: self.y[6],
            10: self.y[5],
            11: self.y[4],
            12: self.y[3],
            13: self.y[2],
            14: self.y[1],
            15: self.y[0],
            # 16: vcc,
        }

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
