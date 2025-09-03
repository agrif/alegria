import amaranth as am
import amaranth.lib.wiring

class ClockDivider(am.lib.wiring.Component):
    def __init__(self, max_divisor):
        self.max_divisor = max_divisor

        super().__init__({
            'divisor': am.lib.wiring.In(range(max_divisor + 1), init=1),
            'load': am.lib.wiring.In(1),
            'en': am.lib.wiring.In(1),
            'pulse': am.lib.wiring.Out(1),
        })

    def elaborate(self, platform):
        m = am.Module()

        counter = am.Signal(am.Signal(range(self.max_divisor)).shape().width + 1)
        counter_next = counter - self.en
        m.d.sync += counter.eq(counter_next)
        m.d.comb += self.pulse.eq(counter_next[-1])

        with m.If(self.load | self.pulse):
            # divisor - 1, or 0 if divisor == 0
            m.d.sync += counter.eq(self.divisor - self.divisor.any())

        return m
