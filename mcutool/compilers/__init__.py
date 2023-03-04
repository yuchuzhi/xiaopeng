
import importlib
from mcutool.compilers.idebase import IDEBase
from mcutool.compilers.result import Result, BuildResult
from mcutool.exceptions import (ProjectNotFound, ProjectParserError)


__all__ = ["compilerfactory", "factory", "IDEBase", "Result", 
    "BuildResult", "ProjectNotFound", "ProjectParserError",
    "SUPPORTED_TOOLCHAINS"
]

# Don't change the oder
# codewarrior must be front than mcux
SUPPORTED_TOOLCHAINS = [
    'mcux'
]

def compilerfactory(name):
    """Return specific Compiler class.

    Example 1, basic:
        >>> Compiler = compilerfactory('iar')
        <mcutool.compilers.iar.Compiler object at 0x1023203>

    Example 2, get the latest instance by scanning your system:
        >>> app = compilerfactory('iar').get_latest()
        >>> print app.path
        C:/program files(x86)/IAR Systems/IAR Workbench/
        >>> print app.version
        8.22.2

    Example 3, create app instance directly:
        >>> Compiler = compilerfactory('iar')
        >>> app = Compiler('/path/to/ide', version='1.0.0')
        >>> print app.path
        C:/program files(x86)/IAR Systems/IAR Workbench/
        >>> print app.version
        8.22.2

    Example 4, load and parse the project:
        >>> project = compilerfactory('iar').Project('/path/to/project')
        >>> print project.name
        hello_world
        >>> print project.targets
        ['debug', 'release']

    """
    try:
        idemodule = importlib.import_module(f"mcutool.compilers.{name}")
        appcls = getattr(idemodule, "Compiler")
        projcls = getattr(idemodule, "Project")
        appcls.Project = projcls
    except ImportError as err:
        raise ValueError(f"not supported {name}") from err

    return appcls


def factory(name):
    """Return specific app module"""
    try:
        idemodule = importlib.import_module(f"mcutool.compilers.{name}")
    except ImportError:
        pass
    return idemodule
