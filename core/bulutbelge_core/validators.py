"""Türk kimlik ve finans numaraları için kontrol hanesi doğrulamaları.

Kalıba uyan ama doğrulamadan geçmeyen değerler bulgu sayılmaz; bu, rastgele
rakam dizilerinin yanlışlıkla maskelenmesini azaltır.
"""


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def tc_kimlik_valid(value: str) -> bool:
    d = [int(c) for c in value]
    if len(d) != 11 or d[0] == 0:
        return False
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = sum(d[:10]) % 10
    return d[9] == d10 and d[10] == d11


def vkn_valid(value: str) -> bool:
    if len(value) != 10 or not value.isdigit():
        return False
    total = 0
    for i in range(9):
        tmp = (int(value[i]) + (9 - i)) % 10
        tmp2 = (tmp * (2 ** (9 - i))) % 9
        if tmp != 0 and tmp2 == 0:
            tmp2 = 9
        total += tmp2
    return (10 - total % 10) % 10 == int(value[9])


def iban_valid(value: str) -> bool:
    iban = value.replace(" ", "").upper()
    if len(iban) < 15 or not iban[:2].isalpha():
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def luhn_valid(value: str) -> bool:
    if not 13 <= len(value) <= 19 or not value.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(value)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
