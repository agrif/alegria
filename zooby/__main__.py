import importlib

import click

import zooby.cxxrtl
import zooby.demo

@click.group
def cli():
    pass

@cli.command
def build():
    platform = zooby.cxxrtl.CxxRtlPlatform()
    platform.add_file('cxxrtl/driver.cpp', importlib.resources.files().joinpath('cxxrtl_driver.cpp').read_text())

    top = zooby.demo.Demo('R0001009.bin')
    platform.build(top)

if __name__ == '__main__':
    cli()
