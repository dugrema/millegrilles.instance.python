import logging
import datetime

from typing import Optional


class TacheEntretien:

    def __init__(self, intervalle: datetime.timedelta, callback, get_producer=None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__intervalle = intervalle
        self.__intervalle_retry = datetime.timedelta(seconds=30)
        self.__callback = callback
        self.__dernier_entretien: Optional[datetime.datetime] = None
        self.__get_producer = get_producer
        self.__en_erreur = False

    def reset(self):
        """
        Force une execution a la prochaine occasion
        :return:
        """
        self.__dernier_entretien = None

    def set_intervalle(self, intervalle: datetime.timedelta):
        self.__intervalle = intervalle

    def set_intervalle_retry(self, intervalle: datetime.timedelta):
        self.__intervalle_retry = intervalle

    async def run(self):
        now = datetime.datetime.utcnow()
        if self.__dernier_entretien is None:
            pass
        elif self.__en_erreur and now - self.__intervalle_retry > self.__dernier_entretien:
            pass
        elif now - self.__intervalle > self.__dernier_entretien:
            pass
        else:
            return

        self.__dernier_entretien = now

        try:
            if self.__get_producer is not None:
                await self.__callback(self.__get_producer)
            else:
                await self.__callback()
            self.__en_erreur = False
        except:
            self.__logger.exception("Erreur execution tache entretien")
            self.__en_erreur = True
