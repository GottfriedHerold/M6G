from . import CharVersion

# TODO
def no_test_lookup_order(empty3cv: CharVersion):
    l1 = list(empty3cv.lookup_candidates('abc'))
    assert l1 == [('abc', 0), ('abc', 1), ('abc', 2), ('_all', 0), ('_all', 1), ('_all', 2)]
    it2 = empty3cv.lookup_candidates('abc', restricted=True)
    assert not list(*it2)
    it3 = empty3cv.lookup_candidates('_all', indices=[1])
    l3 = list(it3)
    assert l3 == [('_all', 1)]
    l4 = list(empty3cv.lookup_candidates('a.__b__.c', indices=[1]))
    assert l4 == [('a.__b__.c', 1), ('a.__b__._all', 1)]
    ll = list(empty3cv.lookup_candidates('__a__.b.c', indices=[1]))
    assert ll == [('__a__.b.c', 1), ('__a__.b._all', 1), ('__a__.c', 1), ('__a__._all', 1)]
    ll = list(empty3cv.lookup_candidates('a.b.__c__', indices=[1]))
    assert ll == [('a.b.__c__', 1), ('a.__c__', 1), ('__c__', 1)]
    empty3cv.lists[0].set_from_string('a.b', '=1 + 5')
    empty3cv.lists[0].set_from_string('b', '=8')
    empty3cv.lists[2].set_from_string('_all', '"0')
    empty3cv.lists[0].set_from_string('c', "1")
    empty3cv.lists[1].set_from_string('b', '=9')
    it = empty3cv.find_lookup('a.b')
    ll = list(it)
    assert ll == [('a.b', 0), ('b', 0), ('b', 1), ('_all', 2)]
    ll = list(empty3cv.function_candidates('f'))
    assert ll == [('__fun__.f', 0), ('__fun__.f', 1), ('__fun__.f', 2), ('fun.f', 0), ('fun.f', 1), ('fun.f', 2)]
    ll = list(empty3cv.function_candidates('g', indices=[1]))
    assert ll == [('__fun__.g', 1), ('fun.g', 1)]

