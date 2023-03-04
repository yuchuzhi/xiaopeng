#

#

import os
import time
import logging
import shutil
import subprocess
import threading
import socket
import errno
import shlex
from types import MethodType
from contextlib import closing

try:
    CREATE_NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
except AttributeError:
    CREATE_NEW_PROCESS_GROUP = 0

from pexpect.popen_spawn import PopenSpawn
from mcutool.compilers import compilerfactory
from mcutool.compilerbase import CompilerBase
from mcutool.gdb_session import GDBSession
from mcutool.exceptions import GDBServerStartupError



def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

def get_arm_gdb():
    if shutil.which("arm-none-eabi-gdb"):
        return "arm-none-eabi-gdb"

    armgcc_path, armgcc_version = compilerfactory('armgcc').get_latest()
    if armgcc_path:
        return os.path.join(armgcc_path, 'bin/arm-none-eabi-gdb')

    return "arm-none-eabi-gdb"



class DebuggerBase(CompilerBase):
    """A general debugger class to define basic debugger interfaces.

    All debugger should instantiat from this class.
    """

    DEFAULT_FLASH_TIMEOUT = 200

    STAGES = ['before_load']

    @classmethod
    def guess_image_format(cls, filepath) -> str:
        """Guess image format by it's extension.

        Possible formats: elf, hex, bin.
        """
        file_format = 'elf'
        if filepath.endswith(".bin"):
            file_format = 'bin'
        elif filepath.endswith('.hex'):
            file_format = 'hex'

        return file_format

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gdbpath = kwargs.get("gdbpath", "")
        self.version = kwargs.get("version", "unknown")
        self._gdbserver = None
        self._board = None
        self._callback_map = {"before_load": None}

    def __str__(self):
        return f"<Debugger: name={self.name}, version={self.version}>"

    @property
    def is_ready(self):
        return True

    def set_board(self, board):
        self._board = board

    @property
    def gdbexe(self):
        """
        GDB executable
        """
        if self.gdbpath:
            return self.gdbpath

        self.gdbpath = get_arm_gdb()
        return self.gdbpath

    @property
    def default_gdb_commands(self):
        """Return a string about gdb init template.
        """
        return ("target remote :{gdbport}\n"
                "load\n"
                "continue &\n"
                "q\n")

    def reset(self):
        """Used to reset target CPU.
        """
        pass

    def erase(self, **kwargs):
        """Used to erase flash.
        """
        pass

    def flash(self, filepath, **kwargs):
        """Binary image programming.
            .bin
            .hex
        """
        pass

    def get_gdbserver(self, **kwargs):
        """Return a string about the command line of gdbserver
        """
        raise NotImplementedError(f"{self.name}: not support")

    def read32(self, addr):
        """read a 32-bit word"""
        raise NotImplementedError(f"{self.name}: not support")

    def write32(self, addr, value):
        """write a 32-bit word"""
        raise NotImplementedError(f"{self.name}: not support")

    def start_gdbserver(self, background=True, gdbserver_cmdline=None, **kwargs):
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

        port = kwargs.get("port")

        if self._board:
            port = self._board.gdbport

        # On Linux, port cannot be released even if current process
        # is terminted, to avoid exception "Address already in use";
        # Find and use free port from socket.
        if not port or os.name != "nt":
            port = find_free_port()

        if self._board:
            self._board.gdbport = port

        kwargs["port"] = port
        gdbserver_cmd = gdbserver_cmdline or self.get_gdbserver(**kwargs)
        logging.info("gdbserver: %s", gdbserver_cmd)

        if os.name == "nt":
            gdbserver_cmd = gdbserver_cmd.replace("\\", "\\\\")

        gdbserver_cmd = shlex.split(gdbserver_cmd)

        if not background:
            return subprocess.call(gdbserver_cmd, shell=True)

        self._gdbserver = subprocess.Popen(gdbserver_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            shell=False, creationflags=CREATE_NEW_PROCESS_GROUP,
            universal_newlines=True
        )

        console = list()

        def get_output(self):
            return "".join(self.console)

        setattr(self._gdbserver, "console", console)
        setattr(self._gdbserver, "get_output", MethodType(get_output, self._gdbserver))

        def stdout_reader(process):
            for line in iter(process.stdout.readline, b''):
                if process.poll() is not None:
                    break
                if line:
                    self._gdbserver.console.append(line)

        time.sleep(0.3)
        # To resolve large output from subprocess PIPE,
        # use a background thread to continues read data from stdout.
        reader_thread = threading.Thread(target=stdout_reader, args=(self._gdbserver, ))
        reader_thread.start()

        if self._gdbserver.poll() is not None:
            logging.error('gdb server start failed:\n %s', self._gdbserver.returncode)

        return self._gdbserver

    def list_connected_devices(self):
        pass

    def gdb_program(self, filename, gdbserver_cmdline=None, gdb_commands=None,
            board=None, timeout=200, **kwargs):
        """Flash image/binary with gdb & gdbserver.

        Steps:
            1> Start gdbserver at port: board.gdbport
            2> Render gdbinit_template
            3> Start gdb.exe:
                gdb.exe -x <gdb.init> -se <binary.file>

        Arguments:
            filename - {str}: path to image file.
            gdbserver_cmdline - {str}: gdb server command line, used for starting gdb server.
            gdb_commands - {str}: gdb init commands to control gdb behaviour.
            timeout - {int}: set timeout for gdb & gdb server process. default 200 seconds.

        Returns:
            tuple --- (returncode, console-output)
        """
        timer = None
        try:
            session, timer, server_output = self._start_debug_session(filename,
                gdbserver_cmdline, gdb_commands, board, timeout, **kwargs)

            if not session:
                return 1, server_output

            # gdb client disconnect the connection,
            # and gdbsever will automaticlly close
            session.close()
            session.gdb_server_proc.wait()

        except GDBServerStartupError:
            return 1, ""

        finally:
            # Stop timeout timer when communicate call returns.
            if timeout is not None and timer:
                timer.cancel()

        logging.debug("gdbserver exit code: %s", session.gdb_server_proc.returncode)

        # get gdb console output
        output = server_output
        output += session.console_output
        retcode = session.gdb_server_proc.returncode
        return retcode, output

    def _start_debug_session(self, filename=None, gdbserver_cmdline=None, gdb_commands=None,
            board=None, timeout=None, **kwargs):
        """
        Start a gdb session.
        Return a attached gdb session object.
        """

        if board is None:
            board = self._board

        if not self.gdbexe:
            raise ValueError("Invalid gdb executable")

        if board is None:
            raise ValueError('no board is associated with debugger!')

        timer = None
        gdb_errorcode = 0

        start = time.time()

        gdbserver_proc = self.start_gdbserver(gdbserver_cmdline=gdbserver_cmdline, **kwargs)

        if os.name == "nt" and not validate_port_is_ready(gdbserver_proc, board.gdbport):
            if gdbserver_proc.poll() is None:
                gdbserver_proc.kill()

            gdbserver_proc.wait()
            logging.error(f"gdbserver cannot start, console output: \n {gdbserver_proc.get_output()}")
            raise GDBServerStartupError("gdbserver start failure")

        logging.debug(f"gdbserver is ready, pid: {gdbserver_proc.pid}, port: {board.gdbport}.")

        gdb_cmds_template = gdb_commands or board.gdb_commands or self.default_gdb_commands
        gdbcommands = render_gdbinit(gdb_cmds_template, board)

        # start gdb client
        gdb_cmd_line = GDBSession.get_gdb_commands(self.gdbexe, filename)
        logging.debug("start gdb client to connect to server.")
        session = GDBSession.start(gdb_cmd_line)
        session.gdb_server_proc = gdbserver_proc

        # Use a timer to stop the subprocess if the timeout is exceeded.
        if timeout is not None:
            session.timeout = timeout
            ps_list = [gdbserver_proc, session]
            timer = threading.Timer(timeout, timeout_exceeded, (ps_list, timeout))
            timer.start()

        # convert string commands to a list
        _gdb_actions = [line.strip() for line in gdbcommands.split("\n") if line.strip()]

        for act in _gdb_actions:
            # call registerd callback function before_load command
            if act.startswith("load"):
                self._call_registered_callback("before_load")
            try:
                c = session.run_cmd(act)
                if "No connection could be made" in c or "Target disconnected" in c\
                    or "Connection timed out" in c or '"monitor" command not supported by this target' in c \
                    or "Error finishing flash operation" in c or "Load failed" in c:
                    gdb_errorcode = 1
                    logging.error(c)
                    break
            except:
                logging.exception('gdb cmd error, CMD: %s', act)
                gdb_errorcode = 1

        if gdb_errorcode == 1:
            session.close()
            session = None
            try:
                gdbserver_proc.terminate()
            except:
                pass

        print("time used: %.2f" % (time.time() - start))
        return session, timer, gdbserver_proc.get_output()

    def start_gdb_debug_session(self, filename=None, gdbserver_cmdline=None,
        gdb_commands=None, board=None, **kwargs):
        """Start gdbserver and then start gdb client to connect.

        Arguments:
            filename: {str} -- executable file path
            gdbserver_cmdline: {str} -- custom gdbserver startup command line
            gdb_commands: {str} -- custom gdb commands

        Returns:
            Return an active GDBSession object.
        """
        session, _, _ = self._start_debug_session(
            filename, gdbserver_cmdline, gdb_commands,
            board, timeout=None, **kwargs)

        return session

    def register(self, name):
        """Aecorator to register callback to debugger instance.

        Supported callbacks:
            - before_load
        """
        def func_wrapper(func, *args, **kwagrs):
            self._callback_map[name] = (func, args, kwagrs)
            return func
        return func_wrapper

    def register_callback(self, stage, func, *args, **kwagrs):
        assert stage in DebuggerBase.STAGES
        self._callback_map[stage] = (func, args, kwagrs)

    def remove_callback(self, stage):
        if stage in self._callback_map:
            del self._callback_map[stage]

    def _call_registered_callback(self, name=None):
        value = self._callback_map.get(name)
        if isinstance(value, tuple):
            func, args, kwargs = value
            if func:
                return func(*args, **kwargs)
        return None


