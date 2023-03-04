#

#

import os
import re
import glob
import platform
import logging
import tempfile

from mcutool.debugger.general import DebuggerBase
from mcutool.util import to_hex, get_max_version, run_command



class JLINK(DebuggerBase):
    """
    A wrapper for SEGGER-JLink.
    """

    @classmethod
    def get_latest(cls):
        """Get latest installed instance from the system.
        """
        return _scan_installed_instance()

    def __init__(self, *args, **kwargs):
        """Create an instance of the JLink debugger class.
        """
        super().__init__("jlink", *args, **kwargs)
        self.auto_find()

        osname = platform.system().lower()
        if osname == "windows":
            self._jlink_exe = os.path.join(self.path, "JLink.exe")
            self._jlink_gdbserver_exe = os.path.join(self.path, "JLinkGDBServerCL.exe")
        else:
            self._jlink_exe = os.path.join(self.path, "JLinkExe")
            self._jlink_gdbserver_exe = os.path.join(self.path, "JLinkGDBServerCLExe")

        self._connect_opt = None

    def auto_find(self):
        """Auto find available instance
        """
        if self.path:
            return

        _jlink = _scan_installed_instance()
        if _jlink and _jlink.is_ready:
            self.path = _jlink.path
            self.version = _jlink.version

    @property
    def is_ready(self):
        return os.path.exists(self._jlink_exe)

    def set_connection(self, type="usb", value=None):
        """Set J-Link connection. Default automaticlly select usb to connect.

        Manual to set connection options by value:
            - port: -p/--port <name>[,<speed>]
            - usb: -u/--usb [[[<vid>,]<pid>] | [<path>]]

            Example:
            - set connection with usb serial number:
                jlink.set_connection("usb", value="62100000")
            - set connection with ip address 127.0.0.1:3728:
                jlink.set_connection("ip", value="127.0.0.1:3728")

        Arguments:
            type {str} -- usb or ip.
            value {str} -- serial_number | ip:port
        """
        if type not in ("usb", "ip"):
            raise ValueError('connection type is incorrect, usb or ip?')

        if type == 'usb':
            self._connect_opt = ["-SelectEmuBySN", value]
        else:
            self._connect_opt = ["-ip", value]

    def set_board(self, board):
        if board.usbid:
            self.set_connection('usb', board.usbid)
        self._board = board

    def _run_jlink_exe(self, jlink_exe_cmd, timeout):
        """Run jlink.exe process.

        Arguments:
            jlink_exe_cmd {list or string} -- JLink.exe or JLinkExe command line
            timeout {int} -- Max timeout in seconds

        Returns:
            Tuple -- (retcode, output)
        """

        logging.debug(str(jlink_exe_cmd))
        rc, output = run_command(jlink_exe_cmd, timeout=timeout, stdout="capture")

        level = logging.DEBUG if rc == 0 else logging.ERROR
        logging.log(level, "JLink.exe output:\n%s", output)
        return rc, output

    def run_script(self, filename, auto_connect=True, timeout=60, **kwargs):
        """Run jlink script with JLink.exe with a timeout timer.

        Arguments:
            filename -- {string} path to jlink script.
            device -- {str} device name to connect, default it use board.devicename
            auto_connect -- {bool} auto connect to device when jlink startup
            speed -- {str} set target interface speed(khz), default=auto
            interface -- {str} default use board.interface
            jlinkscript -- {str} specify -jlinkscriptfile to use
            timeout -- {int} seconds for timeout value

        Returns:
            tuple -- (jlink_exit_code, console_output)
        """
        device = kwargs.get("device")
        interface = kwargs.get("interface")
        jlink_exe_cmd = [ self._jlink_exe ]

        if self._board:
            device = device or self._board.devicename
            interface = interface or self._board.interface
            if self._connect_opt:
                jlink_exe_cmd.extend(self._connect_opt)
        else:
            jlink_exe_cmd.extend(["-SelectEmuBySN", "6210000"])

        if device:
            jlink_exe_cmd.extend(["-Device", device])

        if interface:
            jlink_exe_cmd.extend(["-IF", interface])

        # default jtag chain
        if interface and interface.upper() == "JTAG":
            jlink_exe_cmd.append("-jtagconf")
            jlink_exe_cmd.append("-1,-1")

        if kwargs.get("speed"):
            jlink_exe_cmd.extend(["-speed", str(kwargs.get("speed"))])

        jlink_exe_cmd.extend(["-autoconnect", "1" if auto_connect else "0"])
        jlink_exe_cmd.extend(["-CommandFile", filename])

        if kwargs.get("jlinkscript"):
            jlink_exe_cmd.extend(["-jlinkscriptfile", kwargs.get("jlinkscript")])

        return self._run_jlink_exe(jlink_exe_cmd, timeout)

    def run_commands(self, commands, auto_connect=True, timeout=60,
            speed="auto", jlinkscript=None, device=None, interface=None, **kwargs):
        """Run a list of commands by JLink.exe.

        Arguments:
            commands -- {list} list of JLink commands
            device -- {str} device name to connect, default it use board.devicename
            auto_connect -- {bool} auto connect to device when jlink startup
            speed -- {str} set target interface speed, default=auto
            interface -- {str} default use board.interface
            jlinkscript -- {str} specify -jlinkscriptfile to use
            timeout -- {int} seconds for timeout value

        Returns:
            Tuple(int, str) -- returncode and console output
        """
        script_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        commands = '\n'.join(commands)
        script_file.write(commands)
        script_file.close()
        logging.debug(f'Using script file name: {script_file.name}')
        logging.debug(f'Running JLink commands: {commands}')

        return self.run_script(script_file.name, auto_connect, timeout,
            speed=speed, jlinkscript=jlinkscript, device=device, interface=interface)

    def test_conn(self):
        """Test debugger connection."""

        p1 = re.compile("Connecting to J-Link via USB.{3}FAILED")
        p2 = re.compile("Found.*JTAG")
        p3 = re.compile("Found.*SW")
        p4 = re.compile("JTAG chain detection found 1 devices")
        # If debugger is closed by ROM, will return "Error: Could not find core in Coresight setup"
        p5 = re.compile("Could not find core in Coresight setup")

        commands = [
            'regs',
            'qc'
        ]
        # Run commands.
        _, output = self.run_commands(commands, timeout=30)

        if p1.search(output) is not None:
            return "NotConnected"

        elif p5.search(output):
            return "Could not find core"

        elif (p2.search(output) is not None) or (p3.search(output) is not None) \
            or (p4.search(output) is not None):
            return "NoError"

        else:
            return "Error"

    def erase(self, start_addr=None, end_addr=None, **kwargs):
        """Erase flash.
        Arguments:
            start_addr: {int} start addr
            end_addr: {int} end addr
            timeout: {int} default 500
        """
        erase_cmd = kwargs.get('cmd', 'erase')
        timeout = kwargs.get('timeout', 500)

        if start_addr and end_addr:
            erase_cmd = "erase 0x{:x} 0x{:x}".format(start_addr, end_addr)

        logging.info(erase_cmd)

        commands = [
            'r',        # Reset
            'wh',       # Wait for CPU to halt
            erase_cmd,  # Erase
            'r',        # Reset
            'qc'        # Quit
        ]
        return self.run_commands(commands, timeout=timeout)

    def unlock(self):
        """Unlock kientis device."""

        commands = [
            'unlock Kinetis',
            'q'
        ]
        return self.run_commands(commands)

    def reset(self):
        """Hardware reset."""
        commands = [
            'r0',
            'r1',
            'q'
        ]
        # Run commands.
        logging.info("reseting board by jlink")
        return self.run_commands(commands, auto_connect=False, timeout=30)

    def read32(self, addr):
        (returncode, regVal) = self.read_reg32(addr)
        return int(regVal, 16)

    def write32(self, addr, value):
        self.write_reg32(addr, value)

    def write_reg32(self, regAddr, writeValue):
        """
        Write 32-bit register by JLink command line.
        """
        commands = [
            "w4 {0}, {1}".format(to_hex(regAddr), to_hex(writeValue)), # Write 32-bit register
            "qc"        # Quit
        ]

        # logging.info('Write 32-bit register:\n%s'%output)
        msg = 'Write 32-bit register...\n'\
              '================================\n'\
              'Writing {0} -> {1}\n'\
              '================================\n'.format(to_hex(writeValue), to_hex(regAddr))
        logging.info(msg)

        # Run commands.
        return self.run_commands(commands, timeout=30)

    def read_reg32(self, regAddr):
        """
        Read 32-bit register by JLink command line.
        """
        commands = [
            "mem {0}, 0x4".format(to_hex(regAddr)),       # read 32-bit register
            "qc"        # Quit
        ]
        returncode, output = self.run_commands(commands, timeout=30)
        if returncode:
            raise Exception('JLink script running failed ({0}), please check!'.format(returncode))

        pattern = to_hex(regAddr).replace("0x", '')
        matchObj = "(.*){0} = (.*) ".format(pattern)

        regVal = 'Unknown'

        for line in output.splitlines():
            if re.match(matchObj, line, re.I | re.M) == None:
                continue
            else:
                regValList = re.match(matchObj, line, re.I | re.M).group(2).split()
                regValList.reverse()
                regVal = '0x' + ''.join(regValList)
        if regVal == 'Unknown':
            raise Exception('Cannot read the register {0} or no match {1}'.format(to_hex(regAddr), matchObj))
        return (returncode, regVal)

    def savebin(self, file_name, addr, num_bytes):
        """
        Saves target memory into binary file.
        Syntax: savebin <filename>, <addr>, <NumBytes>
        """
        addr = to_hex(addr)
        num_bytes = to_hex(num_bytes)
        commands = [
            f"savebin {file_name}, {addr}, {num_bytes}",
            "qc"
        ]

        return self.run_commands(commands, timeout=30)

    def flash(self, filepath, addr=None, **kwargs):
        """Program binary to flash.
        The file could be ".bin" or ".hex". addr is the start address.
        """
        timeout = kwargs.get("timeout", self.DEFAULT_FLASH_TIMEOUT)
        address = 0
        if addr is not None:
            address = addr
        elif self._board.start_address:
            address = self._board.start_address

        # Build list of commands to program hex files.
        commands = ['r', 'waithalt', 'sleep 10']   # Reset and wait for CPU to halt

        # Program each hex file.
        if filepath.endswith(".hex"):
            commands.append(f'loadfile "{filepath}"')

        elif filepath.endswith(".bin"):
            commands.append(f'loadbin "{filepath}" {address}')

        commands.extend([
            'r',   # Reset
            'wh',  # Wait for CPU to halt
            'g',   # Run the MCU
            'qc'    # Quit
        ])
        logging.info("flash start address: %s", address)
        # call registerd callback function
        self._call_registered_callback("before_load")
        # Run commands.
        return self.run_commands(commands, timeout=timeout)

    def list_connected_devices(self):
        """Return a list of connected id list."""

        devices = list()
        ret, raw_data = self.run_commands(["ShowEmuList", "qc"], 10)
        if ret != 0:
            return devices

        reg1 = re.compile(r"number: -{0,1}\d{5,15}, ProductName:")
        reg2 = re.compile(r"-{0,1}\d{5,15}")

        for line in raw_data.split('\n'):
            if reg1.search(line)is not None:
                m = reg2.search(line)
                if m is not None:
                    usb_id = m.group(0)
                    if '-' in usb_id:
                        usb_id = str(0xFFFFFFFF + int(usb_id) + 1)
                    devices.append({'debugger': 'jlink', "type": 'jlink', 'usbid': usb_id})

        return devices

    def get_gdbserver(self, **kwargs):
        """Return gdbserver startup shell command.

        Example returns:
            JLinkGDBServerCL.exe -if <JTAG/SWD> -speed auto -device <device name> -port <port>
            --singlerun -strict -select usb=<usb serial number>
        """

        board = kwargs.get('board')
        speed = kwargs.get('speed', 'auto')
        interface = kwargs.get('interface', 'SWD')
        port = kwargs.get('port')
        usbid = kwargs.get('usbid')
        jlinkscript = kwargs.get('jlinkscript')
        devicename = kwargs.get('devicename')

        if board is None:
            board = self._board

        if board and board.gdbport:
            devicename = board.devicename
            interface = board.interface
            usbid = board.usbid

        if not devicename:
            logging.warning('jlink: device name is not set.')

        if not usbid:
            logging.warning('jlink: serial number is not set.')

        options = f"-if {interface} -singlerun -strict -noir"
        if devicename:
            options += f" -device {devicename}"

        if usbid not in (None, ""):
            options = f"-select usb={usbid} {options}"

        if port:
            options += f" -port {port}"

        if speed:
            options += f" -speed {speed}"

        if jlinkscript:
            options += f" -jlinkscriptfile {jlinkscript}"

        return f"\"{self._jlink_gdbserver_exe}\" {options}"

    @property
    def default_gdb_commands(self):
        """Defined default gdb commands for J-Link gdb-server."""

        commands = [
            "target remote localhost:{gdbport}",
            "monitor reset",
            "monitor halt",
            "load",
            "{PC_SP}",
            "monitor go",
            "q"
        ]

        return "\n".join(commands)



