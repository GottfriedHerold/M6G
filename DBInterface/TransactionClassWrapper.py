from __future__ import annotations
from typing import Type, TYPE_CHECKING, Callable, Optional
import sys

from django.db import transaction

if TYPE_CHECKING:
    from CharData import BaseCharVersion

class TransactionContextManagerWrapper:
    _cls: Type[BaseCharVersion]

    def __init__(self, *args, _cls: Type[BaseCharVersion], _at_exit: Optional[Callable[[BaseCharVersion], None]] = None, **kwargs):
        self._cls = _cls
        self._args = args
        self._kwargs = kwargs
        self._at_exit = _at_exit

    def __enter__(self):
        self._atomic_manager = transaction.atomic()
        self._enter = self._atomic_manager.__enter__
        self._exit = self._atomic_manager.__exit__
        self._transaction = self._enter(self._atomic_manager)
        self._exception_hit_and_handled = False
        try:
            self._char_version = self._cls(*self._args, **self._kwargs)
            return self._char_version
        except Exception:
            if self._exit(self._atomic_manager, *sys.exc_info()):
                #  The "correct" action would be to skip the body of the calling with... block.
                #  This is not possible in Python 3.8 (cf. the rejected PEP 377; contextlib has the exactly some problem.)
                raise RuntimeError("Exception occurred during setup of TransactionContextManager and was unexpectedly caught.")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._at_exit and exc_type is None:
            try:
                self._at_exit(self._char_version)
            except Exception:
                exc_type, exc_val, exc_tb = sys.exc_info()
                if self._exit(exc_type, exc_val, exc_tb):
                    return True
                raise
        return self._exit(exc_type, exc_val, exc_tb)
