import amaranth as am
import amaranth.lib.wiring

class Counter(am.lib.wiring.Component):
    en: am.lib.wiring.In(1, init=1)
    ovf: am.lib.wiring.Out(1)

    def __init__(self, limit):
        self.limit = limit
        self.count = am.Signal(16)

        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.d.comb += self.ovf.eq(self.count == self.limit)

        with m.If(self.en):
            with m.If(self.ovf):
                m.d.sync += self.count.eq(0)
            with m.Else():
                m.d.sync += self.count.eq(self.count + 1)

        return m
