#

#

import logging
import click
import importlib
from mcutool import __version__


class ComplexCLI(click.MultiCommand):

    COMMANDS = [
        'build',
        'list',
        'scan',
        'config',
        'cmake',
        'elfcov',
        "merge_mf"
        # 'gdbserver',
        # 'flash'
    ]

    def list_commands(self, ctx):
        return self.COMMANDS

    def get_command(self, ctx, name):
        mod = importlib.import_module(f'mcutool.commands.{name}')
        return mod.cli



@click.command(cls=ComplexCLI, invoke_without_command=True, help="mcutool command line tool")
@click.option('-v', '--verbose', is_flag=True, help='show more console message')
@click.option('--version', is_flag=True, help="show mcutool version")
def main(version=False, verbose=False, debug=False):
    if verbose:
        logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.WARNING)

    if version:
        click.echo(__version__)


if __name__ == '__main__':
    main()
