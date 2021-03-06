import argparse

from .LcleanCommand import LcleanCommand
from .LstartCommand import LstartCommand
from .. import utils
from ..foundation.command.Command import Command
from ..strings import strings, wiki_description


class LrestartCommand(Command):
    __slots__ = ['parser']

    def __init__(self):
        Command.__init__(self)

        parser = argparse.ArgumentParser(
            prog='kathara lrestart',
            description=strings['lrestart'],
            epilog=wiki_description,
            add_help=False
        )

        parser.add_argument(
            '-h', '--help',
            action='help',
            default=argparse.SUPPRESS,
            help='Show an help message and exit.'
        )

        group = parser.add_mutually_exclusive_group(required=False)

        group.add_argument(
            "-n", "--noterminals",
            action="store_const",
            dest="terminals",
            const=False,
            default=True,
            help='Start the lab without opening terminal windows.'
        )
        group.add_argument(
            "-t", "--terminals",
            action="store_const",
            dest="terminals",
            const=True,
            help='Start the lab opening terminal windows.'
        )
        parser.add_argument(
            '-d', '--directory',
            required=False,
            help='Specify the folder containing the lab.'
        )
        parser.add_argument(
            '-F', '--force-lab',
            dest='force_lab',
            required=False,
            action='store_true',
            help='Force the lab to start without a lab.conf or lab.dep file.'
        )
        parser.add_argument(
            '-l', '--list',
            required=False,
            action='store_true',
            help='Show information about running machines after the lab has been started.'
        )
        parser.add_argument(
            '-o', '--pass',
            dest='options',
            metavar="OPTION",
            nargs='*',
            required=False,
            help="Apply options to all machines of a lab during startup."
        )
        parser.add_argument(
            '--xterm',
            required=False,
            help='Set a different terminal emulator application (Unix only).'
        )
        parser.add_argument(
            '-H', '--no-hosthome',
            dest="no_hosthome",
            required=False,
            action='store_false',
            help='/hosthome dir will not be mounted inside the machine.'
        )
        parser.add_argument(
            '-S', '--no-shared',
            dest="no_shared",
            required=False,
            action='store_false',
            help='/shared dir will not be mounted inside the machine.'
        )
        group.add_argument(
            "--privileged",
            action="store_true",
            required=False,
            help='Start the devices in privileged mode. MUST BE ROOT FOR THIS OPTION.'
        )

        self.parser = parser

    def run(self, current_path, argv):
        args = self.parser.parse_args(argv)

        lab_path = args.directory.replace('"', '').replace("'", '') if args.directory else current_path
        lab_path = utils.get_absolute_path(lab_path)

        lclean_argv = ['-d', args.directory] if args.directory else []

        LcleanCommand().run(lab_path, lclean_argv)
        LstartCommand().run(lab_path, argv)
