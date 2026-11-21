"""Kişi adı kaçırma ölçümü. Yalnızca uydurma ad ve soyad kullanır; değer yazdırmaz.

Kullanım (core/ içinden): python tools/ad_olcum.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulutbelge_core.detect import detect
from bulutbelge_core.rules import Rules
bilinen=["Ahmet","Ayşe","Mehmet","Zeynep","Mustafa","Elif","Hakan","Selin","Burak","Derya","Emre","Merve","Serkan","Pınar","Okan"]
bilinmeyen=["Beyza","Yağmur","Kuzey","Asya","Poyraz","Ecrin","Ilgın","Miraç","Defne","Alaz","Nehir","Çınar","Rüzgar","Aras","Ceren"]
soyad=["Karaman","Tekinalp","Özdemirci","Yurtsever","Baltacı","Çakırer","Demirtaş","Sarıkaya","Koçyiğit","Aydınlı","Gürbüz","Tanrıverdi","Kandemir","Erdoğmuş","Bozkurtoğlu"]
baglamlar={
 "etiketli":"Ad Soyad: {n}\nT.C. Kimlik No: yok",
 "cumle":"Toplantıya {n} katıldı ve raporu sundu.",
 "buyuk_harf":"SÖZLEŞME TARAFI: {N}",
 "tablo":"Sıra | Ad | Tutar\n1 | {n} | 450 TL",
 "unvanli":"Sayın {n}, başvurunuz alınmıştır.",
 "sadece_ad_baglam":"Müşteri temsilcisi {a} ile görüştük.",
}
r=Rules.from_dict(None)
def olc(adlar):
    sonuc={}
    for k,tpl in baglamlar.items():
        ok=0;top=0
        for i,a in enumerate(adlar):
            s=soyad[i%len(soyad)]; n=f"{a} {s}"; N=n.upper().replace("İ","İ")
            txt=tpl.format(n=n,N=N,a=a)
            hedef=n if "{a}" not in tpl else a
            if "{N}" in tpl: hedef=N
            fs=[f for f in detect(txt,r) if f.type=="kisi_adi"]
            bas=txt.index(hedef); son=bas+len(hedef)
            # örtüşme
            kapsadi=any(f.start<=bas+1 and f.end>=son-1 for f in fs)
            ok+=kapsadi; top+=1
        sonuc[k]=(ok,top)
    return sonuc
for ad,l in (("sozlükte olan",bilinen),("sozlükte olmayan",bilinmeyen)):
    print(ad)
    for k,(ok,top) in olc(l).items(): print(f"  {k:18} yakalanan {ok}/{top}  kaçırma {100*(top-ok)/top:.0f}%")
