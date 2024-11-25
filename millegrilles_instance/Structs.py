import datetime

from typing import Optional

from millegrilles_instance.ModulesRequisInstance import RequiredModules


class ApplicationInstallationStatus:

    def __init__(self):
        self.required_modules: Optional[RequiredModules] = None
        self.required_app_names: list[str] = list()
        self.apps: dict[str, dict] = dict()
        self.last_update = datetime.datetime.now()

    def update(self, app_name: str, status: dict):
        try:
            self.apps[app_name].update(status)
        except KeyError:
            self.apps[app_name] = status
        self.last_update = datetime.datetime.now()

