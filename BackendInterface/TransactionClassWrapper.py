"""
This file defines a utility wrapper that allows DBCharVersion to be used as a context manager that starts a transaction
with DBCharVersion.start_transaction(...) as char_version:
    ...
"""

#  Move class to DBCharVersion?
from __future__ import annotations
from typing import Type, TYPE_CHECKING, Callable, Optional
import sys

from django.db import transaction

if TYPE_CHECKING:
    from CharData import BaseCharVersion


class TransactionContextManagerWrapper:
    """
    This class allows DBCharVersion to be used as a context manager that starts a transaction.

    A TransactionContextManagerWrapper instance takes constructor arguments for a class _cls (Subtype of BaseCharVersion)
    and delays its creation until TransactionContextManagerWrapper.__enter__(), where it first opens a transaction
    and then returns the _cls instance as the context manager.

    In an expression
    with DBCharVersion.start_transaction(constructor args) as char_version,
    DBCharVersion.start_transaction actually creates an object of type TransactionContextManagerWrapper (this class)
    that just stores the constructor args. TransactionContextManagerWrapper.__enter__ then creates and returns the
    actual DBCharVersion that is stored in char_version.
    The point here is that using a different class on which __enter__ is defined (and which does not return self)
    ensures that with DBCharVersion(...) as char_version does *not* work, preventing mistakes.
    Also, defining __enter__ on DBCharVersion itself runs into the problem that we need to ensure that DB accesses
    during DBCharVersion.__init__ are part of the same transaction as the uses of the resulting char_version.
    """
    _cls: Type[BaseCharVersion]  # Intented to be DBCharVersion

    def __init__(self, *args, _cls: Type[BaseCharVersion], _at_exit: Optional[Callable[[BaseCharVersion], None]] = None, **kwargs):
        """
        Takes constructor arguments *args and **kwargs for class _cls and delays instance creation until __enter__
        If given, _at_exit is called on the _cls instance during __exit__ if no exception occurred.
        (names contain _ to not clash with *args, **kwargs)
        """
        self._cls = _cls
        self._args = args
        self._kwargs = kwargs
        self._at_exit = _at_exit

    # Note: with ... as ... is purely scope-based rather than bound to the lifetime of an object. (RAII in Python sucks)
    # We "fake" the behaviour of an with transaction.atomic() block surrounding _cls(*args, **kwargs) as good as
    # possible.
    def __enter__(self):
        self._atomic_manager = transaction.atomic()
        self._enter = self._atomic_manager.__enter__
        self._exit = self._atomic_manager.__exit__
        self._transaction = self._enter(self._atomic_manager)
        try:
            self._char_version = self._cls(*self._args, **self._kwargs)
            return self._char_version
        except Exception:
            if self._exit(self._atomic_manager, *sys.exc_info()):
                #  The "correct" action would be to skip the body of the calling with... block and suppress the
                #  exception.
                #  This is not possible in Python 3.8 (cf. the rejected PEP 377; contextlib has the exactly some problem.)
                raise RuntimeError("Exception occurred during setup of TransactionContextManager and was unexpectedly caught.")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._at_exit and (exc_type is None):
            try:
                self._at_exit(self._char_version)
            except Exception:
                exc_type, exc_val, exc_tb = sys.exc_info()
                if self._exit(exc_type, exc_val, exc_tb):
                    return True
                raise
        return self._exit(exc_type, exc_val, exc_tb)
