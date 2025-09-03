import dataclasses
import functools
import importlib
import io
import pkgutil
import sys

import amaranth as am
import amaranth.back.cxxrtl
import amaranth.back.rtlil
import amaranth.back.verilog
import amaranth_boards
import click

import alegria.platforms

__all__ = ['BasedInt', 'Builder', 'Generator', 'BuildAndGenerate']

PLATFORM_CLASSES = [
    alegria.platforms.CxxRtlPlatform,
]

PLATFORMS = {}

def _import_platforms(root):
    for _, module_name, _ in pkgutil.walk_packages(root.__path__):
        # only look at top-level submodules
        if '.' in module_name:
            continue
        full_name = root.__name__ + '.' + module_name
        try:
            mod = importlib.import_module(full_name)
        except Exception:
            continue

        # look at every item inside the module for Platforms
        for name, item in vars(mod).items():
            # skip underscored things
            if name.startswith('_') or name.endswith('_'):
                continue
            # skip classes not defined in this module
            if getattr(item, '__module__', None) != mod.__name__:
                continue
            try:
                if issubclass(item, am.build.Platform):
                    PLATFORM_CLASSES.append(item)
            except TypeError:
                continue

# import all the boards we can from amaranth_boards
_import_platforms(amaranth_boards)

# turn classes in PLATFORM_CLASSES into named, upgraded PLATFORMS
for platform in PLATFORM_CLASSES:
    name = platform.__name__.lower()
    if name.endswith('platform'):
        name = name[:-len('platform')]
    name = name.rstrip('_')

    qualname = platform.__module__ + '.' + platform.__qualname__

    if issubclass(platform, am.vendor.GowinPlatform):
        platform = alegria.platforms.GowinPlatform.upgrade_platform(platform)

    PLATFORMS[name] = (qualname, platform)

PLATFORMS = {k: v for k, v in sorted(PLATFORMS.items())}

FORMATS = {
    'verilog': am.back.verilog.convert,
    'rtlil': am.back.rtlil.convert,
    'cxxrtl': am.back.cxxrtl.convert,
}

class BasedInt(click.ParamType):
    name = 'integer'

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        try:
            return int(value, 0)
        except ValueError:
            self.fail('%s is not a valid integer' % value, param, ctx)

@dataclasses.dataclass
class Builder:
    platform: str = 'cxxrtl'
    toolchain: str | None = None
    generate: bool = False
    archive: io.RawIOBase | None = None
    path: str = 'build'
    top_name: str = 'top'
    ssh: str | None = None
    ssh_path: str | None = None
    program: bool = False

    def build(self, top):
        if self.archive:
            self.generate = True

        if self.ssh and not self.ssh_path:
            raise ValueError('ssh requires an ssh path')

        connect_to = dict()
        if self.ssh:
            connect_to = dict(hostname=self.ssh)

        platform_kwargs = {}
        if self.toolchain:
            platform_kwargs['toolchain'] = self.toolchain

        platform = PLATFORMS[self.platform][1](**platform_kwargs)

        build_kwargs = dict(
            name=self.top_name,
            do_build=not self.generate,
            build_dir=self.path,
            do_program=self.program,
            debug_verilog=True,
        )

        # this mess of logic mostly uses execute_remote_ssh when ssh is set
        # while still using build() for local stuff

        if self.ssh:
            plan = platform.prepare(top, **build_kwargs)
            if self.generate:
                result = plan
            else:
                products = plan.execute_remote_ssh(connect_to=connect_to, root=self.ssh_path)
                if not self.program:
                    result = products
                else:
                    platform.toolchain_program(products, self.top_name, **build_kwargs.get('program_opts', {}))
                    result = None
        else:
            result = platform.build(top, **build_kwargs)

        if self.generate:
            plan = result
            if self.archive:
                plan.archive(self.archive)
            else:
                if self.ssh:
                    plan.execute_remote_ssh(connect_to=connect_to, root=self.ssh_path, run_script=False)
                else:
                    plan.extract(self.path)
            return

        if not self.program:
            products = result
            return

    @classmethod
    def _list_platforms(cls, ctx, param, value):
        if not value or ctx.resilient_parsing:
            return
        for name, (qualname, _) in PLATFORMS.items():
            click.echo(f'{name:<20s} {qualname}')
        ctx.exit()

    @classmethod
    def pass_builder(cls, f):
        @click.pass_context
        @click.option('--platform', '-p',
                      type=click.Choice(PLATFORMS.keys()), default='cxxrtl',
                      show_default=True, show_choices=False, metavar='PLATFORM',
                      help='target platform')
        @click.option('--list-platforms', is_flag=True, is_eager=True,
                      callback=cls._list_platforms, expose_value=False,
                      help='list available platforms then exit')
        @click.option('--toolchain', '-t', metavar='TOOLCHAIN',
                      help='toolchain to use for the target platform')
        @click.option('--generate', '-g', is_flag=True,
                      help='generate files only, do not build')
        @click.option('--archive', '-a', type=click.File('wb'),
                      help='compress generated files into a zip')
        @click.option('--path', default='build', metavar='BUILDPATH',
                      help='location to place generated and built files')
        @click.option('--top-name', default='top', metavar='TOP',
                      help='name of the toplevel module')
        @click.option('--ssh', metavar='HOST',
                      help='ssh host use for build')
        @click.option('--ssh-path', metavar='BUILDPATH',
                      help='path on ssh host to place files')
        @click.option('--program/--no-program',
                      help='program the board after build')
        def make_builder(ctx, *args, **kwargs):
            names = (k.name for k in dataclasses.fields(cls))
            builder = cls(**{k: kwargs.pop(k) for k in names})
            return ctx.invoke(f, builder, *args, **kwargs)

        return functools.update_wrapper(make_builder, f)

    @classmethod
    def cli(cls, top_factory, **kwargs):
        @click.command
        @cls.pass_builder
        def build(builder):
            builder.build(top_factory())
        build(**kwargs)

