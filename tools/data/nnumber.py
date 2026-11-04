"""FAA N-number to ICAO 24-bit address: the US block's fixed enumeration (as in dopplerprint's
eval/livermore.rs, whose test values are checked in __main__).

usage: python tools/data/nnumber.py N1387U [...]
"""
import sys

LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"     # no I or O
SUFFIX = 1 + 24 * 25
B4 = 1 + 24 + 10
B3 = 10 * B4 + SUFFIX
B2 = 10 * B3 + SUFFIX
B1 = 10 * B2 + SUFFIX


def icao(reg: str) -> str | None:
    s = reg.upper().removeprefix("N")
    if not s or len(s) > 5 or s[0] == "0" or not s[0].isdigit():
        return None
    letter = lambda c: LETTERS.index(c) if c in LETTERS else None
    def suffix(r):
        if len(r) == 1 and letter(r[0]) is not None:
            return 25 * letter(r[0]) + 1
        if len(r) == 2 and letter(r[0]) is not None and letter(r[1]) is not None:
            return 25 * letter(r[0]) + 1 + letter(r[1]) + 1
        return None
    out = 0xA00001 + (int(s[0]) - 1) * B1
    for i, b in ((1, B2), (2, B3), (3, B4)):
        if len(s) == i:
            return f"{out:06x}"
        if s[i].isalpha():
            sf = suffix(s[i:])
            return None if sf is None else f"{out + sf:06x}"
        out += int(s[i]) * b + SUFFIX
    if len(s) == 4:
        return f"{out:06x}"
    c = s[4]
    if c.isalpha():
        return None if letter(c) is None else f"{out + 1 + letter(c):06x}"
    return f"{out + 1 + 24 + int(c):06x}"


if __name__ == "__main__":
    for n, h in (("N1387U", "a09c49"), ("N172EL", "a1210a"), ("N413AK", "a4df4f"), ("N7PG", "a95128")):
        assert icao(n) == h, (n, icao(n), h)
    for reg in sys.argv[1:]:
        print(reg, icao(reg))
