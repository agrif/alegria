import amaranth as am
import amaranth.build
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
        with open(self.rom_file, 'rb') as f:
            self.rom_data = f.read()[self.rom_start:self.rom_start + self.rom_size]

        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        # generate an appropriate sysclk to reach 115200 baud
        m.domains.sysclk = am.ClockDomain()
        m.submodules.pll = pll = platform.generate_pll(platform.default_clk_period, am.Period(Hz=115200 * 64), 'sysclk')

        # add a reset to our sysclk, with a button if we have it
        try:
            reset_button = platform.request('button').i
        except am.build.ResourceError:
            reset_button = 0
        sysclk_reset = reset_button | ~pll.lock | am.ResetSignal()
        m.submodules.reset_sync = am.lib.cdc.ResetSynchronizer(arst=sysclk_reset, domain='sysclk', stages=2)

        m.submodules.system = system = am.DomainRenamer('sysclk')(System(self.rom_data))

        # connect the uart pins
        try:
            uart = platform.request('uart')
            m.d.comb += [
                uart.tx.o.eq(system.tx),
                system.rx.eq(uart.rx.i),
            ]
        except am.build.ResourceError:
            pass

        return m

class System(am.lib.wiring.Component):
    bus: am.lib.wiring.Out(zooby.bus.RcBus())

    rx: am.lib.wiring.In(1)
    tx: am.lib.wiring.Out(1)

    rts: am.lib.wiring.Out(1)

    def __init__(self, rom_data):
        self.rom_data = rom_data
        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.tv80 = tv80 = zooby.tv80.Cpu()
        m.submodules.bus = bus = zooby.bus.RcBusMultiplexer()
        am.lib.wiring.connect(m, tv80.bus, bus.bus)
        bus.add(am.lib.wiring.flipped(self.bus))

        m.submodules.rom = rom = zooby.memory.Rom(0x0000, len(self.rom_data), init=self.rom_data)
        bus.add(rom.bus)

        m.submodules.ram = ram = zooby.memory.Ram(0x8000, 0x8000)
        bus.add(ram.bus)

        m.submodules.serial = serial = zooby.rc2014.SerialIO()
        bus.add(serial.bus)
        m.d.comb += [
            serial.rx.eq(self.rx),
            self.tx.eq(serial.tx),
            self.rts.eq(serial.rts),
        ]

        return m
