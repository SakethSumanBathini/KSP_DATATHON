"""
Component 5a — Kannada<->Roman transliteration interface.

PRODUCTION: plug in AI4Bharat IndicXlit (pip install ai4bharat-transliteration).
    from ai4bharat.transliteration import XlitEngine
    engine = XlitEngine("kn", beam_width=10, rescore=True)
    engine.translit_word(kannada_word, topk=5)  -> ranked Roman candidates

HERE (verifiable stand-in): a lightweight rule-based Kannada->Roman mapping covering the
demo names, returning a small candidate set. Clearly marked as a stand-in; the interface
is identical so swapping to IndicXlit is a one-line change with no downstream impact.
"""

# Minimal Kannada akshara -> Roman mapping (sufficient for the seeded demo names)
_KN_MAP = [
    ("ರಾಮಯ್ಯ", ["ramayya","ramaiah","ramaiya"]),
    ("ರಾಮು",   ["ramu"]),
    ("ರಮೇಶ್",  ["ramesh"]),
    ("ಸುರೇಶ್", ["suresh"]),
    ("ಮಂಜುನಾಥ್",["manjunath","manjunatha"]),
    ("ಪ್ರಕಾಶ್", ["prakash"]),
    ("ನಾಗರಾಜ್", ["nagaraj","nagaraja"]),
    ("ಶಿವಕುಮಾರ್",["shivakumar"]),
    ("ಮಹೇಶ್",   ["mahesh"]),
    ("ಲಕ್ಷ್ಮಿ", ["lakshmi"]),
    ("ಸವಿತಾ",   ["savitha","savita"]),
    ("ಗೀತಾ",    ["geetha","gita"]),
    ("ಕಾವ್ಯ",   ["kavya"]),
    ("ಸುನೀತಾ",  ["sunitha","sunita"]),
    ("ರಾಧಾ",    ["radha"]),
]

def is_kannada(text):
    return any('\u0c80' <= ch <= '\u0cff' for ch in text)

def _strip_noise(s):
    # remove initials/dots/extra tokens like ".ಕೆ" or " K"
    return s.replace(".", " ").strip()

def transliterate(name, topk=5):
    """
    Return a set of Roman candidate strings for a name (Kannada or Roman).
    PRODUCTION: replace body with IndicXlit engine.translit_word(...).
    """
    name = _strip_noise(name)
    if not is_kannada(name):
        # already Roman: normalize to lowercase token set
        return { name.lower() }
    cands = set()
    # try to match known aksharas as substrings
    for kn, romans in _KN_MAP:
        if kn in name:
            cands.update(romans)
    # also handle the ".ಕೆ" style trailing initial (ಕೆ -> 'k')
    if "ಕೆ" in name:
        cands = { c for c in cands }  # initial handled separately in blocking
    if not cands:
        cands = { name }  # fallback: keep original (would be IndicXlit output in prod)
    return cands

if __name__ == "__main__":
    for n in ["ರಾಮಯ್ಯ.ಕೆ", "Ramaiah K", "ರಾಮು", "Ramesh", "ಮಂಜುನಾಥ್"]:
        print(f"{n:15s} -> {sorted(transliterate(n))}")
