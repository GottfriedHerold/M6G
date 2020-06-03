from typing import Iterable, Iterator
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

class _IterBuffer:
    base_iterable: Iterator
    values: list

    def __init__(self, it: Iterable):
        self.base_iterator = iter(it)
        self.values = []
        self.computed_vals = 0  # length of values
        self.max_len = -1

class LazyIterList:

    lazy_iter_buffer: _IterBuffer
    position: int

    def __init__(self, it):
        try:
            self.lazy_iter_buffer = it.lazy_iter_buffer
            self.position = it.position
        except AttributeError:
            self.lazy_iter_buffer = _IterBuffer(it)
            self.position = 0
        assert isinstance(self.lazy_iter_buffer, _IterBuffer)

    def __iter__(self):  # Note that this does not return itself, but rather a copy of itself.
        return LazyIterList(self)

    def __next__(self):
        buf = self.lazy_iter_buffer
        if self.position < buf.computed_vals:
            ret = buf.values[self.position]
            self.position += 1
            return ret
        elif self.position == buf.max_len:
            raise StopIteration
        else:
            assert self.position == buf.computed_vals
            try:
                ret = next(buf.base_iterator)
                buf.values.append(ret)
                buf.computed_vals += 1
                self.position += 1
                return ret
            except StopIteration:
                buf.max_len = self.position
                raise
