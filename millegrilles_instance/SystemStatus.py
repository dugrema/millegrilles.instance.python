import asyncio
import logging
import psutil
import time


class SystemStatus:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__apc_info = None
        self.__current_state = dict()
        psutil.cpu_percent(interval=None)

    @property
    def current_state(self):
        return self.__current_state

    def read_system_status(self):
        info_systeme = dict()
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

        if self.__apc_info:
            info_systeme['apc'] = self.__apc_info

        self.__current_state = info_systeme

    async def apc_info(self):
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

    def partition_usage(self):
        partitions = psutil.disk_partitions()
        reponse = list()
        for p in partitions:
            if 'rw' in p.opts and '/boot' not in p.mountpoint:
                usage = psutil.disk_usage(p.mountpoint)
                reponse.append(
                    {'mountpoint': p.mountpoint, 'free': usage.free, 'used': usage.used, 'total': usage.total})
        return reponse
