

import re
import sys
import time
import signal
import logging
import pexpect
from pexpect.popen_spawn import PopenSpawn
from io import StringIO



class GDBSessionInitFailed(Exception):
    pass


class GDBTimeout(Exception):
    pass


class GDBSession(object):
    """GDB debug session manager. This class will start a gdb process in backend.
    And provide methods allow user interact with gdb or manage the state.

    Example:
        >>> session = GDBSession.start("/path/to/gdb <image.elf> -x <gdb.init>")
        >>> response = session.run_cmd("load)
        >>> response = session.run_cmd("continue", timeout=10)
        >>> response = session.run_cmd("q")
        >>> session.close()
        >>> session.console_output
    """

    @classmethod
    def get_gdb_commands(cls, gdbexe, filepath=""):
        """Generate GDB startup commands according image file.

        Args:
            gdbexe (str): gdb executable
            filepath (str, optional): _description_. Defaults to "".

        Returns:
            str: commands to start gdb
        """

        if filepath.endswith(".elf"):
            return f"{gdbexe} {filepath} --silent"

        elif filepath:
            return f'{gdbexe} --exec {filepath} --silent'

        return f'{gdbexe} --silent'

    @staticmethod
    def start(cmdline):
        """A shortcut to start a gdb session.

        Arguments:
            cmdline {str} -- gdb startup command line.
        """

        session = GDBSession(cmdline)
        session.init()
        return session

    def __init__(self, executable):
        """GDB Session constructor.

        Create a gdb debug session. Pass the gdb executable path (also with arguments) as the
        startup command line.

        Arguments:
            executable {str} -- gdb startup command line or gdb executable.
        """

        self.executable = executable
        self._spawn = None
        self._logfile = None
        self._console = ''
        self.timeout = 60 * 5
        self._gdbsep = [re.compile(r"\(gdb\) "), re.compile("^>")]
        self.gdb_server_proc = None

        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            logging.warning("reconfigure encoding failed")

    def init(self):
        """Start GDB process in backend."""

        logging.info(self.executable)
        self._logfile = StringIO()
        self._spawn = PopenSpawn(
            self.executable,
            logfile=self._logfile,
            encoding='utf8',
            timeout=self.timeout,
            codec_errors="ignore"
        )
        self._spawn.logfile_read = sys.stdout
        try:
            self._spawn.expect(self._gdbsep)
        except Exception as err:
            raise GDBSessionInitFailed("gdb start failed")

    def run_cmd(self, cmd, wait=True, timeout=-1):
        """Run gdb command.

        Arguments:
            cmd {str} -- gdb command
            wait {boolean} -- block and wait for "continue"/"jump" finish.
            timeout {int} -- max timeout to wait the response,
                -1: use default timeout value, None: block and until match.

        Returns:
            {str} -- gdb response text
        """
        response = ''
        if timeout == -1:
            timeout = self.timeout

        if not self.is_alive:
            raise RuntimeError("gdb session is inactive, cannot send command.")

        try:
            logging.info("gdb=> %s", cmd)
            self._spawn.sendline(cmd)
            # popenSpawn cannot response if sent "end"
            # so we send a new line after the command
            # can make pexpect to get wanted response
            expect_str = self._gdbsep

            if cmd == "end":
                self._spawn.send("\n")
                self._spawn.expect(self._gdbsep, timeout=timeout)

            cmd = cmd.lower()

            if not wait:
                if cmd == "c" or cmd == "continue" or cmd.startswith("jump"):
                    expect_str = "Continuing"

            self._spawn.expect(expect_str, timeout=timeout)

        except pexpect.TIMEOUT:
            raise GDBTimeout('CMD: %s, timeout=%ss!' % (cmd, timeout))

        except pexpect.EOF:
            logging.debug("GDB EOF")

        if isinstance(self._spawn.before, str):
            response = self._spawn.before

        return response

    def run_cmds(self, cmds):
        """Run a list of commands."""

        for cmd in cmds:
            self.run_cmd(cmd)

    @property
    def is_alive(self):
        """GDB process is alive or not"""

        return self._spawn.proc.poll() == None

    @property
    def pid(self):
        """GDB process pid"""

        return self._spawn.proc.pid

    def kill(self):
        """Kill GDB process"""

        return self._spawn.proc.kill()

    @property
    def console_output(self):
        """Return all console output"""

        if self.is_alive:
            raise RuntimeError('the console output cannot access when session is alive!')
        return self._console

    def _handle_console_output(self):
        self._logfile.seek(0)
        self._console = self._logfile.read()
        self._logfile.close()

    def send_ctrl_c(self):
        """Send CTRL C event to gdb."""
        self._spawn.proc.send_signal(sig=signal.CTRL_C_EVENT)

    def close(self):
        """Close session and make sure process has exited."""

        if self.is_alive:
            try:
                # send q command to make sure gdb exit
                self._spawn.logfile = None
                self._spawn.sendline('q')
            except IOError:
                pass

            # wait 2 seconds to terminate the gdb process
            start_time = time.time()
            while self.is_alive:
                if time.time() - start_time > 2:
                    self.kill()
                    logging.warning("force terminate GDB (PID=%s)", self.pid)
                    break

            # wait for exit
            self._spawn.proc.wait()

        self._handle_console_output()
        logging.info("Debug session is closed!")

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, etype, evalue, tb):
        self.close()