def _scan_installed_instance():
    osname = platform.system().lower()
    if osname == "windows":
        import winreg
        root_entries = [
            winreg.HKEY_LOCAL_MACHINE,
            winreg.HKEY_CURRENT_USER
        ]

        jlink_entries = [
            r"SOFTWARE\WOW6432Node\SEGGER\J-Link",
            r"SOFTWARE\SEGGER\J-Link"
        ]

        versions = list()
        for root_en in root_entries:
            for jlink_en in jlink_entries:
                try:
                    jlink_key = winreg.OpenKey(root_en, jlink_en, 0, winreg.KEY_READ)
                    path = winreg.QueryValueEx(jlink_key, "InstallPath")[0]
                    version = winreg.QueryValueEx(jlink_key, "CurrentVersion")[0]
                    winreg.CloseKey(jlink_key)
                    versions.append((path, version))
                except WindowsError:
                    pass

        if versions:
            m_path, m_version = get_max_version(versions)
            return JLINK(m_path, version=m_version)
        else:
            return None

    elif osname == 'linux':
        default_path = "/opt/SEGGER"
        jlinks = glob.glob(default_path + "/JLink*")
        if jlinks:
            jlinks.sort()
            path = jlinks[-1]
            version = path.split("JLink")[-1].replace('_', '')
            return JLINK(path, version=version)
        return None