def _generate_gdb_commands_for_sp_pc(**kwargs):
    """Generate GDB commands for SP and PC."""

    commands = [f"set ${register}={value}" for register, value in kwargs.items() if value]
    return "\n".join(commands)


def timeout_exceeded(procs, timeout):
    """
    Subprocess tiemout exceeded handler.
    """
    # process.kill() just killed the parent process, and cannot kill the child process
    # that caused the popen process in running state.
    # force to use windows command to kill that the process!
    for process in procs:
        proc = process
        if isinstance(process, PopenSpawn):
            proc = process.proc

        logging.warning('pid: %s exceeded timeout[Timeout=%d(s)], force killed', proc.pid, timeout)
        if os.name == "nt":
            os.system(f"TASKKILL /F /PID {proc.pid} /T")
        else:
            process.kill()


def render_gdbinit(template, board):
    """
    Render gdbinit template with board object.
    """
    dicta = board.__dict__
    dicta["PC_SP"] = _generate_gdb_commands_for_sp_pc(sp=board.sp, pc=board.pc)
    # dicta["file"] = executable
    return template.format(**dicta)


def _check_port_in_use(addr, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((addr, port))
        except (OSError, socket.error) as err:
            if isinstance(err, OSError) or err.errno == errno.EADDRINUSE:
                return True

    return False


def validate_port_is_ready(server_process, port, timeout=30):
    """Validate the port is open on localhost"""

    port = int(port)
    start_time = time.time()

    while time.time() - start_time <= timeout:
        print(" Wait for gdb server ready.")

        if server_process.poll() != None:
            return False

        time.sleep(0.4)

        if _check_port_in_use("127.0.0.1", port) or _check_port_in_use("", port):
            return True

    if server_process.poll() is None:
        return True

    return False
