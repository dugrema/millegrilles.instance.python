import logging

from typing import Optional


class EtatCertissuer:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__csr: Optional[str] = None

    def get_csr(self):
        if self.__csr is None:
            pass

        return self.__csr