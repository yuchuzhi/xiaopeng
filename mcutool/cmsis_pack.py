

import zipfile
import logging
from xml.etree import cElementTree as ET
from mcutool.exceptions import CmsisPackIssue


LOGGER = logging.getLogger(__name__)


class CMSISPack:
    """CMSIS Pack.

    Support to parse basic information from CMSIS Packs.
    """
    def __init__(self, filepath):
        self._name = None
        self._version = None
        self._vendor = None
        self._devices = None
        self._boardname = ""
        self.path = filepath
        self._pack_type = None
        self.pack_file = zipfile.ZipFile(self.path, mode='r')
        self.parse_pdsc(self.pack_file)

    def parse_pdsc(self, packfile):
        files = packfile.namelist()
        pdsc = None
        for item in files:
            if item.endswith(".pdsc"):
                pdsc = item
                break

        if pdsc is None:
            raise CmsisPackIssue("fatal error: could not found .pdsc file in pack!")

        self.xmltree = ET.fromstring(packfile.read(pdsc))
        self._name = self.xmltree.find("name").text
        self._vendor = self.xmltree.find("vendor").text
        self._version = self.xmltree.find("releases/release").attrib["version"]
        self._pack_type = "DFP" if "DFP" in self._name.upper() else "BSP"
        if self._pack_type == 'DFP':
            self._dfp()
        else:
            self._bsp()

    def _dfp(self):
        device_xpath = 'devices/family/device'
        linker_xpath = "components/component/files/file[@category='linkerScript']"

        # Device Definition Reference:
        # https://www.keil.com/pack/doc/CMSIS/Pack/html/pdsc_family_pg.html#element_memory

        devices = dict()
        for device_node in self.xmltree.findall(device_xpath):
            device_name = device_node.attrib["Dname"]
            device = {
                "name": device_name,
                "memory": list(),
                "algorithm": list(),
                "linker": list(),
                "partnumbers": list()
            }

            for mem_node in device_node.findall("memory"):
                device["memory"].append(mem_node.attrib)

            for algo_node in device_node.findall("algorithm"):
                algoinfo = algo_node.attrib
                device["algorithm"].append(algoinfo)

                # RAMstart & RAMsize: If not specified,
                # require a RAM memory with default=1 attribute.
                if "RAMstart" not in algoinfo:
                    algoinfo["RAMstart_from_memory"] = "1"
                    for mem in device["memory"]:
                        if mem.get("default") == "1" and mem["access"] != "rx":
                            algoinfo["RAMstart"] = mem['start']
                            algoinfo["RAMsize"] = mem['size']
                            break

            for var_node in device_node.findall("variant"):
                device["partnumbers"].append(var_node.attrib["Dvariant"])

            for linker_node in self.xmltree.findall(linker_xpath):
                device["linker"].append(linker_node.attrib)

            devices[device_name] = device

        self._devices = devices

    def _bsp(self):
        components = "components/component[@Cclass='Board Support']"
        node = self.xmltree.find(components)
        if node:
            self._boardname = node.attrib['Cvariant']

    @property
    def name(self):
        return self._name

    @property
    def vendor(self):
        return self._vendor

    @property
    def is_dfp(self):
        return "DFP" in self.name

    @property
    def version(self):
        return self._version

    @property
    def devicelist(self):
        return self._devices.keys()

    @property
    def boardname(self):
        return self._boardname

    @property
    def partnumbers(self):
        parts = list()
        for _, deviceinfo in self._devices.items():
            parts.extend(deviceinfo["partnumbers"])
        return parts

    @property
    def requirements(self):
        reqs = list()
        for node in self.xmltree.findall("requirements/packages/package"):
            reqs.append(node.attrib)
        return reqs

    def has_partnumbers(self, name):
        for _, deviceinfo in self._devices.items():
            if name in deviceinfo["partnumbers"]:
                return True
        return False

    def get_device_info_by_name(self, name):
        if not self.is_dfp:
            return None

        for _, deviceinfo in self._devices.items():
            if name in deviceinfo["partnumbers"] or deviceinfo["name"] == name \
                or deviceinfo["name"] in name:
                return deviceinfo
        return None

    def validate_algorithm(self):
        if "DFP" not in self.name:
            return
        for _, deviceinfo in self._devices.items():
            if not deviceinfo["algorithm"]:
                raise CmsisPackIssue(f"no algorithm found: {self.path}")

            for info in deviceinfo["algorithm"]:
                name = info.get("name")
                if name not in self.pack_file.namelist():
                    raise CmsisPackIssue(f"Critical: Missing flash algorithm \"{name}\" in pack!")

    def validate_linker(self):
        if "DFP" not in self.name:
            return

        for _, deviceinfo in self._devices.items():
            if not deviceinfo["linker"]:
                raise CmsisPackIssue("no linker information found")

            for info in deviceinfo["linker"]:
                name = info.get("name")
                if name not in self.pack_file.namelist():
                    raise CmsisPackIssue(f"Critical: Missing linker script \"{name}\" in pack!")

    def extract(self, location):
        """Extract packs to specific location.

        Args:
            location (_type_): _description_
        """
        self.pack_file.extractall(location)

    def close(self):
        self.pack_file.close()
