"""Testler için sahte ama doğrulamadan geçen numaralar üretir. Gerçek kişiye ait değildir."""


def fake_tc(first9: str = "123456789") -> str:
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return first9 + str(d10) + str(d11)


def fake_vkn(first9: str = "123456789") -> str:
    total = 0
    for i in range(9):
        tmp = (int(first9[i]) + (9 - i)) % 10
        tmp2 = (tmp * (2 ** (9 - i))) % 9
        if tmp != 0 and tmp2 == 0:
            tmp2 = 9
        total += tmp2
    return first9 + str((10 - total % 10) % 10)


def fake_iban(bban: str = "0006100519786457841326") -> str:
    """TR IBAN: 'TR' + 2 kontrol hanesi + 22 haneli BBAN."""
    numeric = bban + "2927" + "00"  # T=29, R=27
    check = 98 - int(numeric) % 97
    raw = f"TR{check:02d}{bban}"
    return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def fake_card(first15: str = "411111111111111") -> str:
    for last in "0123456789":
        number = first15 + last
        total = 0
        for i, ch in enumerate(reversed(number)):
            n = int(ch)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        if total % 10 == 0:
            return " ".join(number[i : i + 4] for i in range(0, 16, 4))
    raise AssertionError
