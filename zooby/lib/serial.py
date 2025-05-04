import importlib

import amaranth as am
import amaranth.lib.wiring

import zooby.cxxrtl

class Tx(am.lib.wiring.Component):
    def __init__(self, bits=8, txdomain='sync'):
        self.bits = bits
        self.txdomain = txdomain

        super().__init__({
            'tx': am.lib.wiring.Out(1, init=1),

            'data': am.lib.wiring.In(bits),
            'valid': am.lib.wiring.In(1),
            'ready': am.lib.wiring.Out(1),
        })

    @property
    def stream(self):
        stream = am.lib.stream.Signature(self.data.shape()).flip().create()
        stream.payload = self.data
        stream.valid = self.valid
        stream.ready = self.ready

    def elaborate(self, platform):
        m = am.Module()

        # use a blackbox in cxxrtl simulation
        if isinstance(platform, zooby.cxxrtl.CxxRtlPlatform):
            for name in ['cxxrtl_serial.v', 'cxxrtl_serial.cpp']:
                platform.add_file('cxxrtl/' + name, importlib.resources.files().joinpath('serial', name).read_text())

            return am.Instance(
                'cxxrtl_serial_tx',
                p_BITS=self.bits,
                i_clk=am.ClockSignal(),
                i_data=self.data,
                i_valid=self.valid,
                o_ready=self.ready,
            )

        # FIXME
        m.d.comb += self.ready.eq(1)

        return m
