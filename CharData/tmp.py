def locate(self, key: str, *, startafter=None, restrict=False):
    # Check at call site. TODO: Verify this! (Otherwise, raise Exception)
    if restrict:
        assert Regexps.re_key_restrict.fullmatch(key)
    else:
        assert Regexps.re_key_regular.fullmatch(key)
    L = len(self.lists)
    # L = 3  #  for debug
    split_key = key.split('.')
    keylen = len(split_key)
    assert keylen > 0
    main_key = split_key[keylen - 1]

    # This is really 2 for-loops, but we need to be able to start in the middle of an inner loops.
    # So it becomes easier to write it as a single while-loop

    # We iterate over possible candidate names for lookup in the while True - loop below
    # Since we need to iterate

    if startafter:
        assert len(startafter) == 2
        j = startafter[1]
        current = startafter[0].split('.')
        search_key = startafter[0]
        i = len(current) - 1
        postfix = current[-1]
    else:
        i = keylen  # length of prefix to take
        j = L - 1  #
        postfix = _ALL_SUFFIX

    while True:
        j += 1
        if j == L:
            j = 0
            if postfix == _ALL_SUFFIX:  # comparison with == rather than is (because main_key == ALL_SUFFIX is possible)
                postfix = main_key
                i -= 1
                if i == -1:
                    return None, None
            else:
                postfix = _ALL_SUFFIX
            search_key = ".".join(split_key[0:i] + [postfix])
            if restrict and Regexps.re_key_regular.fullmatch(search_key):
                j = L - 1
                continue
        # print (search_key, j)
        if search_key in self.lists[j]:
            return search_key, j

    # for i in range(keylen-1, -1,-1):
    #    prefix = ".".join(split_key[0:i])
    #    search_key = prefix + "." + main_key
    #    for j in range(L):
    #    #   print(search_key, j) -- debug
    #        if search_key in self.lists[j]:
    #            return search_key, j
    #    search_key = prefix + "._all"
    #    for j in range(L):
    #    #   print(search_key, j)  -- debug
    #        if search_key in self.lists[j]:
    #            return search_key, j
    # return None, None


def locate_function(self, key: str):
    main_key = key.lower()
    L = len(self.lists)
    search_key = "__fun__" + main_key
    for j in range(L):
        if search_key in self.lists[j]:
            return search_key, j
    search_key = "_fun" + main_key
    for j in range(L):
        if search_key in self.lists[j]:
            return search_key, j
    return None, None