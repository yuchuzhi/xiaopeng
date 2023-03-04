

import os
import re
import glob
import platform
from packaging import version
from mcutool.compilers import IDEBase


def get_gcc_arm_none_eabi_version(arm_gcc):
    version_content = os.popen(f"\"{arm_gcc}\" --version").read()
    ret = re.search(r"\d\.\d\.\d", version_content)
    if ret is not None:
        ide_version = ret.group()
    return ide_version


class Compiler(IDEBase):
    """GNU ARM GCC compiler.

    CMake and ARM-GCC build explanation:
        - Generate Makefile:
        >>> cmake -DCMAKE_TOOLCHAIN_FILE={path}/armgcc.cmake -G "{MinGW|Unix} Makefiles" -DCMAKE_BUILD_TYPE=debug

        - Start build with make tool or mingw32-make:
        >>> make -C "<path-to-makefile-directory>" -j4
        >>> mingw32-make -C "<path-to-makefile-directory>" -j4

        - Compile. Armgcc compiler will be called to compile in makefile.

    CMake is a cross-platform build system generator. Projects specify their build
    process with platform-independent CMake listfiles included in each directory
    of a source tree with the name CMakeLists.txt. Users build a project by using
    CMake to generate a build system for a native tool on their platform.

    GNU Make is a tool which controls the generation of executables and other non-source
    files of a program from the program's source files. Make gets its knowledge of how to
    build your program from a file called the makefile, which lists each of the non-source
    files and how to compute it from other files. When you write a program, you should
    write a makefile for it, so that it is possible to use Make to build and install the
    program.

    """

    OSLIST = ["Windows", "Linux", "Darwin"]

    Search_locations = {
        "Windows": [
            "C:\\Program Files (x86)\\GNU Arm Embedded Toolchain",
            "C:\\Program Files (x86)\\GNU Tools ARM Embedded"
            ],
        "Linux": ["/usr/local", '/opt/armgcc', os.path.expanduser("~")],
        "Darwin": ["/usr/local", '/opt/armgcc', os.path.expanduser("~")],
    }

    @property
    def is_ready(self):
        return True

    @classmethod
    def get_latest(cls):
        osname = platform.system()
        versions_dict = {}

        # find directly from current env
        # gcc = shutil.which("arm-none-eabi-gcc")
        # if gcc and gcc.startswith("/usr"):
        #     version = get_gcc_arm_none_eabi_version(gcc)
        #     versions_dict[str(version)] = gcc.split("/bin")[0]

        search_paths = cls.Search_locations.get(platform.system())

        for root_path in search_paths:
            if not os.path.exists(root_path):
                continue

            # build the glob serach pattern
            if osname == "Windows":
                gcc_exes = glob.glob(root_path + "/*/bin/arm-none-eabi-gcc.exe")
            else:
                gcc_exes = glob.glob(root_path + "/gcc-arm-none-eabi*/bin/arm-none-eabi-gcc")

            for gcc_exe in gcc_exes:
                instance_path = os.path.abspath(os.path.join(gcc_exe, "../../"))

                if osname == "Windows":
                    ide_version = os.path.basename(instance_path).replace(" ", "-").strip()
                else:
                    ide_version = os.path.basename(instance_path).replace("gcc-arm-none-eabi-", "")

                # Try to get version from: arm-none-eabi-gcc --version
                if not ide_version:
                    ide_version = get_gcc_arm_none_eabi_version(gcc_exes)

                if ide_version:
                    versions_dict[str(ide_version)] = instance_path

        version_pool = [(path, ide_version) for ide_version, path in versions_dict.items()]
        versions = [(ver[0], version.parse(str(ver[1]))) for ver in version_pool]
        versions.sort(key=lambda x: x[1])

        return versions[-1]

