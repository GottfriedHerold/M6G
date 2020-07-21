from __future__ import annotations
from typing import Literal
from logging import Logger

from django.conf import settings


_Levels = Literal['debug', 'info', 'error', 'critical', 'warning', 'exception', None]


def conditional_log(logger: Logger, *args, normal_level: _Levels = 'critical', test_level: _Levels = 'info', **kwargs):
    if settings.TESTING_MODE:
        if test_level:
            getattr(logger, test_level)(*args, **kwargs)
    else:  # pragma: no cover
        if normal_level:
            getattr(logger, normal_level)(*args, **kwargs)
