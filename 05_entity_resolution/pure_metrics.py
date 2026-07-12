"""
Pure-Python string metrics — drop-in replacements for jellyfish (soundex, jaro_winkler_similarity).

WHY: jellyfish is a compiled (native) extension. Catalyst AppSail's Catalyst-Managed Python runtime
does NOT pip-install requirements.txt — libraries must be shipped inside the app folder, and shipping
compiled binaries across platforms is fragile. These pure-Python implementations remove that risk
entirely while producing the SAME values (verified against jellyfish on the project's name data).

Algorithms are the standard, well-specified ones:
  - American Soundex
  - Jaro similarity + Winkler prefix boost (prefix scale 0.1, max prefix 4)
"""

_SOUNDEX_CODES = {
    **{c: "1" for c in "BFPV"},
    **{c: "2" for c in "CGJKQSXZ"},
    **{c: "3" for c in "DT"},
    **{c: "4" for c in "L"},
    **{c: "5" for c in "MN"},
    **{c: "6" for c in "R"},
}


def soundex(s):
    """American Soundex. Returns '' for input with no usable letters (jellyfish-compatible)."""
    if not s:
        return ""
    s = "".join(ch for ch in s.upper() if ch.isalpha() and ch.isascii())
    if not s:
        return ""

    first = s[0]
    out = first
    prev_code = _SOUNDEX_CODES.get(first, "")

    for ch in s[1:]:
        code = _SOUNDEX_CODES.get(ch, "")
        if ch in "HW":
            # H and W are ignored but do NOT reset adjacency (same-coded letters
            # separated by H/W count once)
            continue
        if code:
            if code != prev_code:
                out += code
                if len(out) == 4:
                    break
            prev_code = code
        else:
            # vowels (AEIOUY) separate codes -> reset adjacency
            prev_code = ""

    return (out + "000")[:4]


def jaro_similarity(s1, s2):
    """Standard Jaro similarity."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_window = max(len1, len2) // 2 - 1
    if match_window < 0:
        match_window = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0

    for i in range(len1):
        start = max(0, i - match_window)
        end = min(i + match_window + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # count transpositions
    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    m = float(matches)
    return (m / len1 + m / len2 + (m - transpositions) / m) / 3.0


def jaro_winkler_similarity(s1, s2, prefix_scale=0.1, max_prefix=4):
    """Jaro similarity with the Winkler common-prefix boost."""
    jaro = jaro_similarity(s1, s2)
    # common prefix length (capped)
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b:
            break
        prefix += 1
        if prefix == max_prefix:
            break
    return jaro + prefix * prefix_scale * (1.0 - jaro)
