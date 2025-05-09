import amaranth as am
import amaranth.lib.wiring

import zooby.bus
import zooby.memory
import zooby.rc2014
import zooby.tv80

class Demo(am.Elaboratable):
    def __init__(self, rom_file, rom_start=0x0000, rom_size=0x2000):
        self.rom_file = rom_file
        self.rom_start = rom_start
        self.rom_size = rom_size

        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.tv80 = tv80 = zooby.tv80.Cpu()
        m.submodules.bus = bus = zooby.bus.RcBusMultiplexer()
        am.lib.wiring.connect(m, tv80.bus, bus.bus)

        with open(self.rom_file, 'rb') as f:
            rom_data = f.read()[self.rom_start:self.rom_start + self.rom_size]

        m.submodules.rom = rom = zooby.memory.Rom(0x0000, len(rom_data), init=rom_data)
        bus.add(rom.bus)

        m.submodules.ram = ram = zooby.memory.Ram(0x8000, 0x8000)
        bus.add(ram.bus)

        m.submodules.serial = serial = zooby.rc2014.SerialIO()
        bus.add(serial.bus)

        return m
