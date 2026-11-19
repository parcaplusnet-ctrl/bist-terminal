# Radar bulut tarama motoru · çalışma kılavuzu

Terminal (merkez, yayın hedefi): https://claude.ai/artifact/Q8A2s6Dk83tHhzZEuzgNrM — bu hesapta yazar yetkisi var. Motor dosyaları bu sayfada (Radar Motoru) tutulur.
Motor: terminalin yayınlanmış `motor/radar.py.txt` dosyası (Python 3, yalnızca standart kütüphane). Chrome gerekmez.
Gerekli ağ izinleri (hesap ayarı): scanner.tradingview.com, news-headlines.tradingview.com, query1/query2.finance.yahoo.com, www.kap.org.tr.

Kurallar: Türkçe, duygudan arınmış. Terminalde ULAK ile ilgili hiçbir şey gösterilmez. Kullanıcı, sistem en iyisi olana kadar sormadan deneme izni verdi.
Laboratuvar (kripto, endeks katmanları, sektör rotasyonu) yalnızca öğrenme içindir; işlem adayı üretmez.

## 0. Hazırlık (her çalışmada)
1. `Artifact` read: url (path olmadan) → sonra path ile `veri.json`, `motor/radar.py.txt`, `index.html` oku (dosyalar scratchpad'e kaydedilir).
2. Çalışma klasörü kur: `radar.py.txt` → `radar.py`; `veri.json` kopyala.
3. `ArtifactData` get radar/rules → `rules.json` (data alanını dosyaya yaz); canli/durum'un version'ını not et.
4. Erişim testi: `curl -sS -X POST https://scanner.tradingview.com/turkey/scan -d '{"columns":["name"],"range":[0,1]}'`. 403 ise ağ izni yok: hiçbir şeyi değiştirme, nedenini yaz ve bitir.

## 1. Açık kayıtların kontrolü
> ZORUNLU: kontrol sonrası ve yayından önce §8 (kasa) adımı çalıştırılır.
STOP KURALI (09.11 kullanıcı talimatı): Stop yalnızca 1 saatlik mum stop rakamının ALTINDA KAPANIRSA geçerlidir. Fiyat stopun altına inip saatlik mum stop üzerinde kapanırsa stop sayılmaz (stop_igne alanına not edilir). Henüz kapanmamış mum sayılmaz. BIST saat mumları TradingView ile aynıdır: tam saatte başlar (10:00-11:00 … 17:00-18:10; 15 dk mumlardan oluşturulur). Seçimden önce başlamış mum değerlendirilmez; bu yüzden 10:16 taramasında stop kararı verilmez, ilk karar 11:00'de kapanan 10:00 mumuyla (11:01/11:16 çalışmaları) verilir. Motor bunu kendisi uygular.
`python3 -I radar.py kontrol --veri veri.json` → `cikti/kontrol.json` (değişen kayıtlar). Değişen varsa canli/durum'a (get → if_version ile update) `hedefe_ulasan`, `stop_olan`, `suresi_dolan` listelerini yaz (laboratuvar kayıtları hariç). Terminal sesli uyarı verir.

## 2. BIST tam tarama (canlı akışlı)
1. `python3 -I radar.py bist --rules rules.json --veri veri.json`
2. `python3 -I radar.py paket --girdi cikti/bist.json --n 12 --etiket "GG.AA BIST"` → `cikti/paketler.json`.
3. Her paketi sırayla canli/durum'a `set` et (her pakete `at` = şimdiki UTC ISO zamanı, her `son` öğesine benzersiz `t` alanı ekle; paketler arası ~20 sn). Her pakette ≥4 hisse pk ve tk ile bulunur.
4. Haber/KAP: `python3 -I radar.py haber --piyasa bist KOD1 KOD2 ...` (ilk 20 aday). Her hisse için 30 günlük başlıkları değerlendir: olumlu (+1: zarardan kâra, kâr artışı, sipariş, geri alım, hedef fiyat artışı), olumsuz (-1: zarara geçiş, sert kâr düşüşü >%50, rapor gecikmesi, kayyım, sermaye artırımı/hisse satışı, hedef düşürme), nötr (0). `karar.json` = `[{"kod","haber_puan","haber":"olumlu: ... (GG.AA)"}]`.
5. `python3 -I radar.py adaylar --girdi cikti/bist.json --karar karar.json --veri veri.json --piyasa bist` → 10 aday + izleme.
6. Son paketi `durum:"bitti"` ile, veri.json YAYINLANDIKTAN SONRA gönder (terminal bitti görünce veri.json'u yeniden yükler).

## 3. ABD taraması
Aynı akış: `abd` → `paket` (paketlere "para":"$" eklenir) → `haber --piyasa abd` → `adaylar --piyasa abd`.

## 4. Laboratuvar
- `python3 -I radar.py kripto --veri veri.json` ; `python3 -I radar.py sektor` ; `python3 -I radar.py endeks --veri veri.json`
- `python3 -I radar.py kaydet kripto sektor endeks --veri veri.json` (açık deneyler korunur; endeks yalnızca açık deney yoksa yenilenir; sektör projeksiyonu yalnızca bekleyen yoksa yenilenir).
- BTC tahmini 24 saat sonra, sektör projeksiyonu cuma kapanışında kontrol edilir (kripto.tahminler / sektor_lab.projeksiyon: sonuc "Doğru"/"Yanlış", gerceklesen).

## 5. Öğrenme ve yayın
1. `learning` listesine sıradaki numarayla 1-3 madde (bulgu + değişiklik). Kural ağırlıkları yalnızca veri destekliyorsa ve küçük adımla değişir; radar/rules'a if_version ile yaz. Stop marjı hedefi %1 altı; %3 tavanı veri desteklemeden daraltılmaz.
2. `Artifact` publish: url + file_path = okunan index.html + files {"veri.json": <güncel veri.json>}. Yayındaki sürümün üstüne kur.
3. Merkez aktarım dosyası: `/mnt/user-data/outputs/merkez_aktarim_YYYY-MM-DD_HHMM.json` (ne değişti, adaylar, sonuçlar, öğrenme, kural değişiklikleri) → SendUserFile.
Vade kuralı: bitiş = seçimden sonra 2 tam İŞLEM GÜNÜ (hafta sonu ve resmî tatiller sayılmaz; seçim günü seansın kalanı bonus). Sonuç kontrolü saatlik mumlarla ve yalnız seçim anından sonraki mumlarla yapılır (motor bunu kendisi uygular).
4. Kısa özet. Süresi dolan (hedef de stop da görülmeden vadesi biten, sonuc="Başarısız") kayıtları özette AYRI bir başlıkla, kod · son değişim · en yüksek değişim ile listele; aynı kayıtlar canli/durum suresi_dolan listesine de yazılır (terminal uyarı bandı + sesli uyarı). Hedefe ulaşıp yeniden seçilen hisseler 'trend devam' olarak belirtilir. "Yatırım tavsiyesi değildir."

## 6. Arka plan gözlem arşivi ve öğrenme (16.11 denetiminden sonra OTOMATİK)
Amaç: yalnızca adayları değil TÜM hisseleri izleyip yükselen/düşen hisselerin neden hareket ettiğini öğrenmek. 09.11-16.11 arasında bu adım görev komutlarında "YAPILMAZ" yazdığı için hiç çalışmamıştı; artık `adaylar --piyasa bist` komutu gözlem (`gozlem`) ve öğren (`ogren`) adımlarını kendisi çalıştırır. Yapılacaklar:
1. Hazırlıkta arşivi indir: `Artifact` list scope "files" → `arsiv/gozlem_bist_YYYY-MM-DD.json` dosyalarından bugün ve önceki 4 işlem gününe ait olanları `read` paths ile çalışma klasörüne `arsiv/` altına indir. (Arşiv yoksa komut yenisini oluşturur.)
2. `adaylar` komutunu çalıştır (`--girdi cikti/bist.json`). Çıktıda "GÖZLEM:" ve "ÖĞREN (bist):" satırları görünmelidir; "UYARI" görürsen özette belirt.
3. Yayında bugünkü arşiv dosyasını da gönder: files {"veri.json": ..., "arsiv/gozlem_bist_YYYY-MM-DD.json": ...}. 30 işlem gününden eski arşiv dosyaları `null` ile kaldırılır.
4. Yeni gözlem işlendiyse çıktıdaki "Hareket kodları" için `haber` çalıştır; hareketi açıklayan haber/KAP varsa learning maddesine "neden" olarak yaz.
5. Kural ağırlığına geçiş: bir özellik ancak n ≥ 30, kaldıraç ≥ 1,3 (veya ≤ 0,7) ve en az 3 farklı günde aynı yönde ise küçük adımla (±0,25) ağırlığa yansıtılır.
6. İlk gerçek sonuçlar 18.11 kapanışından sonra oluşur (gözlem + 2 işlem günü). Likidite eşiği (`likidite.min`) ancak o zaman öğrenilir.
7. Kural dosyası: `motor/rules.json` bu artifact'tan indirilir (`rules.json` adıyla çalışma klasörüne konursa `radar.py` otomatik kullanır). ArtifactData `radar/rules` erişimi gerekmez.

## 7. Takip güncellemesi (15 dakikada bir, seans içinde; 09.11 kullanıcı talimatı)
> ZORUNLU: `kontrol` sonrası `python3 -I radar.py kasa --veri veri.json` çalıştır (§8); kasa değeri her 15 dakikada güncellenir.
Saatlik tarama :16'da çalışır; arada :01, :31 ve :46'da yalnızca açık kayıtlar güncellenir. Yeni tarama ve aday seçimi YOK.
1. Hazırlık §0 (rules gerekmez). Saatlik tarama sürüyorsa (canli/durum durum="taraniyor" ve `at` 30 dk içinde) hiçbir şey yapma ve bitir.
2. `python3 -I radar.py kontrol --veri veri.json` → açık BIST/ABD kayıtlarının anlık değişimi, en yüksek/en düşük ve sonuçları (hedef/stop/süre) güncellenir.
3. Değişen kayıt varsa canli/durum'a (get → if_version ile update) hedefe_ulasan / stop_olan / suresi_dolan yaz (sesli uyarı).
4. `Artifact` publish: file_path = okunan index.html, files {"veri.json": ...}; yalnızca veri.json değişir. Çakışma olursa yeniden oku, kontrolü yeni sürüm üzerinde tekrarla ve yayınla.
5. Aktarım dosyası ve uzun özet yok; yalnızca sonuçlanan kayıt varsa 1-2 cümle özet (stop olanlar ve süresi dolanlar ayrı). Yatırım tavsiyesi değildir.

## §8 Kasa (sanal portföy) — HER YAYINDAN ÖNCE ZORUNLU
Bu bölüm tüm görevler için geçerlidir ve görev metnindeki "kasa korunur" ifadesini şöyle yorumlar: kasa dondurulmaz, `kasa` komutuyla güncellenir; diğer anahtarlar (lab_ozellik, dogrulama, lab_bist, sektor_lab, kripto) aynen korunur.
- Sıra: `kontrol` → (tarama görevlerinde `adaylar`) → `python3 -I radar.py kasa --veri veri.json` → yayın.
- Kural: başlangıç 100.000 ₺; yeni seçime alım anındaki GÜNCEL toplam kasa değerinin %10'u (bileşik getiri; kasa büyüdükçe pozisyon da büyür); komisyon binde 1 (alış ve satış); en fazla 10 açık pozisyon; alım yalnızca 10:00–18:00 taramalarında; hedef %5 / stop / süre dolumunda satış; adet = tam sayı.
- Komut çıktısının son satırı "KASA: toplam … · nakit … · N açık" yazar; kasa.ozet.tarih güncel olmalı. Yayından sonra özete toplam değeri ekle.

## §9 Likidite (derinlik) kuralı — 16.11 kullanıcı kararı
Amaç: sığ hissede işlem açılmaz; yüklü (büyük tutarlı) alım-satım yapılabilmeli. Motor bunu kendisi uygular, ayrıca bir adım gerekmez.
- Ciro = kapanış × 30 günlük ortalama hacim (≈ günlük ₺ ciro; yalnız BIST). Derinlik: ≥100 mn ₺ Derin, 20-100 mn Orta, <20 mn Sığ.
- Sığ hisse `uygun` olamaz (aday, izleme "eşik üstü" ve kasa alımı dışı); sebep: "sığ hisse: günlük ort. ciro X mn ₺". Derin hisse +0,5 puan (`likit_100mn`).
- Kapasite: her seçimde `likit_mn`, `kapasite_tl` (= günlük cironun %1'i) ve `derinlik` alanları picks/history/kasa kayıtlarına yazılır. Kasa pozisyonu kapasiteyi aşmaz (`kapasite_siniri`=true), sığ kayıt kasaya alınmaz ("sığ hisse" atlandı). Kasa büyüdükçe işlem tutarı derin hisselere doğal olarak kayar.
- Öğrenme: `gozlem` arşivine `likit_mn` sütunu eklenir (eski arşivler otomatik doldurulur); `ogren --piyasa bist` likidite bantlarını (<5, 5-20, 20-50, 50-100, ≥100 mn) 2 günlük sonuçlarla ölçer. 20-50 ya da 50-100 mn bandı (n ≥ 30) tabandan kötü getiri ve daha çok düşüş gösterirse eşik otomatik yükselir (tavan 100 mn ₺, taban 20 mn ₺); `veri.json` → `likidite.min` (mn ₺) alanına yazılır, `bist` komutu bunu okur. Eşik değişince `learning` listesine madde ekle.
- Elle ayar: `rules.json` içine `"likidite": {"min": 2e7, "iyi": 1e8, "katilim": 0.01}` (₺) yazılırsa üstüne alınır; öğrenilmiş eşik tabanın altına inemez.

## §10 İsabet oranı tanımı — 16.11 kullanıcı kararı
Genel isabet = (hedefe ulaşan "Başarılı" + "Kâr korundu") / sonuçlanan (Başarılı, Kâr korundu, Stop, Başarısız). "Kâr korundu" para kazanılarak kapandığı için başarı sayılır. "Erken kapandı" paya ve paydaya girmez. learning maddeleri, özetler ve aktarım dosyaları isabeti bu tanımla yazar; "Tuttu · +%5" sayacı yalnızca hedefe ulaşanları gösterir (ikisi ayrı raporlanır). Terminal bu tanıma göre güncellendi (16.11: 115 / 225 = %51,1).

## §11 Günlük seyir — 16.11 kullanıcı kararı
`kasa` komutu `kasa.gunluk` listesine her günün son toplam değerini (`{"gun":"13.11","kapanis":103671.99}`) yazar; bugün için kapanış her çalışmada güncellenir. `kasa.ozet` içine `gun_oncesi`, `gun_oncesi_tarih`, `gun_kar_tl`, `gun_yuzde` eklenir (günlük değişim = şimdiki toplam − önceki günün kapanışı). Terminal "Günlük değişim" kartını ve son günlerin şeridini bundan çizer; `gunluk` anahtarı silinmemeli.

## §12 İsabet — erken kapanan (16.11 kullanıcı kararı)
§10 tanımına ek: "Erken kapandı" seçimler artık sonuçlanan sayılır. Kapanış anında kârdaysa (`degisim` > 0) başarı, zarardaysa başarısız (negatif) sayılır; `degisim` boşsa (fiyat alınamadı) hariç tutulur. İsabet = (Başarılı + Kâr korundu + kârla Erken kapandı) / (Başarılı, Kâr korundu, Stop, Başarısız, değişimi olan Erken kapandı).

## §13 Denetim kuralları — 16.11 kullanıcı kararı (en az kayıp, en hızlı ve en çok yükselen)
- Kasa alım filtresi (deneme): ilk kez seçilen (geçmişte hiç seçilmemiş) hisse 10:00-11:59 arasında portföye alınmaz (canlı veri: isabet %40, stop %52, n=52). Tekrar seçilen hisseler aynı taramada önce alınır (12:00-15:59 isabet %76, n=37). Atlanan hisse kasa "son hareketler" listesinde nedeniyle görünür. 30 yeni sonuç birikince yeniden değerlendirilir.
- Gap riski: stop saatlik kapanışta uygulandığı için gerçekleşen stop ortalama -%3,6 (plan -%2,6); 10:00 açılışında tetiklenen stoplar -%4,2. Çıkış kuralı geriye dönük testte neredeyse en iyi çıktı; kayıp azaltma girişten gelir (yukarıdaki filtre, Derin/Orta likidite, tekrar seçim önceliği).
- `adaylar`: karar.json'da KAP/haber kararı olmayan eşik üstü aday artık sessiz atlanmaz; "UYARI" basılır ve veri.json `son_tarama.karar_eksik` alanına yazılır. Önce karar.json tamamlanıp komut yeniden çalıştırılmalıdır.
- `learning[].no` her zaman sayıdır (kasa komutu düzeltir).
- Laboratuvar modeli `ileri_test` oranı stopsuz +%5 değme oranıdır; canlı isabetle aynı ölçü değildir. `kasa` komutu `lab_ozellik.model.canli_kiyas` alanına canlı isabeti yazar; kararlar canlı sonuca göre verilir.
- ABD modülü canlıda zarar ediyor ve fiyatları bayat: yalnızca laboratuvar olarak çalışır, kasaya girmez.

## §14 Vade sonu düzeltmesi — 16.11 denetimi
- BIST vade günü seans kapanışı 18:00'dir; 18:05'ten sonra süre dolmuş sayılır, böylece vade günü 18:16 taraması "Başarısız" (süre doldu) kayıtlarını aynı gün sonuçlandırır. Önceden eşik 19:19 idi ve sonuçlanma ertesi sabahki taramaya kalıyor, çıkış fiyatı ertesi sabahın fiyatı oluyordu.
- Sonuç kararı yalnızca vade gününün 18:00 kapanışına kadar olan mumlarla verilir; ertesi sabahki taramada açılan mumlar hedef/stop kararına katılmaz (ABD kuralı değişmedi).
- Kasa süre dolumunda çıkışı vade günü kapanış fiyatından yazar (`kapanis` = bitiş günü 18:00).
- `adaylar` komutu tarama sonrası başka çalışmada takibe alınmış hisseyi (ACIK0 koruması) tekrar seçmez.

## §15 Özellik laboratuvarı (her grafik taramasından sonra) — 16.11 gecesi
- `python3 -I radar.py ozlab --veri veri.json --girdi cikti/bist.json` BIST evrenindeki hisselerin 2 yıllık günlük grafiğinde 24 özelliği (ADX, Supertrend, tavan, boşluklu açılış, hacim, RSI vb.) ölçer: 2 işlem günü içinde +%5'e ulaşma ve %3 altında kapanma (stop) oranı, tabana (tüm örneklerin +%5 oranı) göre fark. Yaklaşık 100 sn sürer; 12 paralel Yahoo isteği kullanır.
- `adaylar --piyasa bist --girdi ...` komutu gözlem/öğren adımlarından sonra bunu OTOMATİK çalıştırır; ayrıca çalıştırmaya gerek yoktur. Çıktıdaki `ÖZLAB:` satırını özette belirt. Hata verirse `UYARI: özellik laboratuvarı başarısız` yazar, tarama sonucu etkilenmez.
- Sonuç `veri.json → lab_ozellik` içine yazılır: `ozellikler[]` (oran, stop, fark, ornek, durum), `taban`, `ornek`, `tur{tur, zaman, sure_sn, grafik, gun, sayac, bulgular}`. Terminalde "Özellik laboratuvarı" kartları bu alandan okunur; `canli/lab` db belgesi varsa ve daha yeniyse o gösterilir.
- Durum kuralı: `kullaniliyor` yalnızca kural ağırlığında gerçekten kullanılan özelliklerdir; yeni özellik otomatik ağırlık kazanmaz (§5: n ≥ 30, kaldıraç ≥ 1,3 ve 3 farklı günde aynı yön). Fark ≥ +10 puan ve n ≥ 300 olanlar "Ağırlığa aday" olarak bulgulara yazılır. n < 100 "az örnek", fark ≤ -4 puan "elendi".
- 1 saatlik/4 saatlik grafikler bu turda taranmaz (günlük grafik 2 yıl). OBV (1S) ve "yakın destek" özellikleri önceki turdan korunur.
- Yayında `veri.json` mutlaka dahil edilir (zaten her yayında dahil).
- BİRİKİM (16.11 gecesi): `lab_ozellik.birikim` sayaçları (grafik, örnek, özellik, tur; taban: tur 18, 1.869 grafik, 287.785 örnek, 497 özellik) her turda ÜSTÜNE eklenir, sıfırlanmaz. Aynı gün-hisse örneği ikinci kez sayılmaz (özellik başına son işlenen gün tutulur), bu yüzden örnek sayısı yalnızca yeni işlem günü geldikçe artar; grafik sayısı her taramada +tarananHisse artar.
- Her turda havuzdan (`OZ_SIRA`, 32 formasyon: yutan mum, çekiç, 20 gün kırılım, 52H zirve, EMA9/20 kesişim, RSI dönüş, Bollinger, EMA200, MACD, sıkışma, iç mum, RSI/hacim/ATR/ardışık gün varyasyonları) sıradaki 3 yeni formasyon etkinleştirilir ve tüm 2 yıllık geçmişte geriye dönük ölçülür. Havuz bitince yeni formasyon eklemek için `_ek(ad, açıklama, fn)` satırı eklenir. Terminal kartları: Test edilen grafik (toplam, bu tur +N), Örnek (toplam, bu tur +N), Ölçülen özellik (toplam, +3 yeni formasyon).

## §16 Kalite kapısı (öğrenilmiş sıralama modeli) — 17.11 gecesi
- Amaç: takipteki hisse sayısını "her taramada 10" yerine yalnızca gerçekten güçlü adaylarla sınırlamak (0-5 arası). Kullanıcı kuralı: sayı öğrendikçe azalmalı, hata azalmalı.
- `motor/model.json` (~315 KB) çalışma klasörüne `model.json` adıyla indirilir. `adaylar --piyasa bist` komutu eşik üstü havuzdaki her hisse için 2 yıllık günlük grafiği çeker, özellik laboratuvarındaki aynı özellik bayrakları + 9 sayısal özellikten (gün değişimi, göreli hacim, boşluk, gün içi konum, 5/20 günlük getiri, 52H zirveye uzaklık, aralık, ciro, piyasa genişliği) model skoru hesaplar (saf Python değerlendirici `_agac_tahmin`, ek paket gerekmez). Skor = 2 işlem günü için beklenen net puan (+%5 hedef = +5, stop = −3).
- Seçim: §16.1'deki öğrenilmiş kural (evren içi sıralama kademesi + günlük sayı + radar filtreleri). `veri.json → kalite_kapisi` o taramadaki evren sayısı, öğrenilen sınırlar ve en iyi 15 skoru tutar; her pick ve history kaydında `model` alanı vardır (sonradan ölçmek için). `model.json` yoksa eski davranış sürer ve bu durum özette belirtilmelidir.
- Doğrulama (ileri doğru / walk-forward, 2025-12 → 2026-11, tavan dışı ve ciro ≥ 20 mn ₺): günün en iyi 3 skoru için +%5 oranı %52, stop %31 (taban %24 / %29); dört ayrı dönemde de hedef %48-55. Mevcut kural sisteminin gerçekleşen kayıtları: hedef %47, stop %41. Yani kapı hata oranını düşürür ama sıfırlamaz; rakamlar gün kapanış verisiyle ölçülmüştür, saat içi taramada fark olabilir — gerçek sonuçlar `history[].model` ile izlenir.
- Sürekli öğrenme: `python3 -I egit.py radar.py arsiv/gozlem_bist_<tarih>.json model.json` (numpy + scikit-learn gerekir: `pip install numpy scikit-learn --break-system-packages`; ~3-4 dk). Her Cuma 18:16 çalışmasında (ya da haftada bir) yeniden eğitilir ve motor/model.json olarak yayınlanır; eğitim çıktısındaki top-3 hedef/stop oranları `model.json → dogrulama` içinde saklanır ve learning listesine 1 madde yazılır. Yeni formasyonlar (§15 havuzu) etkinleştikçe eğitime kendiliğinden girer (egit.py tüm OZ_SIRA'yı kullanır).
- Eşik ayarı (OTOMATİK, 17.11): `adaylar` her çalışmada `_kk_esik_gozden` ile `history[].model` kayıtlarını gözden geçirir; elle müdahale gerekmez. Koşullar: sonuçlanmış ve model skorlu en az 20 kayıt; son gözden geçirmeden en az 5 yeni sonuç. Aday eşikler skor dağılımının %50 ve %25 kesimidir; bir eşik ancak (a) üstünde en az 15 kayıt kalıyorsa, (b) isabet tüm kayıtlardan en az 5 puan iyiyse, (c) stop oranı daha yüksek değilse, (d) ortalama getiri en az 0,4 puan iyiyse konur (önce yüksek, sonra düşük aday denenir). Kanıt yoksa eşik kaldırılır (None). Eşik varsa model skoru eşiğin altındaki hisse seçilmez ("model eşiği" olarak elenenlere yazılır). Sonuç `veri.json → kalite_kapisi_esik` (esik, n, tum, ustu, dilimler, gerekce, onceki, guncelleme) ve çıktıda "KK EŞİK:" satırı olarak görünür; özete yazılır. Kademe yüzdesi ve günlük sayı (kademe_yuzde, gunluk_n) hâlâ haftalık/saatlik eğitimden gelir.

### §16.1 Laboratuvarın amacı ve sadeleştirme kuralları (17.11)
- AMAÇ: grafiklerin ne zaman ve nasıl yükseldiğini (ve nerede stop olduğunu) öğrenmek; öğrenileni ileri doğru testten geçirmek; yalnızca testi geçen kurallara uyan hisseleri takibe/portföye almak. Hedef: hızlı VE yükseliş ihtimali en yüksek grafikler; çok hisse takip etmek değil, az ve seçilmiş hisse. Kripto ve ABD yalnızca bilgi birikimi (grafik öğrenme) içindir, seçimi doğrudan belirlemez.
- Takip ≠ portföy (17.11 düzeltilmiş kural): takip = alım kararı verilmemiş ama alım için izlenen adaylardır; portföy = sanal olarak alınmış hisselerdir (en fazla 10); iki küme ayrıdır. Seçilen hisse boş portföy yeri ve nakit varsa (seans 10:00-18:00, sığ değil, ilk kez seçilen için 12:00 sonrası) alınır ve portföye geçer; yer yoksa takipte bekler. Her kasa çalışmasında takipteki en iyi aday, portföydeki en düşük model skorlu hisseden en az 0,25 puan iyiyse portföydeki hisse satılır (tür: değiştirildi, çalışma başına en fazla 2) ve aday alınır. Takip sayısına elle üst sınır YOKTUR; sayıyı model belirler: `adaylar` tüm evreni (alınabilir hisseler: günlük ciro ≥ 20 mn ₺, gün değişimi < %9) model skoruna göre sıralar; yalnızca evrenin en iyi %`kademe_yuzde`'sinde olan ve radar filtrelerini (puan eşiği, KAP kararı, derinlik, ilk kez seçilen hisse 10:00-11:59 kuralı) geçen hisseler seçilir; bir günde toplam `gunluk_n` seçimi aşılmaz. Bu iki sayı egit.py'nin ileri doğru testinden gelir (EV'si en iyinin %95'inden düşük olmayan en geniş kademe/sayı), elle verilmez. Tek sabit sınır sanal portföyün üst sınırıdır (PORTFOY_MAX=10, kullanıcı kuralı): portföyde yer yoksa yeni seçim yapılmaz. Eski 38 kayıt vadesi (19.11) dolana kadar sonuçlanır.
- İzleme listesi terminalden ve motordan kaldırıldı (V["izleme"] BIST için boş yazılır); yalnızca kuralları geçen seçimler görünür.
- STOP (17.11): ileri doğru simülasyon (günlük kapanış bazlı, günün en iyi 3 skoru, ~1.100 örnek): sabit stop %1,5 → hedef %48,8 / stop %42,0 / işlem başı ort. +%1,93; %2 → %49,5 / %39,6 / +1,79; %2,5 → %49,7 / %37,2 / +1,63; %3 → %50,8 / %34,4 / +1,55. Dar stop hedef oranını neredeyse hiç düşürmüyor, stop sıklığını artırıyor ama her kayıp küçüldüğü için ortalama getiri artıyor. Kazananların %77'si %3 içinde kalıyor (kantil model stopu %3'e yakın çıktı: kazananlar yeterince derin geri çekiliyor). Karar: STOP_TAVAN %3 → %2,5 (radar.py). Sonraki adım: canlı kayıtlarda (history, model alanlı) 30 kapanmış işlemde stop oranı ve ortalama getiri izlenir; %2,5 ≥ %3 ise %2'ye inilir. Alt sınır %1. Stopa değip toparlanan (stop sonrası hedefe giden) kayıt oranı da izlenir; bu oran > %25 ise daraltma durur. NOT: simülasyon günlük kapanışa dayanır; gerçek kural 1 saatlik kapanıştır, canlı sonuç belirleyicidir.
- Model eğitimi HER TARAMADA yapılır (17.11): sıra `bist` → paket/haber/karar → `python3 -I egit.py radar.py cikti/bist.json model_yeni.json model.json` (~2,5 dk; önce `pip install numpy scikit-learn --break-system-packages`) → yeni model testi geçtiyse (en iyi 3'te hedef ≥ %45, stop ≤ %38, EV ≥ 1,0 ve eski modelin EV'sinin 0,25'ten fazla altında değil) `model_yeni.json` → `model.json` olarak alınır, geçemezse eski model kalır → `adaylar`. Çıktıdaki "MODEL:" satırı özette belirtilir. Günlük grafik önbelleği (gunluk_onbellek.pkl, 45 dk) egit, adaylar ve ÖZLAB arasında paylaşılır; 600 grafik bir kez indirilir. Güncel model.json terminal artifact'ının `motor/model.json` dosyasındadır (görevler oradan indirir ve her yayında güncel halini terminal yayınına ekler); Radar Motoru artifact'ındaki kopya yalnızca ilk tohumdur. Not: günlük mum modeline günde yalnızca bir yeni gün eklenir; saatlik eğitim bu yüzden küçük farklar üretir, asıl katkı test kapısıyla modelin sürekli doğrulanmasıdır.

## 18.11 Yayın sonrası sayfa denetimi ve bölüm yenileme (kullanıcı kararı)
- Her saatlik taramada `adaylar` ve `kasa` sonrası, yayından önce: `python3 -I radar.py kripto --veri veri.json`, `python3 -I radar.py sektor`, `python3 -I radar.py endeks --veri veri.json`, `python3 -I radar.py kaydet kripto sektor endeks --veri veri.json`. Böylece kripto, sektör ve endeks bölümlerinin etiketi bayat kalmaz (açık deney varsa endeks, bekleyen projeksiyon varsa sektör projeksiyonu korunur; bunu komut kendi yapar).
- Yayından (push) 2-3 dk sonra: `cp motor/sayfa_kontrol.py.txt /tmp/sk.py; python3 -I /tmp/sk.py --yerel /tmp/w/veri.json`. Betik GitHub Pages üzerindeki veri.json, index.html ve canli/durum.json'u buluttan okur; "SORUN:" satırı varsa nedenini gider (bayat bölüm etiketi → ilgili komutu çalıştırıp yeniden yayınla; Pages gecikmesi → 3 dk bekleyip bir kez daha dene; eksik anahtar → önceki commit'teki veri.json ile karşılaştır, kayıp anahtarı geri koy), yeniden yayınla ve denetimi tekrarla (en fazla 2 tur). Hâlâ sorun varsa PushNotification ile bildir.

## 18.11 Günlük Hareket Laboratuvarı (sürekli öğrenme, kullanıcı kararı)
- Amaç: lab her gün önceki günün tüm hareketlerini endekse göre ölçer, yükselenlerin ve düşenlerin SABAHKİ özelliklerini karşılaştırır, kanıtı yeterli örüntüleri bonus ya da eleme kuralı ADAYI olarak önerir. Çalışan sistemler (radar puanı, hacim, uygun işareti, onaylı kurallar) her gün aynı yöntemle puanlanır. Öğrenme bitmez.
- Komut (her saatlik taramada `kasa`/bölüm yenilemeden sonra, yayından önce; gece lab görevinde de): `cp $REPO/motor/hareket.py.txt /tmp/w/hareket.py; mkdir -p /tmp/w/lab; cp $REPO/lab/hareket.json /tmp/w/lab/hareket.json (yoksa boş geç); cd /tmp/w; python3 -I hareket.py --motor radar.py --arsiv arsiv --veri veri.json --kayit lab/hareket.json --rules rules.json` → veri.json `hareket_lab` + lab/hareket.json. Yayında lab/hareket.json da depoya kopyalanır. Çıktıdaki "HAREKET:" ve "SİSTEM" satırları özette belirtilir.
- Ölçü: sabah taraması (<= 11:30) fiyatı -> gün sonu taraması (>= 17:45) fiyatı; hisse getirisi eksi BIST 100 getirisi (aynı saat aralığı). Yükselen: endeksten >= +3 puan fazla; düşen: <= -3 puan. Sabah |gün değişimi| >= %9,5 olan hisseler (kilitli) dışlanır. Özellikler radar.py `_ozellikler` ile aynıdır (hacim, puan, gün içi değişim, RSI, zirveye uzaklık, sektör ...). Ham kapanış değişimi değil, sabahtan sonraki kısım ölçülür: 17.11 ilk analizinde sabah öncesi hareket dahildi, bu ölçüde etkiler çok daha küçüktür (dürüst ölçü budur).
- Kanıt kapıları (lab disiplini): asgari 6 tamamlanmış gün; keşif günlerinde tek özellik >= 60, çift >= 40 örnek; oran farkı z >= 3; endekse göre ortalama fark >= 0,6 puan; günlerin >= %70'i aynı yön; ARDINDAN ileri test (son 2 gün ya da %25'i keşifte kullanılmaz, >= 30 örnek, etki keşfin >= %40'ı ve aynı yön). Durumlar: Veri biriktiriliyor, Kanıt yok, İleri test bekliyor, Onay bekliyor, Elendi (ileri test).
- Seçime etki (yalnızca onayla): "Onay bekliyor" örüntüyü kullanıcı onaylarsa rules.json `hareket_kurallari` listesine {id, yon: "bonus"|"eleme", aciklama, ozellik: [özellik etiketleri], agirlik (bonus için, varsayılan 0,05), onay_tarihi, kanit} olarak eklenir. `adaylar` bunları uygular: bonus yalnız SIRALAMAYI etkiler (kapıyı gevşetmez), eleme adayı dışarıda bırakır (kapıyı yalnız sıkılaştırır). Onaysız hiçbir örüntü seçime girmez. Onaylı kuralların başarısı "Çalışan sistemler" tablosunda sürekli ölçülür; ileri test bozulursa kullanıcıya bildirilir.
- Nedenler: gece lab görevi (21:41) dünün en çok yükselen/düşen 10+10 hissesi için `radar.py haber --piyasa bist KOD...` çıktısını okuyup hareket_neden.json {kod: {tarih, neden}} yazar ("olumlu: ...", "olumsuz: ...", "haber yok, spekülatif/teknik"); neden uydurulmaz. hareket.py bunu `dun` tablosuna işler.

## 19.11 Gölge deney (kullanıcı kararı)
`adaylar --piyasa bist` her taramada kalite kapısı modelinin evren içi ilk kademesini (şu an ilk %1) radar puanı ve uygun filtresi OLMADAN `veri.json -> golge.kayitlar` içine sanal kayıt olarak ekler (yasaklı hisse hariç; günde en çok 3 yeni, en çok 6 açık kayıt; stop/hedef/vade gerçek seçimlerle aynı). `kontrol` komutu bu kayıtları da sonuçlandırır. `golge.ozet` gölge ve gerçek (radar filtreli) seçimlerin isabet ve stop oranlarını yan yana verir. Seçime, kasaya ve öğrenme aşaması sayacına GİRMEZ; yalnızca radar filtresinin değer katıp katmadığını ölçer. Karar için en az 30 sonuçlanan gölge kayıt beklenir.
