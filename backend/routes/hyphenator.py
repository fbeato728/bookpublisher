"""
Pure Python hyphenation module.
Extracted from the Hyphenate This! Calibre plugin by Saulius P.
Original hyphenator.py by Wilbert Berendsen, March 2008.
License: LGPL.
"""

import re

__all__ = ("Hyphenator",)

# cache of per-file Hyph_dict objects
hdcache = {}

parse_hex = re.compile(r'\^{2}([0-9a-f]{2})').sub
parse     = re.compile(r'(\d?)(\D?)').findall


def hexrepl(matchObj):
    return chr(int(matchObj.group(1), 16))


class parse_alt(object):
    def __init__(self, pat, alt):
        alt = alt.split(',')
        self.change = alt[0]
        if len(alt) > 2:
            self.index = int(alt[1])
            self.cut   = int(alt[2]) + 1
        else:
            self.index = 1
            self.cut   = len(re.sub(r'[\d\.]', '', pat)) + 1
        if pat.startswith('.'):
            self.index += 1

    def __call__(self, val):
        self.index -= 1
        val = int(val)
        if val & 1:
            return dint(val, (self.change, self.index, self.cut))
        else:
            return val


class dint(int):
    def __new__(cls, value, data=None, ref=None):
        obj = int.__new__(cls, value)
        if ref and type(ref) == dint:
            obj.data = ref.data
        else:
            obj.data = data
        return obj


class Hyph_dict(object):
    def __init__(self, filename):
        self.patterns = {}
        try:
            f       = open(filename)
            charset = f.readline().strip()
        except Exception:
            f       = open(filename, encoding='latin-1')
            charset = f.readline().strip()
        if charset.startswith('charset '):
            charset = charset[8:].strip()

        for pat in f:
            try:
                pat = pat.decode(charset).strip()
            except Exception:
                pat = pat.strip()
            if not pat or pat[0] == '%':
                continue
            pat = parse_hex(hexrepl, pat)
            if '/' in pat:
                pat, alt = pat.split('/', 1)
                factory  = parse_alt(pat, alt)
            else:
                factory = int
            tag, value = list(zip(*[(s, factory(i or "0")) for i, s in parse(pat)]))
            if max(value) == 0:
                continue
            start, end = 0, len(value)
            while not value[start]:   start += 1
            while not value[end - 1]: end   -= 1
            self.patterns[''.join(tag)] = start, value[start:end]
        f.close()
        self.cache  = {}
        self.maxlen = max(len(k) for k in self.patterns)

    def positions(self, word):
        word   = word.lower()
        points = self.cache.get(word)
        if points is None:
            prepWord = '.%s.' % word
            res = [0] * (len(prepWord) + 1)
            for i in range(len(prepWord) - 1):
                for j in range(i + 1, min(i + self.maxlen, len(prepWord)) + 1):
                    p = self.patterns.get(prepWord[i:j])
                    if p:
                        offset, value = p
                        s       = slice(i + offset, i + offset + len(value))
                        res[s]  = list(map(max, value, res[s]))
            points = [dint(i - 1, ref=r) for i, r in enumerate(res) if r % 2]
            self.cache[word] = points
        return points


class Hyphenator(object):
    def __init__(self, filename, left=2, right=2, cache=True):
        self.left  = left
        self.right = right
        if not cache or filename not in hdcache:
            hdcache[filename] = Hyph_dict(filename)
        self.hd = hdcache[filename]

    def positions(self, word):
        right = len(word) - self.right
        return [i for i in self.hd.positions(word) if self.left <= i <= right]

    def iterate(self, word):
        for p in reversed(self.positions(word)):
            if p.data:
                change, index, cut = p.data
                if word.isupper():
                    change = change.upper()
                c1, c2 = change.split('=')
                yield word[:p + index] + c1, c2 + word[p + index + cut:]
            else:
                yield word[:p], word[p:]

    def inserted(self, word, hyphen='-'):
        """Return the word with all hyphenation points marked by hyphen char."""
        try:
            word = str(word)
        except Exception:
            pass
        l = list(word)
        for p in reversed(self.positions(word)):
            if p.data:
                change, index, cut = p.data
                if word.isupper():
                    change = change.upper()
                l[p + index: p + index + cut] = change.replace('=', hyphen)
            else:
                l.insert(p, hyphen)
        return ''.join(l)

    __call__ = iterate
