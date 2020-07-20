"""
Defines LazyIterList, an iterator buffer that allows to copy read-once iterables.
Usage: for an iterable x, use
buf = LazyIterList(x). After this, x itself MUST NOT BE USED ANYMORE.
you can use next(buf) to iterate over x.
buf2 = iter(buf) or buf2 = LazyIterList(buf) creates a new independent iterator that starts from the position of buf.
(e.g. x = range(10).
it = iter(x)
next(it) >> 0
buf = LazyIterList(x)
next(buf) >> 1
next(buf) >> 2
buf2 = iter(buf)
next(buf) >> 3
next(buf> >> 4
next(buf2) >> 3
next(buf2) >> 4
In all this, the original x has next called on it only 5 times. )
"""
from __future__ import annotations
from typing import Iterable, Iterator, Union


class _IterBuffer:
    """
    encapsulates a buffer for iterable it. Notably, self.values is filled with the results from it on demand.
    The logic what constitutes demand is in LazyIterList
    """
    __slots__ = ['base_iterator', 'values', 'computed_values', 'max_len']

    def __init__(self, it: Iterable, /):
        self.base_iterator: Iterator = iter(it)  # iterator that is buffered by self
        self.values: list = []  # buffer
        self.computed_values: int = 0  # length of self.values
        self.max_len: int = -1  # if we hit StopIteration when trying to get values[i], we set max_len to i


class LazyIterList:
    """
    LazyIterList basically is an iterator/iterable (both) that basically iterates over the iterable it passed to it
    during construction (which gets wrapped in a _IterBuffer buffer object). It current position is position, which
    counts how many iteration LazyIterList is forward from it (its next output is it[pos] if it is list)
    """
    __slots__ = ['lazy_iter_buffer', 'position']
    lazy_iter_buffer: _IterBuffer
    position: int

    def __init__(self, it: Union[Iterable, LazyIterList], /):
        try:  # If it is a LazyIterList, we can reuse the existing _IterBuffer for efficiency, we just need to adjust the position.
            self.lazy_iter_buffer = it.lazy_iter_buffer
            self.position = it.position
        except AttributeError:  # general case for arbitrary iterable. We construct an _IterBuffer. Note that all future
            # accesses to it will be via some LazyIterList, which knows how to adjust the _IterBuffer.
            self.lazy_iter_buffer = _IterBuffer(it)
            self.position = 0
        assert isinstance(self.lazy_iter_buffer, _IterBuffer)

    def __iter__(self, /) -> LazyIterList:  # Note that this does not return itself, but rather a copy of itself. Returning self would
        # actually work due to how we use it, but copying is more consistent. Technically, we should have a separate
        # iterator / iterable class, but there is basically no need for that:
        # (The classes would have identical __dict__ and __init__, with the iterable having no __next__ and __iter__
        # returning a copy as an iterator, which in turn has an __iter__ returning itself and __next__ as below.)
        return LazyIterList(self)

    def __next__(self, /):
        buf = self.lazy_iter_buffer
        if self.position < buf.computed_values:
            ret = buf.values[self.position]
            self.position += 1
            return ret
        elif self.position == buf.max_len:
            raise StopIteration
        else:
            assert self.position == buf.computed_values
            try:
                ret = next(buf.base_iterator)
                buf.values.append(ret)
                buf.computed_values += 1
                self.position += 1
                return ret
            except StopIteration:
                buf.max_len = self.position
                raise
