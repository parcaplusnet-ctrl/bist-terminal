# Radar bulut tarama motoru · çalışma kılavuzu

Terminal: https://claude.ai/artifact/1VwQW177PfmVReSpzh5iAE (Borsa Tarama Terminali). Merkez sahip hesapta.
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

## 6. Arka plan gözlem arşivi (09.11'den itibaren, her çalışmada)
Amaç: yalnızca adayları değil TÜM hisseleri izleyip yükselen/düşen hisselerin neden hareket ettiğini öğrenmek.
1. Hazırlıkta arşivi indir: `Artifact` list scope "files" → `arsiv/gozlem_<piyasa>_YYYY-MM-DD.json` dosyalarından bugün ve önceki 3 işlem gününe ait olanları `read` paths ile çalışma klasörüne indir (yol: `arsiv/...`).
2. Her BIST taramasından sonra: `python3 -I radar.py gozlem --girdi cikti/bist.json --piyasa bist` (18:16'da ABD için de `--girdi cikti/abd.json --piyasa abd`).
3. Ardından: `python3 -I radar.py ogren --veri veri.json --piyasa bist` (ABD: `--piyasa abd`). Gözlemler 2 işlem günü dolunca sonraki fiyatlarla eşleştirilir; veri.json `gozlem_lab.<piyasa>` alanında taban oran, özellik tablosu (+%5 / -%3 oranı, kaldıraç), en çok yükselen/düşen 10'ar hisse ve önceki özellikleri birikir.
4. Yeni gözlem işlendiyse, çıktıdaki "Hareket kodları" için `haber --piyasa <piyasa>` çalıştır; hareketi açıklayan haber/KAP varsa (bilanço, sipariş, sermaye artırımı, hedef fiyat vb.) learning maddesine "neden" olarak yaz. Haber yoksa hareket teknik/piyasa kaynaklı sayılır ve öne çıkan özellikler not edilir.
5. Kural ağırlığına geçiş: bir özellik ancak n ≥ 30, kaldıraç ≥ 1,3 (veya ≤ 0,7) ve en az 3 farklı günde aynı yönde ise küçük adımla (±0,25) ağırlığa yansıtılır.
6. Yayında bugünkü arşiv dosyasını da gönder: files {"veri.json": ..., "arsiv/gozlem_bist_YYYY-MM-DD.json": ...}. 30 işlem gününden eski arşiv dosyaları `null` ile kaldırılır (istatistik veri.json'da birikmiş olarak kalır).

## 7. Takip güncellemesi (15 dakikada bir, seans içinde; 09.11 kullanıcı talimatı)
Saatlik tarama :16'da çalışır; arada :01, :31 ve :46'da yalnızca açık kayıtlar güncellenir. Yeni tarama ve aday seçimi YOK.
1. Hazırlık §0 (rules gerekmez). Saatlik tarama sürüyorsa (canli/durum durum="taraniyor" ve `at` 30 dk içinde) hiçbir şey yapma ve bitir.
2. `python3 -I radar.py kontrol --veri veri.json` → açık BIST/ABD kayıtlarının anlık değişimi, en yüksek/en düşük ve sonuçları (hedef/stop/süre) güncellenir.
3. Değişen kayıt varsa canli/durum'a (get → if_version ile update) hedefe_ulasan / stop_olan / suresi_dolan yaz (sesli uyarı).
4. `Artifact` publish: file_path = okunan index.html, files {"veri.json": ...}; yalnızca veri.json değişir. Çakışma olursa yeniden oku, kontrolü yeni sürüm üzerinde tekrarla ve yayınla.
5. Aktarım dosyası ve uzun özet yok; yalnızca sonuçlanan kayıt varsa 1-2 cümle özet (stop olanlar ve süresi dolanlar ayrı). Yatırım tavsiyesi değildir.
