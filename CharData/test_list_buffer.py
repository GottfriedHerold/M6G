from .ListBuffer import LazyIterList

def counter(start: int, end: int):  # like range, but with control over internals
    assert start <= end
    x = start
    while x < end:
        yield x
        x += 1


def test_list_buffer():
    x = counter(0, 6)
    assert next(x) == 0
    buf1 = LazyIterList(x)
    assert next(buf1) == 1
    assert next(buf1) == 2
    buf2 = iter(buf1)
    assert next(buf1) == 3
    assert next(buf1) == 4
    assert next(buf2) == 3
    assert next(buf2) == 4
    assert next(x) == 5

    x = iter(counter(0, 2))

    c1 = c2 = 0
    buf1 = LazyIterList(x)
    buf2 = LazyIterList(buf1)
    for t in buf1:
        c1 += 1
    for t in buf2:
        c2 += 1
    assert c1 == 2
    assert c2 == 2