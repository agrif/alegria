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
@click.argument('rom-file')
@click.option('--rom-start', type=BasedInt(), default=0x0000)
@click.option('--rom-size', type=BasedInt(), default=0x2000)
@click.option('--platform', '-p', type=click.Choice(PLATFORMS.keys()), default='cxxrtl')
@click.option('--toolchain', '-t', metavar='TOOLCHAIN')
@click.option('--generate', '-g', is_flag=True)
@click.option('--archive', '-a', type=click.File('wb'))
@click.option('--path', default='build')
@click.option('--top-name', default='top')
@click.option('--ssh')
@click.option('--ssh-path')
@click.option('--program/--no-program')
def build(**options):
    if options['archive']:
        options['generate'] = True

    if options['ssh'] and not options['ssh_path']:
        raise RuntimeError('ssh requires an ssh path')

    connect_to = dict()
    if options['ssh']:
        connect_to = dict(hostname=options['ssh'])

    platform_kwargs = {}
    if options['toolchain']:
        platform_kwargs['toolchain'] = options['toolchain']

    platform = PLATFORMS[options['platform']](**platform_kwargs)
    top = zooby.demo.Demo(options['rom_file'], rom_start=options['rom_start'], rom_size=options['rom_size'])

    build_kwargs = dict(
        name=options['top_name'],
        do_build=not options['generate'],
        build_dir=options['path'],
        do_program=options['program'],
        debug_verilog=True,
    )

    # this mess of logic mostly uses execute_remote_ssh when ssh is set
    # while still using build() for local stuff

    if options['ssh']:
        plan = platform.prepare(top, **build_kwargs)
        if options['generate']:
            result = plan
        else:
            products = plan.execute_remote_ssh(connect_to=connect_to, root=options['ssh_path'])
            if not options['program']:
                result = products
            else:
                platform.toolchain_program(products, options['top_name'], **build_kwargs.get('program_opts', {}))
                result = None
    else:
        result = platform.build(top, **build_kwargs)

    if options['generate']:
        plan = result
        if options['archive']:
            plan.archive(options['archive'])
        else:
            if options['ssh']:
                plan.execute_remote_ssh(connect_to=connect_to, root=options['ssh_path'], run_script=False)
            else:
                plan.extract(options['path'])
        return

    if not options['program']:
        products = result
        return

if __name__ == '__main__':
    cli()
