import unittest

import amaranth as am
import amaranth.asserts
import amaranth.lib.wiring

from alegria.test import FormalTestCase

class Counter(am.lib.wiring.Component):
    en: am.lib.wiring.In(1)
    count: am.lib.wiring.Out(8)

    def elaborate(self, platform):
        m = am.Module()

        with m.If(self.en):
            m.d.sync += self.count.eq(self.count + 1)

        return m

class FormalSpec(am.Elaboratable):
    def elaborate(self, platform):
        m = am.Module()

        m.submodules.counter = counter = Counter()
        m.d.sync += [
            counter.en.eq(am.asserts.AnySeq(1)),
        ]

        last_reset = am.Signal(1, reset_less=True)
        last_en = am.Signal(1, reset_less=True)
        last_count = am.Signal(counter.count.shape(), reset_less=True)

        m.d.sync += [
            last_reset.eq(am.ResetSignal()),
            last_en.eq(counter.en),
            last_count.eq(counter.count),
        ]

        with m.If(~last_reset):
            m.d.sync += am.Assert(counter.count == last_count + last_en)
        with m.Else():
            m.d.sync += am.Assert(counter.count == 0)

        return m

class FormalSpecBadReset(am.Elaboratable):
    def elaborate(self, platform):
        m = am.Module()

        m.submodules.counter = counter = Counter()
        m.d.sync += [
            counter.en.eq(am.asserts.AnySeq(1)),
        ]

        last_en = am.Signal(1, reset_less=True)
        last_count = am.Signal(counter.count.shape(), reset_less=True)

        m.d.sync += [
            last_en.eq(counter.en),
            last_count.eq(counter.count),
        ]

        m.d.sync += am.Assert(counter.count == last_count + last_en)

        return m

class TestFormal(FormalTestCase):
    def test_formal(self):
        self.assertFormal(FormalSpec(), depth=10)

    @unittest.expectedFailure
    def test_formal_fail(self):
        self.assertFormal(FormalSpecBadReset(), depth=10)
