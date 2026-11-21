"""XML metnini doğrusal sürede belirteçlere ayırma (güvenlik taraması F1, F2, F9, F20).

`textdoc` ve `efatura` XML'i tek bir düzenli ifadeyle tarar: yorum (`<!--...-->`), CDATA, işleme
talimatı (`<?...?>`) ve etiket seçenekleri. `pattern.finditer(text)` kapanmayan her `<!--` (ya da
`<![CDATA[`, `<?`) için metnin sonuna kadar okur ve bunu sonraki her açıcıda yineler: kapanmayan
açıcılarla dolu bir dosyada süre ikinci derecedendir.

`iter_tokens` aynı deseni yalnızca `<` konumlarında ve kapanışı `str.find` ile önceden bulunmuş bir
pencere içinde dener: kapanış yoksa (sonrasında da olamayacağı için) o açıcı tek adımda geçilir. Sonuç
`pattern.finditer(text)` ile aynı eşleşmelerdir; desenin seçeneklerinin hepsi `<` ile başlamalıdır.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

_OPENERS = (("<!--", "-->"), ("<![CDATA[", "]]>"), ("<?", "?>"))


def iter_tokens(pattern: re.Pattern[str], text: str) -> Iterator[re.Match[str]]:
    pos = 0
    n = len(text)
    no_close: set[str] = set()  # sonrasında bulunmadığı kesinleşen kapanışlar
    while True:
        i = text.find("<", pos)
        if i < 0:
            return
        end = n
        for opener, closer in _OPENERS:
            if text.startswith(opener, i):
                j = -1 if closer in no_close else text.find(closer, i + len(opener))
                if j < 0:
                    no_close.add(closer)
                    end = -1
                else:
                    end = j + len(closer)
                break
        m = pattern.match(text, i, end) if end >= 0 else None
        if m is None:
            pos = i + 1
            continue
        yield m
        pos = max(m.end(), i + 1)
