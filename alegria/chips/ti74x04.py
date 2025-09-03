import amaranth as am
import amaranth.lib.wiring

# Texas Instruments 74x04
# hex inverter
class Ti74x04(am.lib.wiring.Component):
    a: am.lib.wiring.In(6)
    y: am.lib.wiring.Out(6)

    @property
    def pins(self):
        return {
            1: self.a[0],
            2: self.y[0],
            3: self.a[1],
            4: self.y[1],
            5: self.a[2],
            6: self.y[2],
            # 7: gnd,
            8: self.y[3],
            9: self.a[3],
            10: self.y[4],
            11: self.a[4],
            12: self.y[5],
            13: self.a[5],
            # 14: vcc,
        }

    def elaborate(self, platform):
        m = am.Module()

        m.d.comb += self.y.eq(~self.a)

        return m
