import importlib

import amaranth as am
import amaranth.back.verilog
import click

class Demo(am.Elaboratable):
    def elaborate(self, platform):
        import amaranth.lib.wiring
        import zooby.bus
        import zooby.memory
        import zooby.serial
        import zooby.tv80

        m = am.Module()

        m.submodules.tv80 = tv80 = zooby.tv80.Cpu()
        m.submodules.bus = bus = zooby.bus.RcBusMultiplexer()
        am.lib.wiring.connect(m, tv80.bus, bus.bus)

        with open('R0001009.bin', 'rb') as f:
            data = f.read()

        m.submodules.rom = rom = zooby.memory.Rom(0x0000, 0x2000, init=data[0x0000:0x2000])
        bus.add(rom.bus)

        m.submodules.ram = ram = zooby.memory.Ram(0x8000, 0x8000)
        bus.add(ram.bus)

        m.submodules.serial = serial = zooby.serial.Serial()
        bus.add(serial.bus)

        return m

@click.group
def cli():
    pass

@cli.command
def build():
    import zooby.cxxrtl

    platform = zooby.cxxrtl.CxxRtlPlatform()
    platform.add_file('cxxrtl/driver.cpp', importlib.resources.files().joinpath('cxxrtl_driver.cpp').read_text())

    top = Demo()
    platform.build(top)

if __name__ == '__main__':
    cli()
