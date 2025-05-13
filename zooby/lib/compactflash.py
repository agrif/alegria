import importlib

import amaranth as am
import amaranth.lib.wiring

import zooby.platforms

# compact flash interface
# https://pinoutguide.com/Memory/CompactFlash_pinout.shtml
class CompactFlashConnector(am.lib.wiring.Signature):
    def __init__(self):
        super().__init__({
            'data_rd': am.lib.wiring.In(16),
            'data_rd_valid': am.lib.wiring.In(1),
            'data_wr': am.lib.wiring.Out(16),
            'addr': am.lib.wiring.Out(11),

            'cs0_n': am.lib.wiring.Out(1),
            'oe_n': am.lib.wiring.Out(1),
            'wp': am.lib.wiring.Out(1),
            'cd2_n': am.lib.wiring.In(1),
            'cd1_n': am.lib.wiring.In(1),
            'cs1_n': am.lib.wiring.Out(1),
            'vs1_n': am.lib.wiring.In(1),
            'iord_n': am.lib.wiring.Out(1),
            'iowr_n': am.lib.wiring.Out(1),
            'we_n': am.lib.wiring.Out(1),
            'rdy_bsy': am.lib.wiring.In(1),
            'csel_n': am.lib.wiring.Out(1),
            'vs2_n': am.lib.wiring.In(1),
            'reset': am.lib.wiring.Out(1),
            'wait_n': am.lib.wiring.In(1),
            'inpack_n': am.lib.wiring.In(1),
            'reg_n': am.lib.wiring.Out(1),

            # these are bidirectional but only in cf mode? maybe?
            'dasp_n': am.lib.wiring.In(1),
            'pdiag_n': am.lib.wiring.Out(1),
        })

    def __eq__(self, other):
        return isinstance(other, CompactFlashConnector)

    def __repr__(self):
        return f'CompactFlashConnector()'

    def create(self, *, path=None, src_loc_at=0):
        return CompactFlashInterface(self, path=path, src_loc_at=1 + src_loc_at)

class CompactFlashInterface(am.lib.wiring.PureInterface):
    # alternate accessors for IDE mode
    @property
    def ata_sel_n(self):
        return self.oe_n

    @property
    def iocs16_n(self):
        return self.wp

    @property
    def intrq(self):
        return self.rdy_busy

    @property
    def reset_n(self):
        # oh boy
        return self.reset

    @property
    def iordy(self):
        return self.wait_n

    @property
    def h(self):
        return self.reg_n

class CompactFlashEmulator(am.lib.wiring.Component):
    card: am.lib.wiring.In(CompactFlashConnector())

    def elaborate(self, platform):
        if not isinstance(platform, zooby.platforms.CxxRtlPlatform):
            raise RuntimeError('CF emulator can only be used in cxxrtl')

        for name in ['cxxrtl_compactflash.v', 'cxxrtl_compactflash.cpp']:
            platform.add_file('cxxrtl/' + name.split('_', 1)[1], importlib.resources.files().joinpath('compactflash', name).read_text())

        return am.Instance(
            'cxxrtl_compactflash',
            i_clk=am.ClockSignal(),
            o_data_rd=self.card.data_rd,
            o_data_rd_valid=self.card.data_rd_valid,
            i_data_wr=self.card.data_wr,
            i_addr=self.card.addr,
            i_cs0_n=self.card.cs0_n,
            i_cs1_n=self.card.cs1_n,
            i_iord_n=self.card.iord_n,
            i_iowr_n=self.card.iowr_n,
            i_reset_n=self.card.reset_n,
            o_dasp_n=self.card.dasp_n,
        )
