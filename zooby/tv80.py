import importlib

import amaranth as am
import amaranth.lib.enum
import amaranth.lib.wiring

import zooby.bus

class Mode(am.lib.enum.Enum):
    Z80 = 0
    FAST_Z80 = 1
    I8080 = 2
    GB = 3

class Variant(am.lib.enum.StrEnum):
    S = 'tv80s'
    N = 'tv80n'

    def t2write_default(self):
        if self == self.S:
            return True
        else:
            return False

TV80_FILES = ['tv80_alu.v', 'tv80_core.v', 'tv80_mcode.v', 'tv80_reg.v', 'tv80n.v', 'tv80s.v']

def add_tv80_files(platform):
    for name in TV80_FILES:
        platform.add_file('tv80/' + name, importlib.resources.files().joinpath('tv80', name).read_text())

class BareCpu(am.lib.wiring.Component):
    wait_n: am.lib.wiring.In(1, init=1)
    int_n: am.lib.wiring.In(1, init=1)
    nmi_n: am.lib.wiring.In(1, init=1)
    busrq_n: am.lib.wiring.In(1, init=1)

    m1_n: am.lib.wiring.Out(1)
    mreq_n: am.lib.wiring.Out(1)
    iorq_n: am.lib.wiring.Out(1)
    rd_n: am.lib.wiring.Out(1)
    wr_n: am.lib.wiring.Out(1)
    rfsh_n: am.lib.wiring.Out(1)
    halt_n: am.lib.wiring.Out(1)
    busak_n: am.lib.wiring.Out(1)

    A: am.lib.wiring.Out(16)
    di: am.lib.wiring.In(8)
    dout: am.lib.wiring.Out(8)

    def __init__(self, variant=Variant.N, mode=Mode.Z80, t2write=None, iowait=True):
        if t2write is None:
            t2write = variant.t2write_default()

        self.variant = variant
        self.mode = mode
        self.t2write = t2write
        self.iowait = iowait

        super().__init__()

    def elaborate(self, platform):
        add_tv80_files(platform)

        instance = am.Instance(
            self.variant.value,

            p_Mode=self.mode.value,
            p_T2Write=self.t2write,
            p_IOWait=self.iowait,

            i_reset_n=~am.ResetSignal(),
            i_clk=am.ClockSignal(),

            i_wait_n=self.wait_n,
            i_int_n=self.int_n,
            i_nmi_n=self.nmi_n,
            i_busrq_n=self.busrq_n,

            o_m1_n=self.m1_n,
            o_mreq_n=self.mreq_n,
            o_iorq_n=self.iorq_n,
            o_rd_n=self.rd_n,
            o_wr_n=self.wr_n,
            o_rfsh_n=self.rfsh_n,
            o_halt_n=self.halt_n,
            o_busak_n=self.busak_n,

            o_A=self.A,
            i_di=self.di,
            o_dout=self.dout,
        )

        return instance

class Cpu(am.lib.wiring.Component):
    bus: am.lib.wiring.Out(zooby.bus.RcBus())

    def __init__(self, variant=Variant.N, mode=Mode.Z80, t2write=None, iowait=True):
        self._bare = BareCpu(variant=variant, mode=mode, t2write=t2write, iowait=iowait)
        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.bare = bare = self._bare

        m.d.comb += [
            bare.wait_n.eq(~self.bus.memory.wait),
            bare.int_n.eq(~self.bus.int),
            bare.nmi_n.eq(~self.bus.nmi),
            bare.busrq_n.eq(~self.bus.busreq),

            self.bus.m1.eq(~bare.m1_n),
            self.bus.memory.mreq.eq(~bare.mreq_n),
            self.bus.memory.iorq.eq(~bare.iorq_n),
            self.bus.memory.rd.eq(~bare.rd_n),
            self.bus.memory.wr.eq(~bare.wr_n),
            self.bus.rfsh.eq(~bare.rfsh_n),
            self.bus.halt.eq(~bare.halt_n),
            self.bus.busack.eq(~bare.busak_n),

            self.bus.memory.addr.eq(bare.A),
            bare.di.eq(self.bus.memory.data_rd),
            self.bus.memory.data_wr.eq(bare.dout),
        ]

        return m
