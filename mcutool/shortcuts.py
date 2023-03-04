#

#
import logging
import packaging.version
from pathlib import Path

from mcutool.exceptions import ToolchainError
from mcutool.compilers import compilerfactory, IDEBase, SUPPORTED_TOOLCHAINS



def build_project(tool_name, tool_path, project_path, tool_version=None,
    target=None, logfile=None, workspace=None, timeout=None):
    """A simple shortcut method to build C/C++ projects for embedded toolchains.

    Arguments:
        tool_name {string} -- toolchain name, like: iar, mdk, mcux, armgcc...
        tool_path {string} -- toolchain installation root directory
        project_path {string} -- project root directory or project path
        workspace {string} -- workspace directory for Eclipse based toolchains
        timeout {int} -- timeout for build
        tool_version {string} -- set toolchain version
        target {string} -- project configuration, debug/release
        logfile {string} -- log file path (default: {None})

    Raises:
        ToolchainError -- raise on unsupported toolchain
        IOError -- raise on toolchain is not ready

    Returns:
        mcutool.compilers.BuildResult -- build result
    """

    tool = compilerfactory(tool_name)
    if not tool:
        raise ToolchainError(f'unsupported tool: {tool_name}')

    toolchain = tool(tool_path, version=tool_version)
    if not toolchain.is_ready:
        raise IOError(f'tool is not ready to use, path: {tool_path}!')

    project = tool.Project.frompath(project_path)

    if target:
        target = project.map_target(target)
    else:
        target = project.targets[0]

    ret = toolchain.build_project(project, target, logfile, workspace=workspace, timeout=timeout)

    return ret


def list_toolchains(tool_name=None):
    """List all supported toolchains' version and installed path

    Args:
        tool_name: {str} name of specific toolchain.

    Returns:
        dict[list]

    """
    ides = dict()

    if tool_name:
        tool_names = [ tool_name ]
    else:
        tool_names = SUPPORTED_TOOLCHAINS

    for toolname in tool_names:
        try:
            tools = list()
            cls = compilerfactory(toolname)
            instances = cls.discover_installed()

            if not instances:
                continue

            instances.sort(key=lambda x: packaging.version.parse(str(x[1])), reverse=True)

            for (path, version) in instances:
                app_object = cls(path, str(version))

                if not app_object.is_ready:
                    logging.debug(f"{app_object}, \"{app_object.path}\" seems is damaged, ignore")
                    continue

                tools.append(app_object)

            ides[toolname] = tools
        except:
            logging.exception("failed to discover tool %s", toolname)

    return ides


def get_toolchain(tool_name, tool_version=None) -> IDEBase:
    """A shortcut method to get specific ide object.
    By default it return max version of toolchain.

    Arguments:
        tool_name {string} -- toolchain name, like: iar, mdk, mcux, armgcc...
        tool_version {string} -- toolchain version

    Returns:
        mcutool.compilers.{toolchain name}.Compiler -- if toolchin version is installed, or it will return None
    """

    tools = list_toolchains(tool_name).get(tool_name)
    if not tools:
        return

    if not tool_version:
        return tools[0]

    for tool in tools:
        if tool_version == tool.version:
            return tool

    return


def convert_elf(elffile, format, idename=None, ide=None) -> str:
    """A shortcut method to convert elf to specific format.

    Args:
        elffile {str} -- elf file
        format {str} -- format to convert, hex,bin,srec
        idename {str} -- specify ide to convert.
        ide {toolchain object}

    Returns:
        str -- output file
    """
    if idename is None:
        idename = "armgcc"

    if format == "hex":
        format = "ihex"

    extension = "hex" if format == "ihex" else format

    elfpath = Path(elffile)
    filename = elfpath.stem

    outfile = (elfpath.parent / f"{filename}.{extension}").as_posix()
    if not ide:
        ide = get_toolchain(idename)

    ide.transform_elf(format, elffile, out_file=outfile)

    return outfile
