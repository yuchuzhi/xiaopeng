#

#

import os
import time
import logging

from mcutool.debugger import getdebugger
from mcutool.debugger.general import DebuggerBase
from mcutool.pserial import Serial

LOGGER = logging.getLogger(__name__)

class Board(object):
    """This class represent a general embedded device.

    """

    def __init__(self, name="", **kwargs):
        """Create a mcutool.Board instance.

        Arguments:
            name {string} -- board name
            devicename {string} -- device name
            interface {string} -- SWD/JTAG

        Keyword Arguments:
            debugger_type {string} -- debugger type, choices are defined in
        """
        self.main_spawn = None
        self._debugger = None
        self._serial_ports = list()

        self.name = name
        self.devicename = kwargs.get("devicename", "")
        self.interface = kwargs.get("interface", "SWD")
        self.debugger_type = kwargs.get("debugger_type", "general")
        self.gdbport = kwargs.get("gdbport", 3333)
        self.usbid = kwargs.get("usbid")
        self.start_address = kwargs.get("start_address", "0")

        self.sp = None
        self.pc = None
        self.resource = []
        self.debugger = getdebugger(self.debugger_type)

    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.devicename}, usbid={self.usbid})>"

    def get_main_spawn(self, open=True):
        """Return a spawn object which is used as main spawn for testing.

        In general situation, it create a seriaspawn from main serial port.
        If some board not use port for testing, you can custom this function
        to return a related spwan object, like rttSpawn.
        """
        if not self.ser_main:
            return

        if not self.main_spawn:
            self.main_spawn = self.ser_main.SerialSpawn(codec_errors="ignore")

        if open:
            self.main_spawn.open()

        return self.main_spawn

    def set_main_spawn(self, spawn):
        """
        Set main spawn.
        """
        self.main_spawn = spawn

    def write(self, s, delay=None) -> int:
        """Write data to main port of board.

        Returns:
            {int} number of bytes are sent
        """
        if not self.main_spawn:
            self.get_main_spawn()

        ln = self.main_spawn.write(s)
        if delay:
            time.sleep(delay)

        return ln

    def expect(self, pattern, timeout=3, **kw):
        """Expect pattern from self.main_spawn.

        It is a shortcut method for board.main_spawn.expect().
        Default self.main_spawn is the main serial port.
        """
        main_spawn = self.get_main_spawn()
        return main_spawn.expect(pattern=pattern, timeout=timeout, **kw)

    def adv_expect(self, patterns, timeout=3, stop_patterns=None, spawn=None) -> None:
        """Similar to `self.expect()`, but it support expect a list of
        patterns one by one. If you do not want the steam contains some patterns
        you can set `stop_patterns`. Onece stop patterns are matched, the expect
        will be stopped and `ExpectFail` exception will be raised.

        Raises:
            ExpectFail: when timeout or stop_patterns are matched .

        Arguments:
            patterns: {str} or {list} will be compiled to python re objects.
            timeout: {int} default=3s, timeout in seconds.
            stop_patterns: {str} or {list}, patterns to stop expect.
            spawn: {mcutool.spawn} object, if set it will use specified spawn. Default is None use main_spawn.

        Returns: None

        For example:
        ```
        # the input is 'something error foobar'
        board.adv_expect(['something', 'foobar'], stop_patterns=['error'])
        # Expect fail will be raised, due to it contains 'error'
        ```
        """
        if not spawn:
            self.get_main_spawn()
            spawn = self.main_spawn

        return spawn.adv_expect(patterns, timeout=timeout, stop_patterns=stop_patterns)

    def start_gdbserver(self, **kwargs):
        """Start a gdbserver in background.

        Arguments:
            background: {boolean} run gdbserver in background. default True.
            port: {int} server listen port
            jlinkscript: {string} jlinkscript path
            gdbserver_cmdline: {string} command line to start gdb server

        Returns:
            return subprocess.Popen instance if it is background,
            or returncode of gdbserver.
        """

        assert self.debugger, 'require vaild debugger'
        return self.debugger.start_gdbserver(**kwargs)

    def get_mount_point(self):
        """Return mount point by matching usbid.
        """
        import mbed_lstools
        mbeds = mbed_lstools.create()
        mbeds_devices = mbeds.list_mbeds(filter_function=lambda m: m["target_id"] in self.usbid)
        if not mbeds_devices:
            return
        return mbeds_devices[0]['mount_point']

    def set_serial(self, port, baudrate, **kwargs):
        """Set or add serial port to board object, this interface will pass all
        parameters to serial.Serial object. For more details, please refer to pyserial
        documentation: https://pythonhosted.org/pyserial/pyserial_api.html#classes.

        Default timeout=1.
        """
        timeout = kwargs.pop('timeout', 1)
        sp = Serial(timeout=timeout, **kwargs)
        sp.port = port
        sp.baudrate = baudrate
        self._serial_ports.append(sp)

    def get_serial(self, index=0) -> Serial:
        """Get serial port instance by index.
            0 -- main
            1 -- secondary
            2 -- third

        Arguments:
            index {int} -- the port index.

        Returns:
            pyserial, serila.Serial instance,
        """
        try:
            return self._serial_ports[index]
        except IndexError:
            return

    def remove_resource(self, res_inst):
        for res in self.resource:
            if id(res[1]) == id(res_inst):
                LOGGER.warning("find resource for %s", id(res_inst))
                self.resource.remove(res)

        LOGGER.warning("resource for %s not found", id(res_inst))
        return None

    def register_resource(self, res_inst, naming):
        """
        regist resources to board
        res_init: resource instance
        naming: name string of this resource
        """
        res = [naming, res_inst]

        self.resource.insert(-1, res)

    def find_resource_by_name(self, naming):
        """
        find a resource by name
        naming: the name of the resource
        return: the first match resource or None
        """
        for res in self.resource:
            if res[0] == naming:
                return res[1]

        LOGGER.debug("resource for %s not found", naming)
        return None

    def find_resource_by_type(self, type_string):
        """
        find a resource by type
        type_string: the name of resource type(class)
        return: a list of matched resource, otherwise None
        """
        ret = []
        for res in self.resource:
            if type(res[1]).__name__ == type_string:
                LOGGER.info("find resource for %s", type_string)
                ret.insert(-1, res[1])

        LOGGER.info("resource for %s not found", type_string)
        return None

    @property
    def debugger(self) -> DebuggerBase:
        if self._debugger:
            self._debugger.set_board(self)
        return self._debugger

    @debugger.setter
    def debugger(self, value):
        if not value:
            return
        if isinstance(value, DebuggerBase):
            self._debugger = value
        else:
            ValueError("This not a valid debugger object")

    @property
    def gdb_commands(self) -> str:
        """gdb.init is a string include gdb commands.

        It will be rendered before execute 'gdb -x gdb.init'.
        Default it is loaded from debugger.gdbinit_template.
        Overwrite this function can custom the commands.
        """
        return None

    @property
    def ser_main(self) -> Serial:
        """A shortcut attribute to access the main serial port object.
        """
        return self.get_serial(0)

    @property
    def ser_sec(self)-> Serial:
        """A shortcut attribute to access the secondary serial port object.
        """
        return self.get_serial(1)

    def reset_board_by_send_break(self, serial=None):
        """CMSIS-DAP firmware allows the target to be reset by sending a break command
        over the serial port.
        Default use the main serial port.
        """
        if serial == None:
            serial = self.ser_main

        logging.info('reset board by sending break to port: %s', serial.port)
        _opened_by_me = False
        if not serial.is_open:
            _opened_by_me = True
            serial.open()

        try:
            serial.send_break()
        except:
            serial.break_condition = False

        # if port status is aligned with the origin.
        if _opened_by_me:
            serial.close()

        return True

    def reset(self, method="debugger"):
        """Reset board. There are several methos allow user to reset board.
        By default it is debugger method.

        Reset method list:
            - debugger: use debugger(JTAG) to reset board
            - serial: send break via serial port

        Keyword Arguments:
            method {str} -- [description] (default: {"debugger"})
        """
        if method == 'serial':
            return self.reset_board_by_send_break()

        elif method == "debugger":
            assert self.debugger
            return self.debugger.reset()

        else:
            raise ValueError('unknow reset method %s'%method)

    def programming(self, filename, **kwargs):
        """Auto program binary to board.

        For general situation, it is avaliable for most boards.
        It will choose gdb or general method by filename extension.

        params:
            filename: path to image file.
        """
        LOGGER.info("programming %s", filename)
        ext = os.path.splitext(filename)[-1]
        if self.debugger_type in ("jlink", "pyocd"):
            if ext in (".bin", ".img"):
                return self.debugger.flash(filename, addr=self.start_address)
            else:
                return self.debugger.gdb_program(filename, **kwargs)
        else:
            return self.debugger.flash(filename, **kwargs)

    def check_serial(self):
        """Check serial port.
        """
        status = "pass"
        try:
            self.ser_main.write_timeout = 2
            self.ser_main.open()
        except Exception as err:
            status = str(err)
        finally:
            if self.ser_main and self.ser_main.is_open:
                self.ser_main.close()

        return status
