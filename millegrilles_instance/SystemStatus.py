import asyncio
import logging
import socket
from asyncio import TaskGroup

import psutil
import time
from typing import Any, Dict, List, Optional, Union, TypedDict

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_messages.messages import Constantes as MilleGrillesConstantes


# Rust mapping:
# struct HostInfo {
#     hostname: String,
#     ip_addresses: Vec<String>,
#     ports: HashMap<String,u16>,
# }
class HostInfo(TypedDict):
    hostname: str
    ip_addresses: List[str]
    ports: dict[str, int]

# Rust mapping:
# struct PartitionUsageItem {
#     mountpoint: String,
#     free: u64,
#     used: u64,
#     total: u64,
# }
class PartitionUsageItem(TypedDict):
    mountpoint: str
    free: int
    used: int
    total: int

# Rust mapping:
# struct MemoryInfo {
#     total: u64,
#     available: u64,
#     percent: f64,
#     used: u64,
#     free: u64,
# }
class MemoryInfo(TypedDict):
    total: int
    available: int
    percent: float
    used: int
    free: int

# Rust mapping:
# struct SwapInfo {
#     total: u64,
#     used: u64,
#     free: u64,
#     percent: f64,
# }
class SwapInfo(TypedDict):
    total: int
    used: int
    free: int
    percent: float

# Rust mapping:
# struct NetworkInfo {
#     bytes_sent: u64,
#     bytes_recv: u64,
#     packets_sent: u64,
#     packets_recv: u64,
#     errin: u64,
#     errout: u64,
#     dropin: u64,
#     dropout: u64,
# }
class NetworkInfo(TypedDict):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int

# Rust mapping:
# struct DiskIOInfo {
#     read_bytes: u64,
#     write_bytes: u64,
#     read_count: u64,
#     write_count: u64,
#     read_time: f64,
#     write_time: f64,
# }
class DiskIOInfo(TypedDict):
    read_bytes: int
    write_bytes: int
    read_count: int
    write_count: int
    read_time: float
    write_time: float

# Rust mapping:
# struct SystemState {
#     host: Option<HostInfo>,
#     disk: Vec<PartitionUsageItem>,
#     load_average: Vec<f64>,
#     memory: MemoryInfo,
#     swap: SwapInfo,
#     cpu_count: i32,
#     cpu_usage_percent: f64,
#     network: NetworkInfo,
#     disk_io: Option<DiskIOInfo>,
#     uptime_seconds: f64,
#     system_temperature: Option<serde_json::Value>,
#     system_fans: Option<serde_json::Value>,
#     system_battery: Option<serde_json::Value>,
#     apc: Option<serde_json::Value>,
# }
class SystemState(TypedDict, total=False):
    host: HostInfo
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

    def __init__(self, configuration: ConfigurationInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__apc_info: Union[Dict[str, Any], bool, None] = None
        self.__current_state: SystemState = {}
        psutil.cpu_percent(interval=None)

    @property
    def current_state(self) -> SystemState:
        return self.__current_state

    def read_system_status(self) -> None:
        info_systeme: SystemState = {}
        
        # Host info
        hostname = socket.getfqdn()
        ip_addresses: List[str] = []

        # Get all non-loopback, non-docker IP addresses (IPv4 and IPv6)
        for interface, addrs in psutil.net_if_addrs().items():
            # Skip common container/virtual network interfaces
            if any(prefix in interface for prefix in ['docker', 'veth', 'br-', 'docker0', 'cali', 'flannel']):
                continue
            for addr in addrs:
                if addr.family in (socket.AF_INET, socket.AF_INET6):
                    # Skip loopback
                    if addr.address.startswith('127.') or addr.address == '::1':
                        continue
                    ip_addresses.append(addr.address)

        # Fallback if no suitable IP was found
        if not ip_addresses:
            try:
                ip_addresses.append(socket.gethostbyname(hostname))
            except Exception:
                pass

        ports = self.__configuration.instance_ports

        info_systeme['host'] = {
            'hostname': hostname,
            'ip_addresses': ip_addresses,
            'ports': ports
        }

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

        return info_systeme

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


class SystemStatusManager:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context

        self.__applications_changed = asyncio.Event()
        self.__stopping = asyncio.Event()

        self.__initial_refresh_done = asyncio.Event()

        self.__handler = SystemStatus(context.configuration)

        # Downgrade securite level 4.secure to 3.protege
        self.__securite: Optional[str] = None

    async def wait_initial_refresh_done(self):
        await self.__initial_refresh_done.wait()

    async def __stop_thread(self):
        await self.__context.wait()
        self.__stopping.set()

    async def setup(self):
        self.__securite = self.__context.securite if self.__context.securite != MilleGrillesConstantes.SECURITE_SECURE else MilleGrillesConstantes.SECURITE_PROTEGE

    async def run(self):
        self.__logger.debug("SystemStatusManager thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__emit_status_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("SystemStatusManager thread done")

    async def __emit_status_thread(self):
        """
        Thread that manages certificates that are about to expire. Refreshes the certificates and reloads the
        docker compose services.
        """
        await self.__context.wait(4)
        self.__logger.info("Starting emit status thread")
        while self.__context.stopping is False:
            try:
                await self.__emit_status()
            except Exception:
                self.__logger.exception("Error renewing certificates in manager")
            await self.__context.wait(10)
        self.__logger.info("Stopping emit status thread")

    async def __emit_status(self):
        try:
            producer = await asyncio.wait_for(self.__context.get_producer(), 1)
        except asyncio.TimeoutError:
            self.__logger.warning("Timeout waiting for producer to emit instance status")
            return

        system_state = await asyncio.to_thread(self.__handler.read_system_status)

        event_message = {
            'system_state': system_state,
        }

        await producer.event(
            event_message,
            'instance',
            'presenceInstanceV2',
            partition=self.__context.instance_id,
            exchange=self.__securite,
        )
