# DEVİR: Terminali GitHub Pages'e taşı + motor güncellemesi (merkez/sahip hesap)

Bu oturumu açan kullanıcı Bekir. Merkez terminal: https://claude.ai/artifact/Q8A2s6Dk83tHhzZEuzgNrM
GitHub deposu (herkese açık, Pages açık, main/root): https://github.com/parcaplusnet-ctrl/bist-terminal
Site adresi: https://parcaplusnet-ctrl.github.io/bist-terminal/
Depo bu oturuma KAYNAK olarak eklenmiş olmalı (yoksa push reddedilir). Erişim anahtarı (fine-grained, yalnız bu depo, Contents RW) kullanıcıdan istenir, dosyaya yazılmaz.

## Sabit kurallar
Duygusuz/profesyonel dil; ULAK yok (hacim kullanılır); sistem kendi öğrenir; stop payı %3 tavan; sektöre göre öğrenme; KAP haberleri hafızada; canlı akış pk+tk; stop/süre dolumunda ses; uzay çağı/laboratuvar teması; cevap sonu "Yatırım tavsiyesi değildir".

## Bu hesaba işlenecek kural değişiklikleri (motor/radar.py + motor/MOTOR.md içinde hazır)
1. Vade = 2 işlem günü (hafta sonu + BIST/ABD tatilleri hariç; bugünün kalanı bonus).
2. STOP yalnız KAPANMIŞ 1 saatlik mum stopun altında kapanırsa sayılır; fitil sayılmaz (stop_igne notu). BIST saatlik mumlar TradingView hizalı: 10-11 ... 17-18:10; 10:16 taramasında stop kararı yok (ilk karar 11:00 mumu kapanınca). Mumlar 15 dk Yahoo verisinden `bist_saatlik()` ile üretilir.
3. Süresi dolanlar ayrıca duyurulur (ayrı bölüm + amber kayan bant + ses). Metin: "Takip Süresi Doldu".
4. Hedefe ulaşıp yeniden seçilen hisse = "TREND DEVAM".
5. Takipteki hisseler 15 dakikada bir güncellenir (7. bölüm). Tüm takip kartları gösterilir; izleme listesi en az 10'a tamamlanır.
6. Kartlar: hedefe yakın üstte, stopa yakın altta ve yanıp söner; 5'li ızgara.
7. Kod büyük harf; ticker'da BIST etiketi yok (ABD etiketi kalır); "Gördüm" düğmesi yok.

Merkez terminalde yalnız index.html + veri.json var; motor dosyaları yok. Önce motor/ dosyalarını çalışma alanına koy, kendi veri.json şemanla uyumunu `radar.py kontrol` ile dene (yeni sonuç türleri: "Kâr korundu", "Erken kapandı" mevcut şemada var).

## Taşıma adımları
1. Depoyu klonla. Merkez sayfanın HTML'ini (Artifact read) bağımsız index.html'e çevir: Claude'a özgü DB/onSnapshot kodunu kaldır, veriyi `fetch('veri.json?t='+Date.now())` ile oku (60 sn'de bir yenile).
2. Canlı fiyat: tek POST ile tüm takip sembolleri: `https://scanner.tradingview.com/{turkey|america|crypto}/scan` (CORS açık, BIST verisi 15 dk gecikmeli). 20-30 sn'de bir; kartlar, ticker, "stopa yakın" uyarısı ve hedef sesi canlı fiyatla güncellenir. Canlı fiyat stopun altındaysa kartta "Stop altı, mum kapanışı bekleniyor" yaz; resmî STOP kararı yalnız bulut kontrolünden gelir. Ses için sayfada tek tık "Sesi aç" düğmesi.
3. Motor yayın adımı: sonuç veri.json'u depoya `git commit && git push` ile gönder (kimlik: `https://x-access-token:$TOKEN@github.com/parcaplusnet-ctrl/bist-terminal.git`). Görev istemlerinde TOKEN yalnız kullanıcıdan alınıp yerleştirilir.
4. Zamanlanmış görevler (create_trigger; asla CronCreate): saatlik :16 tarama + 15 dk takip güncellemesi (3 ayrı görev) aynı kalır; yayın adımı git push olur. Eski Claude artifact yayını bir süre paralel sürebilir.
5. Test: sayfa açılır, veri yüklenir, fiyat 30 sn içinde güncellenir, push sonrası veri.json değişir. Sonuçta site adresini kullanıcıya ver.

## Bilinen eksikler
13.11 16:16 taraması eksik (dogrulama). son_tarama.ulak anahtarı veride duruyor, sayfada gösterilmemeli. Sanal kasa paneli (kasa verisi var) sayfaya eklenecek.
