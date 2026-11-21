"""Daha önce maskelenmiş (rakam olmayan) değerler doğrulayıcıyı çökertmemeli."""

from bulutbelge_core.validators import iban_valid, tc_kimlik_valid, vkn_valid


def test_karartma_blogu_tc_ve_iban_icin_gecersiz_sayilir():
    assert tc_kimlik_valid("\u2588" * 11) is False
    assert tc_kimlik_valid("1234567890\u2588") is False
    assert tc_kimlik_valid("1\u00b2345678901") is False
    assert iban_valid("TR\u2588\u2588" + "\u2588" * 22) is False
    assert vkn_valid("\u2588" * 10) is False


def test_gecerli_tc_hala_gecerli():
    assert tc_kimlik_valid("10000000146") is True
