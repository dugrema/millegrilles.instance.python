import asyncio
import logging
import psutil

from asyncio import TaskGroup

from millegrilles_instance.Context import InstanceContext


class SystemStatus:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__apc_info = None
        self.__current_state = dict()

    async def run(self):
        self.__logger.debug("SystemStatus thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__polling_thread())
                group.create_task(self.__apc_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("SystemStatus thread done")

    @property
    def current_state(self):
        return self.__current_state

    async def __polling_thread(self):
        while self.__context.stopping is False:
            # Charger information UPS APC (si disponible)
            await asyncio.to_thread(self.__read_system_status)
            await self.__context.wait(20)

    async def __apc_thread(self):
        while self.__context.stopping is False:
            stop = await self.apc_info()
            if stop:
                return  # Stopping thread
            await self.__context.wait(15)

    def __read_system_status(self):
        info_systeme = dict()
        info_systeme['disk'] = self.partition_usage()
        info_systeme['load_average'] = [round(l * 100) / 100 for l in list(psutil.getloadavg())]

        system_temperature = psutil.sensors_temperatures()
        if system_temperature and len(system_temperature) > 0:
            info_systeme['system_temperature'] = system_temperature

        system_fans = psutil.sensors_fans()
        if system_fans and len(system_fans) > 0:
            info_systeme['system_fans'] = system_fans

        system_battery = psutil.sensors_battery()
        if system_battery:
            info_systeme['system_battery'] = system_battery

        if self.__apc_info:
            info_systeme['apc'] = self.__apc_info

        self.__current_state = info_systeme

        # Inject into context
        self.__context.current_system_state = self.__current_state

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
