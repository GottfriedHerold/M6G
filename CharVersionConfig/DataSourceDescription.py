from __future__ import annotations
from enum import IntEnum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .BaseCVManager import BaseCVManager
    from .types import UUID


class DataSourceDescription:
    """
    Class that describes a data source and that indicates how a user can interact with it in the CharVersion config
    settings. Should be subclassed. Note that this is purely for display purposes. The relevant state is held in the
    manager. In particular, we ask the manager to create a data source irrespective of whether active is set or not.
    It is the manager's job to not do anything if active == False.
    """
    movable: bool = True  # Can a user move the data source
    toggleable: bool = False  # Can a user toggle the data source from active / inactive
    active: bool = True  # Is the data source displayed as active? Note that this is purely for display purposes.
    description: str = ""  # Description that is displayed to the user
    # Note that DataSourceDescriptions are NOT (directly) serialized or contained in a configuration description.
    # They are just an interface for existing managers. Unfortunately, managers only expose the set of
    # valid data source description UUIDs after being set up, so we cannot read those off the python/JSON config.
    # TODO: We might want to change this, if it becomes too inconvenient.
    uuid: UUID

    # Position block of the data source. Data sources can only be moved within the blocks.
    class PositionType(IntEnum):
        start = auto()
        middle = auto()
        end = auto()
    position_type: PositionType = PositionType.middle

    # When adding a data source with priority != None, it will get its initial position within its block according to
    # priority, otherwise at the end.
    priority: Optional[int] = None
    # We refer to the manager by object identity rather than uuid for now.
    # Note that the description does not know the config it belongs to, so cannot evaluate uuids.
    # We might change that and make manager a property.
    # Note that DataSourceDescriptions are NOT (directly) serialized.
    manager: BaseCVManager

    def __init__(self, manager, *, description: str = None, active: bool = None, toggleable: bool = None, movable: bool = None, position_type: PositionType = None, priority: Optional[int] = Ellipsis, uuid: UUID):
        self.manager = manager
        self.uuid = uuid
        if description is not None:
            self.description = description
        if active is not None:
            self.active = active
        if toggleable is not None:
            self.toggleable = toggleable
        if movable is not None:
            self.movable = movable
        if position_type is not None:
            self.position_type = position_type
        if priority is not Ellipsis:
            self.priority = priority

    def make_and_append_to(self, target_list: list) -> None:
        self.manager.make_data_source(description=self, target_list=target_list)
