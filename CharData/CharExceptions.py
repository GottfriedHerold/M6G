"""
This module defines our custom exceptions and error placeholders
"""
from __future__ import annotations


class CharGenException(Exception):
    pass


class CGParseException(CharGenException):
    pass


class CGEvalException(CharGenException):
    pass


# TODO: Reconsider error handling when finishing CharGen Expression Language.
class DataError:
    """
    Used to indicate that a database entry is faulty.
    Reason is the reason, exception is possibly an exception that caused it (if present)
    """
    def __init__(self, reason: str = "", exception: Exception = None):
        self.exception = exception
        if (exception is not None) and not reason:
            self.reason = str(exception)
        else:
            self.reason = reason

    def __str__(self):
        return self.reason
