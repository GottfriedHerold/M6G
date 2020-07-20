"""
Defines a DummyManager and tests that the corresponding functions get called.
"""
from __future__ import annotations
from DataSources import CharDataSourceBase, CharDataSourceDict
from CharVersionConfig import BaseCVManager, CreateManagerEnum, DataSourceDescription, CVConfig, ManagerInstruction
from typing import Iterable


class TestCVManager(BaseCVManager):
    num_data_sources: int
    log: list
    _persistent_data_source: CharDataSourceBase = CharDataSourceDict()

    def __init__(self, /, *args, cv_config: CVConfig, manager_instruction: ManagerInstruction, log: list, num_data_sources: int, **kwargs):
        super().__init__(*args, cv_config=cv_config, manager_instruction=manager_instruction, **kwargs)
        self.num_data_sources = num_data_sources
        self.log = log
        self._data_source_descriptions = []
        self._post_setup_was_called = False
        for i in range(num_data_sources):
            self._data_source_descriptions.append(DataSourceDescription(manager=self))

    def post_setup(self, /, create: CreateManagerEnum) -> None:
        assert self._post_setup_was_called is False
        self._post_setup_was_called = True
        assert isinstance(self.log, list)
        assert isinstance(self.num_data_sources, int)
        if create == CreateManagerEnum.no_create:
            self.log.append("manager initialized")
        elif create == CreateManagerEnum.create_config:
            self.log.append("manager created in due to config creation")
        elif create == CreateManagerEnum.destroy_config:
            self.log.append("manager destroyed due to config deletion")
        elif create == CreateManagerEnum.add_manager:
            self.log.append("manager added")

    @property
    def data_source_descriptions(self):
        return self._data_source_descriptions

    def delete_manager(self):
        self.log.append("manager removed")

    def _get_data_sources(self, /, description: DataSourceDescription) -> Iterable[CharDataSourceBase]:
        assert description in self._data_source_descriptions
        return [self._persistent_data_source]

    def validate_config(self, /):
        super().validate_config()
        self.log.append("validating")
