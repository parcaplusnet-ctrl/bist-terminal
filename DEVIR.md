# Radar devir talimatı (16.11.2026 güncel)

Amaç: BIST Yükseliş Radarı taramaları 17.11.2026 Salı 13:00'dan sonra yeni hesaptan sürsün; en az kayıpla en hızlı ve en çok yükselecek hisseleri bulmak.

## 1. Önce erişimler (devralan hesapta)
- Borsa Tarama Terminali: https://claude.ai/artifact/Q8A2s6Dk83tHhzZEuzgNrM — hesabın YAZAR yetkisi olmalı (veri.json, index.html, arsiv/* burada yayınlanır).
- Motor dosyaları (motor/radar.py.txt, motor/MOTOR.md, motor/rules.json) artık terminal artifact'ının içinde (path ile okunur). Ayrı Radar Motoru artifact'ına veya eski hesaba bağımlılık YOKTUR; eski hesap kapanabilir.
- ArtifactData `canli/durum` erişimi isteğe bağlı: reddedilirse görevler canlı akışı atlar, tarama yine çalışır.

## 2. Görevleri kur (Scheduled task, model: claude-opus-5-5, onay: otomatik)
Zaman dilimi CRON_TZ=Europe/Istanbul. Komut metinleri gorev_komutlari/ klasöründe, aynen yapıştır:
- 1_saatlik_tarama_16.txt  → `16 10-18 * * 1-5` (BIST saatlik tarama; 18:16'da ABD de)
- 2_takip_01_31_46.txt     → üç ayrı görev: `31 10-17 * * 1-5`, `46 10-17 * * 1-5`, `1 11-18 * * 1-5` (aynı komut)
- 3_abd_pazartesi_2216.txt → `16 22 * * 1` (isteğe göre 1-5)
Eski hesaptaki görevler 17.11 13:05'te otomatik durur; çakışmaması için yenileri 13:00'dan sonraki ilk uygun saatten itibaren başlat. Bu paketteki komutlarda "devredildi" zaman kontrolü YOKTUR (yeni hesap için doğru).

## 2b. Motor güncellemesi
Motor dosyaları terminal artifact'ında durur. Değiştirmek için terminali yayınlarken files {"motor/radar.py.txt": ...} gönder; görevler veri/HTML yayınında files'a motor/ yazmadığı için dosyalar korunur.

## 3. Değişenler (16.11 denetimi) — motor v10, MOTOR.md §6 ve §13
- Öğrenme döngüsü artık otomatik: `adaylar --piyasa bist --girdi cikti/bist.json` gözlem ve öğren adımlarını çalıştırır. Her yayına arsiv/gozlem_bist_<gün>.json eklenmelidir, yoksa öğrenme verisi birikmez. İlk gerçek bulgular 18.11 kapanışından sonra oluşur; likidite eşiği de o zaman öğrenilir.
- Kasa filtresi (deneme): ilk kez seçilen hisse 10:00-11:59 arası alınmaz; tekrar seçilenler önce alınır. 30 yeni sonuçta yeniden değerlendir.
- `adaylar` KAP kararı eksik adayları uyarıyla gösterir (`son_tarama.karar_eksik`); karar.json'u tamamlayıp yeniden çalıştır.
- rules.json artık motor/rules.json'dan gelir (09.11 tarihli kopya, puan eşiği 7). ArtifactData radar/rules gerekmez.
- Lab kartında canlı isabet kıyası (stoplu) gösterilir. ABD modülü yalnızca laboratuvar, kasaya girmez.

## 4. İlk gün kontrol listesi
1. İlk saatlik tarama özetinde "GÖZLEM:" ve "ÖĞREN (bist):" satırları var mı?
2. Terminalde arsiv/ dosyası ve veri.json yayında mı, Kasa değeri sürüyor mu (başlangıç 100.000 ₺, 16.11 öğleden sonra ~108.300 ₺)?
3. :01/:31/:46 görevleri "kontrol" çalıştırıp yalnızca değişiklik varsa yayınlıyor mu?
4. Atlanan alımlar (ilk seçim 10-11) kasanın "Son hareketler" listesinde nedeniyle görünüyor mu?

## 5. Açık işler
- GitHub Pages kopyası bayat (yeni, kısıtlı yetkili token gerekir; eski açığa çıkan token iptal edilmeli).
- Kural ağırlıkları yalnızca n ≥ 30, kaldıraç ≥ 1,3/≤ 0,7 ve 3 farklı günde aynı yön ise ±0,25 adımla değişir (MOTOR.md §6).

Yatırım tavsiyesi değildir.

## Ek (16.11 akşam denetimi)
- Motor güncellendi: BIST vade sonu artık vade günü 18:00 kapanışına göre sonuçlanır (18:16 taraması aynı gün kapatır); ertesi sabahki mumlar hedef/stop kararına katılmaz. Ayrıntı: motor/MOTOR.md §14.
- Radar Motoru sayfası (eski) güncellendi; devralan hesap motoru terminalin motor/ klasöründen okur.
- Terminal verisi sayfada 60 saniyede bir yenilenir.

## Ek (16.11 gece): Özellik laboratuvarı otomatik
Saatlik görev `adaylar` komutunu `--girdi cikti/bist.json` ile çalıştırdığında özellik laboratuvarı (`ozlab`, ~100 sn) kendiliğinden çalışır ve `veri.json → lab_ozellik` güncellenir. Görev metnindeki "MOTOR.md §4 (laboratuvar) YAPILMAZ" ifadesi kripto/sektör/endeks laboratuvarı içindir; özellik laboratuvarı bundan bağımsızdır (MOTOR.md §15). Özetteki `ÖZLAB:` satırını belirt.

Ek (16.11 gece): Özellik laboratuvarı artık birikimli çalışır (grafik/örnek/özellik sayaçları sıfırlanmaz, her turda 3 yeni formasyon denenir). Ayrıntı: motor/MOTOR.md §15.
Ek (17.11 gece): Kalite kapısı (MOTOR.md §16) eklendi: görevlerde motor/model.json da indirilmeli (model.json adıyla); seçim 0-5 hisse. Haftalık yeniden eğitim için motor/egit.py.txt.
Ek (17.11 sabah): Sade takip: takipte en fazla 10 açık kayıt, tarama başına en fazla 3 yeni hisse, izleme 5; stop tavanı %2,5; haftalık model yeniden eğitimi (MOTOR.md §16.1). gorev_komutlari/1_saatlik_tarama_16.txt bu kurallara göre güncel metindir (aşağıdaki komut güncellenmiştir).
Ek (17.11 öğle): Takip ≠ portföy: takip = alım kararı verilmemiş adaylar, portföy = alınanlar (en fazla 10), takipteki daha iyi aday portföydeki en zayıfla değiştirilir (kasa komutu yapar); elle takip sınırı yok, model öğrenir (günlük sayı ve evren kademesi); portföy üst sınırı 10. İzleme listesi kaldırıldı. Model eğitimi her taramada (bist → paket/haber → egit.py → adaylar); güncel model.json terminal artifact'ının motor/ klasöründe tutulur ve her yayında güncellenir. Ayrıntı: MOTOR.md §16 ve §16.1; saatlik görev komutu bu akışa göre yenilendi.
