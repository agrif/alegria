import amaranth as am
import amaranth.lib.memory
import amaranth.lib.wiring

import zooby.bus

class Memory(am.lib.wiring.Component):
    bus: am.lib.wiring.In(zooby.bus.RcBus())

    def __init__(self, base_addr, size, read_only=False, init=[], debug=False):
        # round size up to the nearest power of two
        size = 1 << (size - 1).bit_length()

        # make sure our base address is aligned to our size
        if base_addr & (size - 1):
            raise RuntimeError('memory region not aligned to size')

        if size < len(init):
            raise RuntimeError('memory initializer larger than memory size')

        self.base_addr = base_addr
        self.size = size
        self.read_only = read_only
        self.init = init
        self.debug = debug

        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.memory = memory = am.lib.memory.Memory(shape=am.unsigned(8), depth=self.size, init=self.init)

        addr_bits = (self.size - 1).bit_length()
        select_bits = self.bus.signature.addr_width - addr_bits

        select = (self.bus.memory.addr[addr_bits:] << addr_bits) == self.base_addr

        memory_rd = memory.read_port(domain='comb')
        m.d.comb += memory_rd.addr.eq(self.bus.memory.addr[:addr_bits])

        with m.If(self.bus.memory.mreq & self.bus.memory.rd & select):
            if self.debug:
                m.d.sync += am.Print(am.Format("mem/r: 0x{:04x} + 0x{:04x}: 0x{:02x}", self.base_addr, memory_rd.addr, memory_rd.data))
            m.d.comb += [
                self.bus.memory.data_rd.eq(memory_rd.data),
                self.bus.memory.data_rd_valid.eq(1),
            ]

        if not self.read_only:
            memory_wr = memory.write_port(domain='sync')
            m.d.comb += [
                memory_wr.addr.eq(self.bus.memory.addr[:addr_bits]),
                memory_wr.data.eq(self.bus.memory.data_wr),
            ]

            with m.If(self.bus.memory.mreq & self.bus.memory.wr & select):
                if self.debug:
                    m.d.sync += am.Print(am.Format("mem/w: 0x{:04x} + 0x{:04x}: 0x{:02x}", self.base_addr, memory_wr.addr, memory_wr.data))
                m.d.comb += memory_wr.en.eq(1)

        return m


class Rom(Memory):
    def __init__(self, base_addr, size, **kwargs):
        super().__init__(base_addr, size, read_only=True, **kwargs)

class Ram(Memory):
    def __init__(self, base_addr, size, **kwargs):
        super().__init__(base_addr, size, read_only=False, **kwargs)
