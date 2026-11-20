"""Hinglish transliteration matching (I3).

Hinglish has no fixed spelling: 'pakka', 'pakkaa' and 'paka' are the same word, and the same phrase may be
written in Devanagari. A banned phrase listed once in one spelling is therefore easy to dodge. Phrases placed in
a rule's `translit_phrases` are matched on a *sound skeleton* instead of exact letters:

  1. Devanagari words are first converted to rough Latin.
  2. Each word is reduced to a skeleton (long vowels shortened, ph->f, w->v, chh->ch, doubled letters collapsed,
     a final 'a' dropped, and so on).
  3. A phrase matches when its skeleton words appear in order, next to each other.

This is a deliberately small, explainable rule set, not a language model. It widens spelling tolerance for the
phrases an owner has chosen; it does not understand meaning, so paraphrases still need a human or the AI judge.
"""
import re

_WORD = re.compile(r"[A-Za-z\u0900-\u097F]+(?:'[A-Za-z]+)?")
_DEV = re.compile(r"[\u0900-\u097F]")

_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॉ": "o", "ॅ": "e"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
         "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
         "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
         "ष": "sh", "स": "s", "ह": "h", "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "j", "ड़": "d", "ढ़": "dh", "फ़": "f"}
_VIRAMA, _NUKTA = "्", "़"
_NASAL = {"ं": "n", "ँ": "n"}


def devanagari_to_latin(word: str) -> str:
    """Rough Latin sound of one Devanagari word (enough for matching, not a transliteration standard)."""
    chars = list(word.replace(_NUKTA, ""))
    out, i = [], 0
    while i < len(chars):
        ch = chars[i]
        if ch in _CONS:
            out.append(_CONS[ch])
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            else:
                out.append("a")  # inherent vowel; dropped at the end of a word below
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _NASAL:
            out.append(_NASAL[ch])
        elif ch == "ः":
            out.append("h")
        i += 1
    s = "".join(out)
    return s[:-1] if s.endswith("a") and not word.endswith(tuple(_MATRAS)) and len(s) > 2 else s


def skeleton(word: str) -> str:
    """Sound skeleton of a single word (Latin or Devanagari)."""
    w = devanagari_to_latin(word) if _DEV.search(word) else word
    w = w.lower().replace("'", "")
    for a, b in (("chh", "ch"), ("ph", "f"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("w", "v"), ("z", "j"),
                 ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ai", "e"), ("au", "o"), ("ei", "e")):
        w = w.replace(a, b)
    w = re.sub(r"([bdgjkt])h", r"\1", w)          # aspirates: bh, dh, gh, jh, kh, th -> b, d, g, j, k, t
    w = w.replace("sh", "s")
    w = re.sub(r"(?<=[aeiou])y(?=[aeiou])", "", w)  # jayega ~ jaega
    w = w.translate(str.maketrans({"e": "i", "o": "u"}))
    w = re.sub(r"([a-z])\1+", r"\1", w)            # doubled letters
    if len(w) > 3 and w.endswith("a"):
        w = w[:-1]                                   # pakka ~ pakk ~ pak
    return w


def tokens(text: str) -> list[tuple[str, int, int]]:
    return [(skeleton(m.group(0)), m.start(), m.end()) for m in _WORD.finditer(text)]


def usable(phrase: str) -> bool:
    """A phrase is only safe to match loosely when its skeleton is long enough not to hit ordinary words."""
    sk = [skeleton(m.group(0)) for m in _WORD.finditer(phrase)]
    return bool(sk) and sum(len(s) for s in sk) >= 6 and all(s for s in sk)


def find(text: str, phrase: str) -> list[tuple[int, int]]:
    """Spans in text whose words sound like the phrase's words, in order and adjacent."""
    want = [t[0] for t in tokens(phrase)]
    if not want or not usable(phrase):
        return []
    have = tokens(text)
    spans = []
    for i in range(len(have) - len(want) + 1):
        if [h[0] for h in have[i:i + len(want)]] == want:
            spans.append((have[i][1], have[i + len(want) - 1][2]))
    return spans
