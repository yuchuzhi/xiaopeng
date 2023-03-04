#

#

import importlib
from mcutool.debugger.general import DebuggerBase

__all__ = ["getdebugger"]


Supported_Debugger_Types = {
    "jlink": "jlink.JLINK",
    "pyocd": "pyocd.PYOCD"
}

def getdebugger(type, *args, **kwargs):
    """Return debugger instance."""

    if type not in Supported_Debugger_Types:
        return DebuggerBase('general_%s' % str(type), *args, **kwargs)

    if type == "iar":
        type = "ide"

    importlib.import_module(f"mcutool.debugger.{type}")
    return eval(Supported_Debugger_Types[type])(*args, **kwargs)
