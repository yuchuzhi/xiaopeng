#

#
from __future__ import absolute_import
import os
import sys
import logging
import subprocess
from packaging import version
from mcutool.debugger.general import DebuggerBase
from mcutool.util import run_command


logging.getLogger('pyocd.coresight.rom_table').setLevel(logging.ERROR)


class PYOCD(DebuggerBase):
    """
    Wrap pyOCD to a standard debugger for pymcutk.

    pyOCD is an open source Python package for programming and debugging Arm Cortex-M
    microcontrollers using multiple supported types of USB debug probes. It is fully
    cross-platform, with support for Linux, macOS, and Windows.

    For more visit https://github.com/mbedmicro/pyOCD.
    """

    _PYOCD_VER = None
    _PYOCD_BUILTIN_TARGETS = None
    _PYOCD_CONNECT_HELPER = None

    @classmethod
    def lazy_import(cls):
        # lazy import in here, because pyocd is too large
        from pyocd import __version__ as pyocd_version
        from pyocd.core.helpers import ConnectHelper
        from pyocd.target import TARGET

        cls._PYOCD_BUILTIN_TARGETS = TARGET
        cls._PYOCD_VER = pyocd_version
        cls._PYOCD_CONNECT_HELPER = ConnectHelper

    def __init__(self, **kwargs):
        super().__init__("pyocd", ".", **kwargs)

        if not self._PYOCD_VER:
            self.lazy_import()

        self.pack_file = None
        self.target_override = None
        self.version = self._PYOCD_VER

    @property
    def is_ready(self):
        return self.version not in (None, '')

    def set_board(self, board):
        # workaround to clear the prefix of usbid
        if board.usbid and ":" in board.usbid:
            board.usbid = board.usbid.split(":")[-1]

        self._board = board
        self._check_overried_target(board.devicename)

    def get_session(self, **kwargs):
        """
        Create and return a pyocd Session.
        """

        if kwargs.get('auto_open') is False:
            kwargs['auto_open'] = False
            kwargs['open_session'] = False

        return self._PYOCD_CONNECT_HELPER.session_with_chosen_probe(
            blocking=False,
            unique_id=self._board.usbid,
            target_override=self.target_override,
            **kwargs
        )

    def _check_overried_target(self, devicename):
        """Overried target if device name is include in pyOCD.target.TARGET.
        This is very useful if you want to use other device target for debugging.
        """

        if devicename.endswith('pack') and os.path.exists(devicename):
            self.pack_file = devicename
            self.target_override = os.path.basename(self.pack_file).split(".")[1].replace("_DFP", "")

        elif self.is_ready and devicename in self._PYOCD_BUILTIN_TARGETS:
            self.target_override = devicename

    def _get_default_session_options(self):
        """ pyocd support to config options to control
        pyocd behaviour. Guide: https://github.com/mbedmicro/pyOCD/blob/master/docs/options.md
        """
        options = {}
        # pyocd 0.23: pre_reset to deal with low power mode
        # workaround for none kinetis series
        if self._board and self._board.name.startswith("frdm"):
            options['connect_mode'] = 'under-reset'

        return options

    def _build_cmd_args(self, board=None, options=None):
        """Build command line arguments."""
        if not board:
            board = self._board

        if not options:
            options = self._get_default_session_options()

        args = list()
        if board:
            args.append(f"-u {board.usbid}")

        if self.target_override:
            args.append(f'-t {self.target_override}')
            if self.pack_file:
                args.append(f'--pack {self.pack_file}')

        if options:
            for item in options.items():
                args.append("-O%s=%s" % (item[0], str(item[1]).lower()))

        return " ".join(args)

    def list_connected_devices(self):
        """List connected CMSIS-DAP devices."""

        probes = self._PYOCD_CONNECT_HELPER.get_all_connected_probes(blocking=False)
        devices = list()
        for probe in probes:
            device = {
                'usbid': probe.unique_id,
                'name': probe.description,
                'type': 'pyocd'
            }
            devices.append(device)
        return devices

    def test_conn(self):
        """Test debugger connection."""

        if self._board is None:
            raise ValueError("board is not set")

        msg = "NoError"
        try:
            with self.get_session():
                pass
        except Exception as err:
            msg = "ConnectError: %s" % str(err)

        return msg

    def read32(self, addr):
        with self.get_session(options={'connect_mode': 'attach'}) as session:
            return session.board.target.read_memory(addr)

    def write32(self, addr, value):
        with self.get_session(options={'connect_mode': 'attach'}) as session:
            session.board.target.write_memory(addr, value)

    def erase(self, **kwargs):
        """Mass erase flash."""

        timeout = kwargs.get("timeout", 300)

        opt_args = self._build_cmd_args(options={
            "resume_on_disconnect": False,
            "allow_no_cores": True
        })

        command = f"\"{sys.executable}\" -m pyocd erase --mass -v -W {opt_args}"
        logging.info(f"erase commad: {command}")
        return run_command(command, stdout=True, timeout=timeout)

    def reset(self):
        """Always perform a hardware reset"""

        logging.info("resetting board by pyocd")
        # do not auto open probe by session it self, because we do not need to
        # init target and flash. Just use probe to perform a hardware reset.
        # This can improve the stability even if board is in lower mode.
        session = self.get_session(auto_open=False)
        if not session:
            logging.error("cannot create session with probe id: %s", self._board.usbid)
            return False

        try:
            session.probe.open()
            session.probe.set_clock(1000000)
            session.probe.connect()
            session.probe.reset()
            session.probe.disconnect()
        finally:
            session.probe.close()

        logging.info("reset done.")
        return True

    def unlock(self):
        """Unlock board."""

        logging.info("unlock board")
        try:
            with self.get_session(options={'auto_unlock': True}):
                pass
            return True
        except:
            logging.exception("exception")
            return False

    def get_gdbserver(self, **kwargs):
        """Return gdb server command. If configured board.devicename is a target
        name in pyocd.target.TARGET. This will overried the target.
        """

        board = kwargs.get('board')
        port = kwargs.get('port')

        if board is None:
            board = self._board

        command = f"\"{sys.executable}\" -m pyocd gdbserver --no-wait"
        if port:
            command += f" --port {port}"

        if kwargs.get('erase'):
            command += f" --erase {kwargs['erase']}"

        if kwargs.get("script"):
            command += f" --script {kwargs['script']}"

        if kwargs.get("core"):
            command += f" --core {kwargs['core']}"

        options = self._get_default_session_options()

        # set console to disable telent server
        options['semihost_console_type'] = 'console'
        options['keep_unwritten'] = '0'

        command += " " + self._build_cmd_args(board, options)
        return command

    def flash_with_api(self, filepath, **kwargs):
        from pyocd.flash.file_programmer import FileProgrammer
        addr = kwargs.get('addr') or self._board.start_address

        if addr:
            logging.info("start address: %s", addr)
            if isinstance(addr, str):
                addr = int(addr, 0)

        # force set None if addr is invalid
        else:
            addr = None

        filepath = filepath.replace("\\", "/")
        options = self._get_default_session_options()
        session = self.get_session(options=options)

        if session is None:
            raise ValueError("No device available to flash")

        file_format = self.guess_image_format(filepath)

        with session:
            # call registerd callback function
            self._call_registered_callback("before_load")
            programmer = FileProgrammer(session, trust_crc=True)
            programmer.program(filepath, file_format, base_address=addr)
        return 0, ''

    def flash(self, filepath, **kwargs):
        """Flash chip with filepath. (bin, hex).

        Arguments:
            erase: erase chip yes or not.
            addr: {str} being the integer starting address for the bin file.
            timeout: {int}
        """

        # pyocd < 0.34.1: bug, pyocd load: cannot recognize path contains character `@`
        # so we use API to flash
        if version.parse(self.version) < version.parse("0.34.1"):
            return self.flash_with_api(filepath, **kwargs)

        timeout = kwargs.get("timeout")
        addr = kwargs.get('addr') or self._board.start_address

        filepath = filepath.replace("\\", "/")
        options = self._get_default_session_options()

        file_format = self.guess_image_format(filepath)
        opt_args = self._build_cmd_args(options=options)

        command = f"\"{sys.executable}\" -m pyocd load -W --format {file_format} {opt_args} {filepath}"

        if addr:
            logging.info("start address: %s", addr)
            command = f"{command} -a {addr}"

        try:
            logging.info(f"flash command: {command}")
            subprocess.check_call(command, shell=True, timeout=timeout)
        except subprocess.CalledProcessError as err:
            return err.returncode, err.output

        return 0, ''

    @property
    def default_gdb_commands(self):
        """Return default pypcd gdb commands."""
        commands = [
            "target remote localhost:{gdbport}",
            "monitor reset --halt",
            "monitor halt",
            "load",
            "{PC_SP}",
            "q"
        ]
        return "\n".join(commands)

    def __str__(self):
        return f"pyocd-{self.version}"

    @staticmethod
    def get_latest():
        """Return pyocd.Debugger instance."""
        return PYOCD()