@dataclasses.dataclass
class Generator:
    format: str = 'verilog'
    output: io.TextIOBase = sys.stdout
    name: str | None = None
    prefix: str = 'am_'

    def generate(self, top):
        convert = FORMATS[self.format]
        if self.name:
            name = self.name
        else:
            name = self.prefix + top.__class__.__name__.lower()
        self.output.write(convert(top, name=name))

    @classmethod
    def pass_generator(cls, f):
        @click.pass_context
        @click.option('--format', '-f',
                      type=click.Choice(FORMATS.keys()), default='verilog',
                      help='output format', show_default=True)
        @click.option('--output', '-o', default='-', type=click.File('w'),
                      help='output file to write generated source to')
        @click.option('--name',
                      help='full name of the toplevel module')
        @click.option('--prefix', default='am_', show_default=True,
                      help='prefix for the name of the toplevel module')
        def make_generator(ctx, *args, **kwargs):
            names = (k.name for k in dataclasses.fields(cls))
            generator = cls(**{k: kwargs.pop(k) for k in names})
            return ctx.invoke(f, generator, *args, **kwargs)

        return functools.update_wrapper(make_generator, f)

    @classmethod
    def cli(cls, top_factory, **kwargs):
        @click.command
        @cls.pass_generator
        def generate(generator):
            generator.generate(top_factory())
        generate(**kwargs)

class BuildAndGenerate:
    def __init__(self, group=None, build_cmd=None, generate_cmd='generate'):
        if group:
            self.group = group
        else:
            self.group = click.Group()

        self.build_group = self.group
        if build_cmd:
            self.build_group = click.Group(build_cmd)
            self.group.add_command(self.build_group)

        self.generate_group = self.group
        if generate_cmd:
            self.generate_group = click.Group(generate_cmd)
            self.group.add_command(self.generate_group)

    def build(self, **kwargs):
        def _inner(f):
            @Builder.pass_builder
            @click.pass_context
            def _inner_build(ctx, builder, *args, **kwargs):
                top = ctx.invoke(f, *args, **kwargs)
                builder.build(top)
            return self.build_group.command(**kwargs)(
                functools.update_wrapper(_inner_build, f),
            )
        return _inner

    def generate(self, **kwargs):
        def _inner(f):
            @Generator.pass_generator
            @click.pass_context
            def _inner_generate(ctx, generator, *args, **kwargs):
                top = ctx.invoke(f, *args, **kwargs)
                generator.generate(top)
            return self.generate_group.command(**kwargs)(
                functools.update_wrapper(_inner_generate, f),
            )
        return _inner

    def run(self, **kwargs):
        return self.group.main(**kwargs)
