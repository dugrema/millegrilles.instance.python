import asyncio
import logging
import psutil
import time
from typing import Any, Dict, List, Optional, Union, TypedDict

class PartitionUsageItem(TypedDict):
    mountpoint: str
    free: int
    used: int
    total: int

class MemoryInfo(TypedDict):
    total: int
    available: int
    percent: float
    used: int
    free: int

class SwapInfo(TypedDict):
    total: int
    used: int
    free: int
    percent: float

class NetworkInfo(TypedDict):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int

class DiskIOInfo(TypedDict):
    read_bytes: int
    write_bytes: int
    read_count: int
    write_count: int
    read_time: float
    write_time: float

class SystemState(TypedDict, total=False):
    disk: List[PartitionUsageItem]
    load_average: List[float]
    memory: MemoryInfo
    swap: SwapInfo
    cpu_count: int
    cpu_usage_percent: float
    network: NetworkInfo
    disk_io: DiskIOInfo
    uptime_seconds: float
    system_temperature: Dict[str, Any]
    system_fans: Dict[str, Any]
    system_battery: Any
    apc: Dict[str, Any]


class SystemStatus:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__apc_info: Union[Dict[str, Any], bool, None] = None
        self.__current_state: SystemState = {}
        psutil.cpu_percent(interval=None)

    @property
    def current_state(self) -> SystemState:
        return self.__current_state

    def read_system_status(self) -> None:
        info_systeme: SystemState = {}
        info_systeme['disk'] = self.partition_usage()
        info_systeme['load_average'] = [round(l * 100) / 100 for l in list(psutil.getloadavg())]

        # Memory
        mem = psutil.virtual_memory()
        info_systeme['memory'] = {
            'total': mem.total,
            'available': mem.available,
            'percent': mem.percent,
            'used': mem.used,
            'free': mem.free
        }
        swap = psutil.swap_memory()
        info_systeme['swap'] = {
            'total': swap.total,
            'used': swap.used,
            'free': swap.free,
            'percent': swap.percent
        }

        # CPU
        info_systeme['cpu_count'] = psutil.cpu_count()
        info_systeme['cpu_usage_percent'] = psutil.cpu_percent()

        # Network
        net = psutil.net_io_counters()
        info_systeme['network'] = {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
            'errin': net.errin,
            'errout': net.errout,
            'dropin': net.dropin,
            'dropout': net.dropout
        }

        # Disk IO
        disk_io = psutil.disk_io_counters()
        if disk_io:
            info_systeme['disk_io'] = {
                'read_bytes': disk_io.read_bytes,
                'write_bytes': disk_io.write_bytes,
                'read_count': disk_io.read_count,
                'write_count': disk_io.write_count,
                'read_time': disk_io.read_time,
                'write_time': disk_io.write_time,
            }

        # Uptime
        info_systeme['uptime_seconds'] = time.time() - psutil.boot_time()

        # Sensors
        try:
            system_temperature = psutil.sensors_temperatures()
            if system_temperature and len(system_temperature) > 0:
                info_systeme['system_temperature'] = system_temperature
        except AttributeError:
            pass

        try:
            system_fans = psutil.sensors_fans()
            if system_fans and len(system_fans) > 0:
                info_systeme['system_fans'] = system_fans
        except AttributeError:
            pass

        try:
            system_battery = psutil.sensors_battery()
            if system_battery:
                info_systeme['system_battery'] = system_battery
        except AttributeError:
            pass

        if self.__apc_info and self.__apc_info is not False:
            info_systeme['apc'] = self.__apc_info

        self.__current_state = info_systeme

    async def apc_info(self) -> bool:
        """
        Charge l'information du UPS de type APC.
        L'option se desactive automatiquement au premier echec
        """
        from apcaccess import status as apc

        if self.__apc_info is False:
            return True  # Make the thread stop
        try:
            resultat = await asyncio.to_thread(apc.get, timeout=10)
            parsed = apc.parse(resultat, strip_units=True)
            self.__apc_info = parsed
        except Exception as e:
            self.__logger.warning("UPS de type APC non accessible, desactiver (erreur %s)" % e)
            self.__apc_info = False

            return True  # Make the thread stop

        return False  # Keep going

    def partition_usage(self) -> List[PartitionUsageItem]:
        partitions = psutil.disk_partitions()
        reponse: List[PartitionUsageItem] = list()
        for p in partitions:
            if 'rw' in p.opts and '/boot' not in p.mountpoint:
                usage = psutil.disk_usage(p.mountpoint)
                reponse.append(
                    {'mountpoint': p.mountpoint, 'free': usage.free, 'used': usage.used, 'total': usage.total})
        return reponse
