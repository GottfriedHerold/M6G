from __future__ import annotations
from django.conf import settings
from typing import TYPE_CHECKING, Literal

from logging import Logger

_Levels = Literal['debug', 'info', 'error', 'critical', 'warning', 'exception', None]


def conditional_log(logger: Logger, *args, normal_level: _Levels = 'critical', test_level: _Levels = 'info', **kwargs):
    if settings.TESTING_MODE:
        if test_level:
            getattr(logger, test_level)(*args, **kwargs)
    else:
        if normal_level:
            getattr(logger, normal_level)(*args, **kwargs)

