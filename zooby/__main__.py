import importlib

import click

import zooby.demo
import zooby.platforms

PLATFORMS = {
    'cxxrtl': zooby.platforms.CxxRtlPlatform,
    'tangnano9k': zooby.platforms.TangNano9kPlatform,
}

@click.group
def cli():
    pass

class BasedInt(click.ParamType):
    name = 'integer'

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        try:
            return int(value, 0)
        except ValueError:
            self.fail('%s is not a valid integer' % value, param, ctx)

@cli.command
@click.option('--platform', '-p', type=click.Choice(PLATFORMS.keys()), default='cxxrtl')
@click.option('--toolchain', '-t', metavar='TOOLCHAIN')
@click.argument('rom-file')
@click.option('--rom-start', type=BasedInt(), default=0x0000)
@click.option('--rom-size', type=BasedInt(), default=0x2000)
@click.option('--program/--no-program', default=True)
def build(**options):
    platform_kwargs = {}
    if options['toolchain']:
        platform_kwargs['toolchain'] = options['toolchain']

    platform = PLATFORMS[options['platform']](**platform_kwargs)

    top = zooby.demo.Demo(options['rom_file'], rom_start=options['rom_start'], rom_size=options['rom_size'])
    platform.build(top, do_program=options['program'])

if __name__ == '__main__':
    cli()
