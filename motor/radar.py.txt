#!/usr/bin/env python3
"""BIST Yükseliş Radarı · bulut tarama motoru (yalnızca standart kütüphane).

Veri: scanner.tradingview.com, news-headlines.tradingview.com, query1/2.finance.yahoo.com
Komutlar (çıktılar --out klasörüne JSON olarak yazılır, varsayılan ./cikti):
  bist      [--rules rules.json] [--veri veri.json]   BIST tam tarama, 1S-4S-G, puan, stop
  abd       [--rules rules.json] [--veri veri.json]   ABD tarama (≥1 mlr $, ≥5 $, ort. hacim ≥500 bin)
  kripto    [--veri veri.json]                        BTC + kripto bağlantılı hisseler, grup sinyali
  endeks    [--veri veri.json]                        BIST 30/50/100 laboratuvar seçimi (2 yüksek, 1 orta, 2 kontrol)
  sektor                                              Sektör rotasyonu BIST + ABD + makro + projeksiyon
  haber     --piyasa bist|abd KOD [KOD...]            Son 30 günün haber/KAP başlıkları
  kontrol   --veri veri.json                          Açık kayıtların sonuçlarını işler (veri.json'u günceller)
  paket     --girdi cikti/bist.json [--n 12] [--etiket "08.11 BIST"]  canlı akış paketleri (her pakette ≥4 hisse)
  kaydet    kripto sektor endeks --veri veri.json        cikti/ sonuçlarını veri.json'a işler (açık deneyler korunur, eskiler arşive)
  adaylar   --girdi cikti/bist.json --karar karar.json --veri veri.json [--piyasa bist|abd]
            karar.json: [{"kod":..,"haber_puan":1|0|-1,"haber":"olumlu: ..."}] → veri.json'a 10 aday, izleme, tarama kaydı
  gozlem    --girdi cikti/bist.json [--piyasa bist|abd] [--arsiv arsiv]   TÜM hisselerin anlık görüntüsünü günlük arşive ekler
  ogren     --veri veri.json [--piyasa bist|abd] [--arsiv arsiv]          arşivi 2 işlem günü sonraki fiyatla eşleştirir →
            veri.json gozlem_lab: özellik bazında +%5 / -%3 oranları, en çok yükselen/düşenlerin önceki özellikleri
Yatırım tavsiyesi değildir.
"""
import json, re, sys, os, time, math, argparse, datetime, urllib.request, urllib.error, statistics

UA = {"User-Agent": "Mozilla/5.0 (radar-motor)", "Content-Type": "application/json", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
IST = datetime.timezone(datetime.timedelta(hours=3))

def simdi():
    return datetime.datetime.now(IST)

def http(url, body=None, deneme=4, bekle=2.0):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(deneme):
        try:
            req = urllib.request.Request(url, data=data, headers=UA, method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < deneme - 1:
                time.sleep(bekle * (i + 1)); continue
            raise
        except Exception:
            if i < deneme - 1:
                time.sleep(bekle * (i + 1)); continue
            raise

def scan(market, body):
    j = http(f"https://scanner.tradingview.com/{market}/scan", body)
    if j.get("error"):
        raise RuntimeError(j["error"])
    return j

def r2(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, 2)

TF = ["|60", "|240", ""]
BASE = ["close", "open", "high", "low", "volume", "RSI", "MACD.macd", "MACD.signal", "EMA20", "EMA50",
        "Recommend.Other", "Recommend.MA", "Recommend.All", "change"]
EXTRA = ["name", "description", "sector", "market_cap_basic", "change_from_open", "relative_volume_10d_calc", "Perf.W",
         "Perf.1M", "High.1M", "Low.1M", "SMA50", "MACD.macd[1]", "MACD.signal[1]", "average_volume_10d_calc", "average_volume_30d_calc"]
COLS = EXTRA + [b + t for t in TF for b in BASE]

def rows(j, cols):
    out = []
    for x in j.get("data", []):
        o = dict(zip(cols, x["d"])); o["_s"] = x["s"]; out.append(o)
    return out

def tick_bist(p):
    for lim, t in ((20, .01), (50, .02), (100, .05), (250, .1), (500, .25), (1000, .5), (2500, 1)):
        if p < lim: return t
    return 2.5

def yuvarla(v, t, yukari=False):
    k = v / t
    k = math.ceil(k - 1e-9) if yukari else math.floor(k + 1e-9)
    return round(k * t, 4)

DEF_W = {"acilistan_beri_yukselis": .5, "asiri_isinma": -2, "bir_saatlik_guc": 1, "dip_taban_kirilimi_hacimli": .5,
         "dipte_macd_donusu": 1, "ema20_gt_ema50_1s_4s": 1, "gun_ici_3_95": 1, "gun_yuksegi_kapanis": .5,
         "hacim_1_5x_yukselis": 1, "hacimli_ilk_tavan": 1, "likit_100mn": .5, "kilitli_tavan_1": .5, "kucuk_sirket": -1,
         "mtf_kriter_basina": .25, "yukselen_dip_yapisi": .5}

# seans içi kümülatif hacim payı (yaklaşık U eğrisi); erken saatte göreli hacmi gün sonu eşdeğerine çevirir
PAY_EGRI = {"bist": [(0, 0), (60, .22), (120, .36), (180, .48), (240, .58), (300, .70), (360, .80), (420, .90), (490, 1)],
            "abd": [(0, 0), (60, .25), (120, .38), (180, .48), (240, .58), (300, .69), (360, .82), (390, 1)]}

# Likidite (derinlik) kuralı — 14.11 kullanıcı kararı: sığ hissede işlem açılmaz, yüklü alım-satım yapılabilmeli.
# ciro = kapanış × 30 günlük ort. hacim (≈ günlük ₺ ciro). min altı: aday olamaz. katilim: bir pozisyon günlük cironun bu payını aşmamalı (kasa büyüdükçe pozisyon kapasiteyle sınırlanır).
LIK = {"min": 20e6, "iyi": 100e6, "katilim": .01}

def derinlik(ciro):
    return "Derin" if ciro >= LIK["iyi"] else "Orta" if ciro >= LIK["min"] else "Sığ"

def hacim_payi(piyasa):
    n = simdi(); bas = (10 * 60) if piyasa == "bist" else (17 * 60 + 30)
    dk = (n.hour * 60 + n.minute - bas) % 1440
    E = PAY_EGRI[piyasa]
    if dk >= E[-1][0]: return 1.0
    for (x0, y0), (x1, y1) in zip(E, E[1:]):
        if x0 <= dk <= x1: return max(.08, y0 + (y1 - y0) * (dk - x0) / (x1 - x0))
    return 1.0

def puanla(o, W, piyasa="bist", esik=7.0, seans_ici=False):
    """Bir hisseyi radar kurallarıyla puanlar. Dönüş: sözlük (pk, tk, stop, sebep, uygun...)"""
    w = lambda k: W.get(k, DEF_W.get(k, 0))
    c = o.get("close")
    if not c: return None
    pk = {"RSI-MACD": 0, "Trend": 0, "Hacim": 0, "Uyum": 0, "Dip": 0, "KAP": 0, "Risk": 0}
    why = []; ch = o.get("change") or 0; rv = o.get("relative_volume_10d_calc") or 0
    if seans_ici: rv = rv / hacim_payi(piyasa)  # gün içi: hacmi saat payına göre gün sonu eşdeğerine çevir
    g = lambda k: o.get(k) if o.get(k) is not None else float("nan")
    mt = 0; yon = {}
    for t in TF:
        n = 0
        if g("close" + t) > g("EMA20" + t): n += 1
        if g("EMA20" + t) > g("EMA50" + t): n += 1
        if g("MACD.macd" + t) > g("MACD.signal" + t): n += 1
        if g("RSI" + t) > 50: n += 1
        mt += n; yon[t] = o.get("Recommend.All" + t) or 0
    pk["Uyum"] = mt * w("mtf_kriter_basina")
    if g("RSI|60") > 55 and g("close|60") > g("EMA20|60") and g("MACD.macd|60") > g("MACD.signal|60"):
        pk["RSI-MACD"] += w("bir_saatlik_guc"); why.append("1 saatlik güçlü")
    asiri = g("RSI") > 75 or g("RSI|60") > 82
    if asiri: pk["RSI-MACD"] += w("asiri_isinma")
    m, s, m1, s1 = g("MACD.macd"), g("MACD.signal"), g("MACD.macd[1]"), g("MACD.signal[1]")
    if m < 0 and m > s and (m1 - s1) < (m - s) and g("RSI") < 55:
        pk["Dip"] += w("dipte_macd_donusu"); why.append("dipte MACD yukarı döndü")
    if c > g("SMA50") and g("Perf.W") > 0 and g("low") > g("Low.1M") * 1.03:
        pk["Dip"] += w("yukselen_dip_yapisi"); why.append("dipler yükseliyor")
    if g("EMA20|60") > g("EMA50|60") and g("EMA20|240") > g("EMA50|240"): pk["Trend"] += w("ema20_gt_ema50_1s_4s")
    if (o.get("change_from_open") or 0) > 0: pk["Trend"] += w("acilistan_beri_yukselis")
    if o.get("high") and c >= o["high"] * .99 and ch > 0: pk["Trend"] += w("gun_yuksegi_kapanis")
    if rv >= 1.5 and ch > 0:
        pk["Hacim"] += w("hacim_1_5x_yukselis"); why.append(f"{str(r2(rv)).replace('.', ',')}x hacimle yükseldi")
    tavan = piyasa == "bist" and ch >= 9.5
    if tavan and rv >= 1.5: pk["Hacim"] += w("hacimli_ilk_tavan"); why.append("hacimli tavan")
    if tavan and o.get("high") and c >= o["high"] * .999 and rv < 1: pk["Hacim"] += w("kilitli_tavan_1"); why.append("düşük hacimli kilitli tavan")
    if 3 <= ch < 9.5: pk["Hacim"] += w("gun_ici_3_95")
    if rv >= 1.5 and ch > 0 and c >= g("High.1M") * .995: pk["Hacim"] += w("dip_taban_kirilimi_hacimli"); why.append("direnci hacimle geçti")
    ciro = (c * (o.get("average_volume_30d_calc") or o.get("average_volume_10d_calc") or 0)) if piyasa == "bist" else None
    if ciro is not None and ciro >= LIK["iyi"]: pk["Hacim"] += w("likit_100mn"); why.append(f"likit (günlük ~{int(ciro / 1e6)} mn ₺)")
    kucuk = 1.5e9 if piyasa == "bist" else 3e8
    if (o.get("market_cap_basic") or 0) < kucuk: pk["Risk"] += w("kucuk_sirket")
    # stop: en yakın dip (1S, 4S, G) %1-%3 arası, yoksa sınırlar
    lows = [v for v in (o.get("low|60"), o.get("low|240"), o.get("low")) if v]
    aday = [v for v in lows if c * .97 <= v <= c * .99]
    if aday:
        st = max(aday) * (0.998 if piyasa == "bist" else 1) - (0 if piyasa == "bist" else .01); sk = "son dibin altında"
    elif [v for v in lows if v < c * .97]:
        st = c * (1 - STOP_TAVAN); sk = f"en fazla %{str(round(STOP_TAVAN * 100, 1)).replace(chr(46), chr(44))} kuralıyla"
    else:
        st = c * .99; sk = "%1 alt sınırı"
    t = tick_bist(c) if piyasa == "bist" else .01
    st = yuvarla(max(st, c * (1 - STOP_TAVAN)), t, yukari=True)
    if st > c * .99: st = yuvarla(c * .99, t)
    puan = round(sum(pk.values()), 2)
    seb = []
    if puan < esik: seb.append(f"puan düşük ({str(puan).replace('.', ',')})")
    if asiri: seb.append("aşırı ısınmış")
    if seans_ici and ch > 4.7: seb.append("gün içi +%4,7 üstünde")
    sig = ciro is not None and ciro < LIK["min"]
    if sig: seb.append(f"sığ hisse: günlük ort. ciro {int(ciro / 1e6)} mn ₺ (eşik {int(LIK['min'] / 1e6)} mn ₺)")
    if not (g("close") > g("EMA20") > g("EMA50")): seb.append("günlük trend aşağı")
    if (yon["|60"] > 0) != (yon["|240"] > 0): seb.append("1S-4S ayrı yön")
    uygun = puan >= esik and not asiri and not (seans_ici and ch > 4.7) and not sig
    tk = {"1S": [r2(o.get(k)) for k in ("Recommend.Other|60", "Recommend.MA|60", "Recommend.All|60")],
          "4S": [r2(o.get(k)) for k in ("Recommend.Other|240", "Recommend.MA|240", "Recommend.All|240")],
          "G": [r2(o.get(k)) for k in ("Recommend.Other", "Recommend.MA", "Recommend.All")]}
    hedef = yuvarla(c * 1.05, t, yukari=True)
    return {"kod": o["name"], "ad": o.get("description"), "sektor": o.get("sector"), "fiyat": c, "ch": r2(ch), "rv": r2(rv),
            "puan": puan, "pk": {k: r2(v) for k, v in pk.items()}, "tk": tk, "mt": mt, "stop": st,
            "stop_yuzde": round(st / c - 1, 4), "stop_neden": sk, "hedef": hedef, "rsi": r2(o.get("RSI")),
            "why": why, "sebep": ", ".join(seb), "uygun": uygun, "mcap": o.get("market_cap_basic"),
            "likit_mn": None if ciro is None else r2(ciro / 1e6), "kapasite_tl": None if ciro is None else int(ciro * LIK["katilim"]),
            "derinlik": None if ciro is None else derinlik(ciro),
            "oz": {"pw": r2(o.get("Perf.W")), "p1m": r2(o.get("Perf.1M")), "cfo": r2(o.get("change_from_open")), "rsi1s": r2(o.get("RSI|60")), "rsi4s": r2(o.get("RSI|240")),
                   "g_trend": int(g("close") > g("EMA20") > g("EMA50")), "asiri": int(bool(asiri)),
                   "h1m": r2(c / o["High.1M"] - 1) if o.get("High.1M") else None, "l1m": r2(c / o["Low.1M"] - 1) if o.get("Low.1M") else None}}

def kurallar(yol, veri=None):
    W, esik = {}, 7.0
    if yol and os.path.exists(yol):
        R = json.load(open(yol)); W, esik = R.get("weights", {}), float(R.get("puan_esigi", 7))
        for k, v in (R.get("likidite") or {}).items():
            if k in LIK: LIK[k] = float(v)
    try:  # öğrenilmiş likidite eşiği (ogren komutu veri.json'a yazar); kullanıcı tabanı 20 mn ₺'nin altına inmez
        if veri and os.path.exists(veri):
            L = (json.load(open(veri)).get("likidite") or {})
            if L.get("min"): LIK["min"] = max(LIK["min"], float(L["min"]) * 1e6)
    except Exception: pass
    return W, esik

def seans_acik(piyasa):
    n = simdi()
    if n.weekday() >= 5: return False
    hm = n.hour * 60 + n.minute
    return (600 <= hm <= 1090) if piyasa == "bist" else (1050 <= hm or hm <= 0)

def acik_kodlar(veri, anahtar="history"):
    if not veri or not os.path.exists(veri): return set()
    V = json.load(open(veri))
    H = V.get(anahtar, []) if anahtar == "history" else V.get("yurtdisi", {}).get("history", [])
    return {h["kod"] for h in H if h.get("sonuc") == "Bekliyor"}

def ozet(S, ek=None):
    hist = {}
    for s in S: hist[str(math.floor(s["puan"]))] = hist.get(str(math.floor(s["puan"])), 0) + 1
    sec = {}
    for s in S:
        k = s["sektor"] or "?"; d = sec.setdefault(k, {"n": 0, "yuk": 0, "rv": 0, "uygun": 0})
        d["n"] += 1; d["yuk"] += s["ch"] > 0; d["rv"] += s["rv"]; d["uygun"] += s["uygun"]
    for d in sec.values(): d["yuk"] = round(d["yuk"] / d["n"], 2); d["rv"] = round(d["rv"] / d["n"], 2)
    o = {"taranan": len(S), "uygun": sum(s["uygun"] for s in S), "asiri": sum("aşırı" in s["sebep"] for s in S),
         "yukselen": round(sum(s["ch"] > 0 for s in S) / max(1, len(S)), 2), "hacim_ort": round(sum(s["rv"] for s in S) / max(1, len(S)), 2),
         "puan_dagilimi": hist, "sektor": sec}
    if ek: o.update(ek)
    return o

def cmd_bist(a):
    W, esik = kurallar(a.rules, a.veri)
    cols = COLS + ["indexes"]
    j = scan("turkey", {"filter": [{"left": "type", "operation": "equal", "right": "stock"}, {"left": "exchange", "operation": "equal", "right": "BIST"}],
                        "markets": ["turkey"], "columns": cols, "sort": {"sortBy": "name", "sortOrder": "asc"}, "range": [0, 1500]})
    R = rows(j, cols); ac = acik_kodlar(a.veri); si = seans_acik("bist"); S = []
    for o in R:
        s = puanla(o, W, "bist", esik, si)
        if not s: continue
        ix = [i.get("proname", "") for i in (o.get("indexes") or [])]
        s["katman"] = "XU030" if "BIST:XU030" in ix else "XU050" if "BIST:XU050" in ix else "XU100" if "BIST:XU100" in ix else None
        s["acik"] = s["kod"] in ac
        S.append(s)
    xu = scan("turkey", {"symbols": {"tickers": ["BIST:XU100"]}, "columns": ["close", "change", "Perf.W"]})["data"][0]["d"]
    out = {"tarih": simdi().strftime("%d.%m %H:%M"), "seans_ici": si, "esik": esik,
           "ozet": ozet(S, {"xu100": {"v": xu[0], "gun": r2(xu[1]), "hafta": r2(xu[2])}}),
           "adaylar": sorted([s for s in S if s["uygun"] and not s["acik"]], key=lambda s: (-s["puan"], -s["rv"]))[:40], "tum": S}
    yaz(a, "bist.json", out); print(f"BIST: {len(S)} hisse, {out['ozet']['uygun']} uygun, ilk: {[x['kod'] for x in out['adaylar'][:10]]}")

ABD_F = [{"left": "type", "operation": "equal", "right": "stock"}, {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
         {"left": "market_cap_basic", "operation": "egreater", "right": 1e9}, {"left": "close", "operation": "egreater", "right": 5},
         {"left": "average_volume_10d_calc", "operation": "egreater", "right": 5e5}, {"left": "is_primary", "operation": "equal", "right": True}]

def cmd_abd(a):
    W, esik = kurallar(a.rules, a.veri)
    j = scan("america", {"filter": ABD_F, "markets": ["america"], "columns": COLS, "sort": {"sortBy": "name", "sortOrder": "asc"}, "range": [0, 4000]})
    R = rows(j, COLS); ac = acik_kodlar(a.veri, "yurtdisi"); si = seans_acik("abd"); S = []
    for o in R:
        s = puanla(o, W, "abd", esik, si)
        if s: s["acik"] = s["kod"] in ac; s["sembol"] = o["_s"]; S.append(s)
    ix = scan("america", {"symbols": {"tickers": ["SP:SPX", "NASDAQ:NDX", "TVC:VIX"]}, "columns": ["close", "change", "Perf.W"]})["data"]
    p = {x["s"]: x["d"] for x in ix}
    pz = {"spx": {"v": p["SP:SPX"][0], "ch": r2(p["SP:SPX"][1]), "w": r2(p["SP:SPX"][2])}, "ndx": {"v": r2(p["NASDAQ:NDX"][0]), "ch": r2(p["NASDAQ:NDX"][1]), "w": r2(p["NASDAQ:NDX"][2])},
          "vix": {"v": p["TVC:VIX"][0], "ch": r2(p["TVC:VIX"][1])}}
    out = {"tarih": simdi().strftime("%d.%m %H:%M"), "seans_ici": si, "esik": esik, "ozet": ozet(S, {"piyasa": pz}),
           "adaylar": sorted([s for s in S if s["uygun"] and not s["acik"]], key=lambda s: (-s["puan"], -s["rv"]))[:40], "tum": S}
    out["ozet"]["piyasa"]["yukselen"] = out["ozet"]["yukselen"]; out["ozet"]["piyasa"]["hacim_ort"] = out["ozet"]["hacim_ort"]
    yaz(a, "abd.json", out); print(f"ABD: {len(S)} hisse, {out['ozet']['uygun']} uygun, ilk: {[x['kod'] for x in out['adaylar'][:10]]}")

KRIPTO_VARS = "MSTR COIN HOOD XYZ GLXY CRCL BLSH MARA RIOT CLSK HUT CIFR IREN WULF BTDR CORZ KEEL HIVE BTBT ASST TSLA GME CME PYPL NVDA APLD BKKT DJT NAKA BMNR".split()

def cmd_kripto(a):
    kodlar = KRIPTO_VARS
    if a.veri and os.path.exists(a.veri):
        V = json.load(open(a.veri)); k = [h["kod"] for h in V.get("kripto", {}).get("hisseler", [])]
        if len(k) >= 25: kodlar = k
    j = scan("america", {"filter": [{"left": "name", "operation": "in_range", "right": kodlar}, {"left": "is_primary", "operation": "equal", "right": True}],
                         "markets": ["america"], "columns": COLS, "range": [0, 200]})
    S = [s for s in (puanla(o, {}, "abd", 7.0) for o in rows(j, COLS)) if s]
    S.sort(key=lambda s: -s["puan"])
    bc = ["close", "change", "RSI", "Recommend.All", "Recommend.All|240", "Recommend.All|60", "Recommend.Other", "Recommend.MA",
          "Recommend.Other|240", "Recommend.MA|240", "Recommend.Other|60", "Recommend.MA|60", "relative_volume_10d_calc"]
    b = dict(zip(bc, scan("crypto", {"symbols": {"tickers": ["BITSTAMP:BTCUSD"]}, "columns": bc})["data"][0]["d"]))
    n = max(1, len(S)); g = sum(s["tk"]["G"][2] or 0 for s in S) / n; g4 = sum(s["tk"]["4S"][2] or 0 for s in S) / n
    btc_sig = ((b["Recommend.All"] or 0) + (b["Recommend.All|240"] or 0)) / 2
    sig = round(((g + g4) / 2 + btc_sig) / 2, 2)
    yon = "yukarı" if sig > .1 else "aşağı" if sig < -.1 else "yatay"
    out = {"tarih": simdi().strftime("%d.%m %H:%M"), "btc": {"fiyat": b["close"], "degisim_gun": round((b["change"] or 0) / 100, 4), "rsi": r2(b["RSI"]),
           "teknik_1s": r2(b["Recommend.All|60"]), "teknik_4s": r2(b["Recommend.All|240"]), "teknik_g": r2(b["Recommend.All"]),
           "tk": {"1S": [r2(b["Recommend.Other|60"]), r2(b["Recommend.MA|60"]), r2(b["Recommend.All|60"])], "4S": [r2(b["Recommend.Other|240"]), r2(b["Recommend.MA|240"]), r2(b["Recommend.All|240"])],
                  "G": [r2(b["Recommend.Other"]), r2(b["Recommend.MA"]), r2(b["Recommend.All"])]}},
           "grup": {"teknik_g": round(g, 2), "teknik_4s": round(g4, 2), "sinyal": sig, "yukselen": sum(s["ch"] > 0 for s in S), "uygun": sum(s["uygun"] for s in S),
                    "ort_puan": round(sum(s["puan"] for s in S) / n, 2), "hisse_sayisi": len(S), "asgari": 25},
           "tahmin": {"yon": yon, "sinyal": sig, "btc_giris": b["close"]}, "hisseler": S}
    yaz(a, "kripto.json", out); print(f"KRİPTO: BTC {b['close']}, {len(S)} hisse, sinyal {sig} → {yon}")

def cmd_endeks(a):
    yol = os.path.join(a.out, "bist.json")
    if not os.path.exists(yol): cmd_bist(a)
    B = json.load(open(yol)); S = [s for s in B["tum"] if s["katman"] and not s["acik"]]
    sec = {}
    for k in ("XU030", "XU050", "XU100"):
        L = sorted([s for s in S if s["katman"] == k], key=lambda s: -s["puan"]); pick = []; used = set()
        def al(arr):
            x = next((s for s in arr if s["sektor"] not in used and s not in pick), None) or next((s for s in arr if s not in pick), None)
            if x: pick.append(x); used.add(x["sektor"])
        al(L); al(L); al(L[int(len(L) * .4):]); al(L[::-1]); al(L[::-1])
        sec[k] = [dict(s, grup=g) for s, g in zip(pick, ["yüksek", "yüksek", "orta", "kontrol", "kontrol"])]
    yaz(a, "endeks.json", {"tarih": B["tarih"], "secim": sec}); print("ENDEKS:", {k: [s["kod"] for s in v] for k, v in sec.items()})

BIST_SEK = ["XBANK", "XSGRT", "XFINK", "XGMYO", "XHOLD", "XAKUR", "XYORT", "XELKT", "XILTM", "XULAS", "XTRZM", "XINSA", "XTCRT", "XSPOR",
            "XGIDA", "XKMYA", "XMANA", "XMESY", "XTEKS", "XKAGT", "XTAST", "XBLSM", "XMADN"]
SEK_AD = {"XMESY": "Metal eşya, makine", "XMADN": "Madencilik", "XBLSM": "Bilişim", "XULAS": "Ulaştırma", "XAKUR": "Aracı kurumlar", "XHOLD": "Holding ve yatırım",
          "XELKT": "Elektrik", "XGIDA": "Gıda, içecek", "XTRZM": "Turizm", "XTAST": "Taş, toprak", "XYORT": "Yatırım ortaklıkları", "XMANA": "Ana metal", "XBANK": "Banka",
          "XSPOR": "Spor", "XTEKS": "Tekstil, deri", "XSGRT": "Sigorta", "XTCRT": "Ticaret", "XFINK": "Finansal kiralama, faktoring", "XGMYO": "GYO",
          "XKMYA": "Kimya, petrol, plastik", "XKAGT": "Orman, kağıt, basım", "XINSA": "İnşaat", "XILTM": "İletişim"}
US_AD = {"Electronic Technology": "Elektronik teknoloji", "Communications": "İletişim", "Non-Energy Minerals": "Enerji dışı madenler", "Retail Trade": "Perakende",
         "Consumer Services": "Tüketici hizmetleri", "Producer Manufacturing": "Üretici imalat", "Health Technology": "Sağlık teknolojisi",
         "Distribution Services": "Dağıtım hizmetleri", "Utilities": "Kamu hizmetleri", "Process Industries": "Proses endüstrisi",
         "Consumer Non-Durables": "Dayanıksız tüketim", "Commercial Services": "Ticari hizmetler", "Health Services": "Sağlık hizmetleri",
         "Industrial Services": "Endüstriyel hizmetler", "Miscellaneous": "Diğer", "Finance": "Finans", "Transportation": "Ulaştırma",
         "Technology Services": "Teknoloji hizmetleri", "Consumer Durables": "Dayanıklı tüketim", "Energy Minerals": "Enerji madenleri"}
SC = ["name", "close", "change", "volume", "average_volume_10d_calc", "Perf.W", "Perf.1M", "Perf.3M", "Volatility.W", "market_cap_basic"]

def topla(R, key, kiyas, adlar):
    G = {}; TV = TA = 0
    for o in R:
        if not o.get("close") or not o.get("market_cap_basic"): continue
        TV += o["close"] * (o.get("volume") or 0); TA += o["close"] * (o.get("average_volume_10d_calc") or 0)
        k = o.get(key)
        if k: G.setdefault(k, []).append(o)
    out = []
    for k, A in G.items():
        if len(A) < 4: continue
        cw = sum(o["market_cap_basic"] for o in A); w = lambda f: sum((o.get(f) or 0) * o["market_cap_basic"] for o in A) / cw
        d, W_, M = w("change"), w("Perf.W"), w("Perf.1M")
        val = sum(o["close"] * (o.get("volume") or 0) for o in A); av = sum(o["close"] * (o.get("average_volume_10d_calc") or 0) for o in A)
        net = sum(o["close"] * (o.get("volume") or 0) * (1 if (o.get("change") or 0) > 0 else -1 if (o.get("change") or 0) < 0 else 0) for o in A) / (val or 1)
        sg = 1 if d >= 0 else -1; uy = sum(1 for o in A if ((o.get("change") or 0) > 0) == (sg > 0)) / len(A)
        chs = [o.get("change") or 0 for o in A]; rs = M - kiyas["ay"]; mom = (W_ - kiyas["hafta"]) - rs / 4.3
        q = ("Lider" if mom >= 0 else "Zayıflayan") if rs >= 0 else ("Toparlanan" if mom >= 0 else "Geride")
        out.append({"kod": k.replace(" ", ""), "ad": adlar.get(k, k), "n": len(A), "gun": r2(d), "hafta": r2(W_), "ay": r2(M), "ay3": r2(w("Perf.3M")), "rs": r2(rs), "ivme": r2(mom),
                    "kadran": q, "hacim_yog": r2(val / (av or 1)), "pay": r2(val / TV * 100), "kayma": r2((val / TV - av / TA) * 100), "net_akis": r2(net),
                    "uyum": r2(uy), "dagilim": r2(statistics.pstdev(chs)), "oynaklik": r2(w("Volatility.W"))})
    def z(f):
        xs = [o[f] for o in out]; m = sum(xs) / len(xs); s = statistics.pstdev(xs) or 1; return lambda o: (o[f] - m) / s
    zm, zk, zn, zu = z("ivme"), z("kayma"), z("net_akis"), z("uyum")
    for o in out: o["proj"] = r2(zm(o) + zk(o) + zn(o) * .5 + zu(o) * .5)
    return sorted(out, key=lambda o: -o["proj"])

def projeksiyon(arr, mk, tarih, kontrol):
    good = [s for s in arr if s["ivme"] > 0 and s["net_akis"] > 0][:3]
    early = [s for s in arr if s["kadran"] == "Geride" and s["kayma"] > 1][:1]
    weak = [s for s in sorted(arr, key=lambda s: s["proj"]) if s["ivme"] < 0][:3]
    r = []
    for t, L in (("güçlü", good), ("erken sinyal", early), ("zayıf", weak)):
        for s in L:
            r.append({"piyasa": mk, "kod": s["kod"], "ad": s["ad"], "tur": t, "kadran": s["kadran"], "skor": s["proj"], "beklenti": "endeksten kötü" if t == "zayıf" else "endeksten iyi",
                      "tarama": tarih, "kontrol": kontrol, "sonuc": "Bekliyor", "gerceklesen": None, "baslangic_hafta": s["hafta"]})
    return r

def cuma_sonra():
    n = simdi(); d = (4 - n.weekday()) % 7 or 7
    return (n + datetime.timedelta(days=d)).strftime("%d.%m") + " kapanış"

def cmd_sektor(a):
    j = scan("turkey", {"filter": [{"left": "type", "operation": "equal", "right": "stock"}, {"left": "exchange", "operation": "equal", "right": "BIST"}],
                        "markets": ["turkey"], "columns": SC + ["indexes"], "range": [0, 1500]})
    R = rows(j, SC + ["indexes"])
    for o in R:
        ix = [i.get("proname", "") for i in (o.get("indexes") or [])]; o["sec"] = next((s for s in BIST_SEK if "BIST:" + s in ix), None)
    k = scan("turkey", {"symbols": {"tickers": ["BIST:XUTUM"]}, "columns": ["change", "Perf.W", "Perf.1M"]})["data"][0]["d"]
    kb = {"ad": "BIST Tüm", "gun": r2(k[0]), "hafta": r2(k[1]), "ay": r2(k[2])}
    ju = scan("america", {"filter": ABD_F, "markets": ["america"], "columns": SC + ["sector"], "range": [0, 4000]}); RU = rows(ju, SC + ["sector"])
    s = scan("america", {"symbols": {"tickers": ["SP:SPX"]}, "columns": ["change", "Perf.W", "Perf.1M"]})["data"][0]["d"]
    ku = {"ad": "S&P 500", "gun": r2(s[0]), "hafta": r2(s[1]), "ay": r2(s[2])}
    B = topla(R, "sec", kb, SEK_AD); U = topla(RU, "sector", ku, US_AD)
    MAK = [("FX_IDC:USDTRY", "USDTRY", "Dolar/TL"), ("TVC:TR10Y", "TR10Y", "TR 10 yıllık faiz"), ("BIST:XU100", "XU100", "BIST 100"), ("SP:SPX", "SPX", "S&P 500"),
           ("TVC:US10Y", "US10Y", "ABD 10 yıllık faiz"), ("TVC:DXY", "DXY", "Dolar endeksi"), ("TVC:GOLD", "GOLD", "Altın"), ("TVC:VIX", "VIX", "VIX korku endeksi")]
    mk = {x["s"]: x["d"] for x in scan("global", {"symbols": {"tickers": [m[0] for m in MAK]}, "columns": ["close", "change", "Perf.W", "Perf.1M", "Perf.3M"]})["data"]}
    makro = [{"kod": k2, "ad": ad, "v": r2(mk[t][0]), "gun": r2(mk[t][1]), "hafta": r2(mk[t][2]), "ay": r2(mk[t][3]), "ay3": r2(mk[t][4])} for t, k2, ad in MAK if t in mk]
    tarih = simdi().strftime("%d.%m %H:%M"); kon = cuma_sonra()
    out = {"tarama": tarih, "bist": {"kiyas": kb, "sektorler": B}, "abd": {"kiyas": ku, "sektorler": U}, "makro": makro,
           "projeksiyon": projeksiyon(B, "BIST", tarih, kon) + projeksiyon(U, "ABD", tarih, kon)}
    yaz(a, "sektor.json", out); print(f"SEKTÖR: BIST {len(B)}, ABD {len(U)}, makro {len(makro)}, projeksiyon {len(out['projeksiyon'])}")

def cmd_haber(a):
    pre = {"bist": "BIST:"}; lim = time.time() - 30 * 86400; out = {}
    sem = {}
    if a.piyasa == "abd":
        j = scan("america", {"filter": [{"left": "name", "operation": "in_range", "right": a.kodlar}, {"left": "is_primary", "operation": "equal", "right": True}],
                             "markets": ["america"], "columns": ["name"], "range": [0, 200]})
        sem = {x["d"][0]: x["s"] for x in j["data"]}
    for k in a.kodlar:
        s = sem.get(k) or (pre.get(a.piyasa, "") + k)
        try:
            j = http(f"https://news-headlines.tradingview.com/v2/headlines?client=web&lang={'tr' if a.piyasa == 'bist' else 'en'}&symbol={s}&streaming=false")
            out[k] = [datetime.datetime.fromtimestamp(i["published"], IST).strftime("%d.%m") + " " + i["title"][:140] for i in j.get("items", []) if i["published"] > lim][:6]
        except Exception as e:
            out[k] = [f"HATA {e}"]
        time.sleep(.3)
    yaz(a, f"haber_{a.piyasa}.json", out)
    for k, v in out.items(): print(k, "|", " || ".join(v[:4]))

def yahoo_mum(sembol, bas_ts, aralik="60m"):
    j = http(f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}?period1={int(bas_ts)}&period2={int(time.time())}&interval={aralik}", deneme=5, bekle=3)
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    return [(t, h, l, c) for t, h, l, c in zip(r["timestamp"], q["high"], q["low"], q["close"]) if h is not None]

def bist_saatlik(sembol, bas_ts):
    """BIST için TradingView ile aynı saat mumları: 15 dk mumlar saat başına (10:00-11:00 ... 17:00-18:10) toplanır.
    Açılış öncesi (09:30-09:59) 10:00 mumuna, kapanış seansı (18:00-18:10) 17:00 mumuna eklenir.
    Dönen zaman damgası t, mumun kapanışı t+3600 olacak şekilde ayarlıdır (17:00 mumu 18:10'da kapanır)."""
    M = yahoo_mum(sembol, bas_ts, "15m"); S = {}
    for t, h, l, c in M:
        d = datetime.datetime.fromtimestamp(t, IST); hr = min(max(d.hour, 10), 17)
        k = d.replace(hour=hr, minute=0, second=0, microsecond=0)
        if k in S: o = S[k]; S[k] = (max(o[0], h), min(o[1], l), c)
        else: S[k] = (h, l, c)
    return [((k.timestamp() + 600) if k.hour == 17 else k.timestamp(), h, l, c) for k, (h, l, c) in sorted(S.items())]

def tarih_ts(t):  # "08.11 20:04" → epoch (yıl: içinde bulunulan yıl)
    g, ay = t.split(" ")[0].split("."); n = simdi()
    hh, mm = (t.split(" ")[1].split(":") + ["0"])[:2] if " " in t else ("0", "0")
    d = datetime.datetime(n.year, int(ay), int(g), int(hh), int(mm), tzinfo=IST)
    if d > n + datetime.timedelta(days=2): d = d.replace(year=n.year - 1)
    return d.timestamp()

def bitis_gecti(bitis, piyasa):
    g, ay = bitis.split("."); n = simdi(); d = datetime.datetime(n.year, int(ay), int(g), 18 if piyasa == "bist" else 23, 59, tzinfo=IST)
    # BIST: vade günü 18:00 seans kapanışıdır; 18:05'ten sonra süre dolmuş sayılır (18:16 taraması aynı gün sonuçlandırır)
    if piyasa == "bist": return n > d.replace(hour=18, minute=0) + datetime.timedelta(minutes=5)
    return n > d + datetime.timedelta(hours=1, minutes=10)

def vade_ts(bitis, piyasa):
    """Vade sonu zaman damgası: BIST için bitiş günü 18:00; sonrasında açılan mumlar sonuca katılmaz."""
    g, ay = bitis.split("."); n = simdi()
    return datetime.datetime(n.year, int(ay), int(g), 18, 0, tzinfo=IST).timestamp() if piyasa == "bist" else None

def sonuclandir(r, mumlar, piyasa, giris_alan="giris"):
    """Giriş tarihinden SONRAKİ günlerin mumlarıyla (giriş günü kapanıştan girildiği için hariç) sonuç belirler."""
    gi = r.get(giris_alan) or r.get("fiyat"); st = r.get("stop"); hed = gi * 1.05; bas = tarih_ts(r["tarama"])
    M = [m for m in mumlar if m[0] >= bas]  # seçim anından sonra açılan saatlik mumlar
    vt = vade_ts(r["bitis"], piyasa) if r.get("bitis") else None
    if vt: M = [m for m in M if m[0] < vt] or M  # vade sonrası mumlar (ertesi sabah taraması) hedef/stop kararına katılmaz
    if not M: return None
    mx = max(m[1] for m in M); mn = min(m[2] for m in M); son = M[-1][3]
    r["max_degisim"] = round(mx / gi - 1, 4); r["min_degisim"] = round(mn / gi - 1, 4); r["degisim"] = round(son / gi - 1, 4)
    r["kontrol"] = simdi().strftime("%d.%m %H:%M"); r["kontrol_fiyat"] = round(son, 4)
    # gölge deney: stop yalnızca günlük KAPANIŞ stopun altındaysa (gün içi iğneler sayılmaz)
    g = None; gunler = {}
    for t, h, l, c in M: gunler[datetime.datetime.fromtimestamp(t, IST).date()] = (gunler.get(datetime.datetime.fromtimestamp(t, IST).date()) or []) + [(h, c)]
    for gd in sorted(gunler):
        if max(h for h, c in gunler[gd]) >= hed: g = "Başarılı"; break
        if st and gunler[gd][-1][1] <= st: g = "Stop"; break
    r["golge_kapanis_stop"] = g or ("Başarısız" if r.get("bitis") and bitis_gecti(r["bitis"], piyasa) else "Bekliyor")
    # Stop kuralı (kullanıcı talimatı 09.11): stop yalnızca 1 SAATLİK MUM stopun ALTINDA KAPANIRSA geçerlidir.
    # Fiyat gün içinde stopun altına inip saatlik mum stop üzerinde kapanırsa stop sayılmaz (iğne). Henüz kapanmamış son mum sayılmaz.
    # BIST saat mumları tam saatte başlar (10:00-11:00 ...); seçimden önce başlamış mum değerlendirilmez. Bu yüzden 10:16 taramasında stop olamaz, ilk karar 11:00 mumu kapanınca verilir.
    an = time.time(); r["stop_igne"] = None
    for t, h, l, c in M:
        gs = datetime.datetime.fromtimestamp(t, IST).strftime("%d.%m %H:%M"); kapandi = t + 3600 <= an
        if st and kapandi and c < st:
            r["sonuc"] = "Stop"; r["stop_tarih"] = gs
            if son > st: r["hata"] = f"Stop {gs} saatlik kapanışla gerçekleşti, sonra toparladı (son {round(son / gi - 1, 4):+.2%})."
            return "Stop"
        if st and l <= st and not r["stop_igne"]: r["stop_igne"] = gs  # iğne: stop altı görüldü ama saatlik kapanış üstünde
        if h >= hed:
            r["sonuc"] = "Başarılı"; r["hedef_tarih"] = gs; return "Başarılı"
    if r.get("bitis") and bitis_gecti(r["bitis"], piyasa):
        r["sonuc"] = "Başarısız"; return "Başarısız"
    return None

def cmd_kontrol(a):
    V = json.load(open(a.veri)); deg = []
    gruplar = [("history", V.get("history", []), "bist", "giris", ".IS"), ("yurtdisi", V.get("yurtdisi", {}).get("history", []), "abd", "giris", ""),
               ("kripto", V.get("kripto", {}).get("hisseler", []), "abd", "fiyat", ""), ("lab_bist", V.get("lab_bist", {}).get("hisseler", []), "bist", "giris", ".IS")]
    for ad, L, pz, ga, ek in gruplar:
        for r in L:
            if r.get("sonuc") != "Bekliyor": continue
            if not r.get("tarama"):
                r["tarama"] = V.get("kripto", {}).get("tarama", "") if ad == "kripto" else ""
            try:
                mum = bist_saatlik(r["kod"] + ek, tarih_ts(r["tarama"]) - 3600) if ek == ".IS" else yahoo_mum(r["kod"] + ek, tarih_ts(r["tarama"]) - 3600)
            except Exception as e:
                print("veri yok", r["kod"], e); continue
            s = sonuclandir(r, mum, pz, ga)
            if s: deg.append({"grup": ad, "kod": r["kod"], "tarama": r["tarama"], "sonuc": s, "giris": r.get(ga), "stop": r.get("stop"), "degisim": r.get("degisim"), "max_degisim": r.get("max_degisim")})
            time.sleep(.4)
    json.dump(V, open(a.veri, "w"), ensure_ascii=False)
    yaz(a, "kontrol.json", {"tarih": simdi().strftime("%d.%m %H:%M"), "degisen": deg})
    print(f"KONTROL: {len(deg)} kayıt sonuçlandı:", [(d['grup'], d['kod'], d['sonuc']) for d in deg])

def cmd_paket(a):
    B = json.load(open(a.girdi)); S = sorted(B["tum"], key=lambda s: s["kod"]); n = a.n; out = []; s0 = 0
    para = "$" if "abd" in os.path.basename(a.girdi) else None
    for i in range(n):
        sz = len(S) // n + (1 if i < len(S) % n else 0); sl = S[s0:s0 + sz]; s0 += sz; done = S[:s0]
        sec = sorted([s for s in sl if s["uygun"]], key=lambda s: -s["puan"]) + sorted([s for s in sl if not s["uygun"]], key=lambda s: -s["puan"])
        son = [{"kod": s["kod"], "periyot": "3P", "puan": s["puan"], "rv": s["rv"], "fiyat": s["fiyat"], "pk": s["pk"], "tk": s["tk"], "uygun": s["uygun"],
                "sebep": "" if s["uygun"] else s["sebep"], **({"para": "$"} if para else {})} for s in sec[:5]]
        uy = sum(s["uygun"] for s in done)
        out.append({"durum": "taraniyor", "tarama": a.etiket, "oturum": a.oturum, "toplam": len(S), "islenen": len(done),
                    "adim": f"1S - 4S - Günlük · paket {i + 1}/{n}", "sayac": {"puanlanan": len(done), "uygun": uy, "elenen": len(done) - uy, "kap": 0},
                    "en_iyi": [{"kod": s["kod"], "puan": s["puan"]} for s in sorted([s for s in done if s["uygun"]], key=lambda s: -s["puan"])[:10]],
                    "son": son, "hedefe_ulasan": [], "stop_olan": [], "suresi_dolan": []})
    yaz(a, "paketler.json", out); print(f"PAKET: {len(out)} paket, en az {min(len(p['son']) for p in out)} hisse/paket")

# Resmî tatiller (tam gün kapalı). Yarım günler işlem günü sayılır.
TATIL = {"bist": {"2026-01-01", "2026-03-20", "2026-04-23", "2026-05-01", "2026-05-19", "2026-05-27", "2026-05-28", "2026-05-29",
                  "2026-07-15", "2026-10-29", "2027-01-01"},
         "abd": {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
                 "2026-11-26", "2026-12-25", "2027-01-01"}}

def islem_gunu(d, piyasa="bist"):
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in TATIL.get(piyasa, set())

def is_gunu_ekle(n, gun, piyasa="bist"):
    d = n
    while gun > 0:
        d += datetime.timedelta(days=1)
        if islem_gunu(d, piyasa): gun -= 1
    return d.strftime("%d.%m")

def vade(piyasa="bist", an=None):
    """Vade = seçimden SONRAKİ 2 tam işlem günü. Seans içinde seçilen hissede seçim gününün kalanı ek süredir (gün sayılmaz)."""
    return is_gunu_ekle((an or simdi()).replace(hour=12), 2, piyasa)

def _kalite_kapisi(a, B, V):
    """Kalite kapısı (§16): model.json ile tüm evrenin günlük grafiğini puanlar. Döner: ({kod: skor}, model) ya da (None, None)."""
    yol = getattr(a, "model", None) or "model.json"
    if not os.path.exists(yol): return None, None
    mj = json.load(open(yol)); gen = (B.get("ozet") or {}).get("yukselen") or .5
    kodlar = sorted({s["kod"] for s in B.get("tum", [])}); C = _gunluk_hepsi(kodlar); out = {}; lt_min = math.log(mj.get("likit_min_tl", 2e7))
    for k, M in C.items():
        if len(M) < 140: continue
        try:
            o = _oz_ozellikler(M, OZ_SIRA, canli=True)
            if not o: continue
            rec = _oz_vektor(M, o[-1][2], gen)
            if rec["lt"] < lt_min or rec["chg"] >= .09: continue   # sığ ya da tavana yakın: alınamaz, sıralamaya girmez
            out[k] = round(_agac_tahmin(mj, rec), 3)
        except Exception as e: print("UYARI: kalite kapısı", k, e)
    dg = mj.get("dogrulama") or {}
    V["kalite_kapisi"] = {"surum": mj.get("surum"), "evren": len(out), "gunluk_n": dg.get("gunluk_n"), "kademe_yuzde": dg.get("kademe_yuzde"), "dogrulama": (dg.get("top") or {}).get("3"),
                          "en_iyi": sorted(out.items(), key=lambda kv: -kv[1])[:15]}
    iz = {p_["kod"] for p_ in (V.get("kasa") or {}).get("acik", [])} | {h["kod"] for h in V.get("history", []) if h.get("sonuc") == "Bekliyor"}
    V["kalite_kapisi"]["skor"] = {k: out[k] for k in iz if k in out}   # portföy ve takip hisselerinin güncel model skoru (kasa değiştirme kararı için)
    return out, mj

KK_ESIK_MIN_N = 20      # gözden geçirme için sonuçlanmış, model skorlu en az kayıt (MOTOR.md §16)
KK_ESIK_YENI_N = 5      # son gözden geçirmeden bu kadar yeni sonuç birikmeden yeniden bakılmaz (gürültüyle oynamayı önler)
KK_ESIK_MIN_USTU = 15   # eşiğin üstünde kalan en az kayıt (az örnekle eşik konmaz)

def _kk_istat(L):
    """Kayıt listesi → n, isabet (hedef ya da kârla kapanış), stop oranı, ortalama getiri (%)."""
    if not L: return {"n": 0, "isabet": None, "stop": None, "ort_getiri": None}
    ok = sum(1 for h in L if h["sonuc"] in ("Başarılı", "Kâr korundu") or (h["sonuc"] == "Erken kapandı" and h["degisim"] > 0))
    st = sum(1 for h in L if h["sonuc"] == "Stop")
    return {"n": len(L), "isabet": round(ok / len(L), 3), "stop": round(st / len(L), 3), "ort_getiri": round(sum(h["degisim"] for h in L) / len(L) * 100, 2)}

def _kk_esik_gozden(V, zaman):
    """Kalite kapısı model-skor eşiğinin OTOMATİK gözden geçirilmesi (MOTOR.md §16).
    Girdi: history'deki sonuçlanmış, model skorlu kayıtlar. n >= 20 olunca, her +5 yeni sonuçta bir kez:
    skor dağılımının alt %25 ve %50 kesimleri aday eşiktir; aday eşik ancak (üstünde en az 15 kayıt kalıyorsa) VE isabet tüm kayıtlardan >= 5 puan iyi
    VE stop oranı daha yüksek değil VE ortalama getiri >= 0,4 puan iyiyse konur; kanıt yoksa eşik kaldırılır (None = eşik yok). Sonuç veri.json → kalite_kapisi_esik. Döner: eşik (ya da None)."""
    S = V.setdefault("kalite_kapisi_esik", {})
    Hs = [h for h in V.get("history", []) if h.get("model") is not None and h.get("sonuc") not in (None, "Bekliyor") and h.get("degisim") is not None]
    n = len(Hs); S["n"] = n
    if n < KK_ESIK_MIN_N:
        S["durum"] = f"bekliyor: sonuçlanmış model skorlu kayıt {n}/{KK_ESIK_MIN_N}"; S.setdefault("esik", None); return S.get("esik")
    if S.get("son_n") is not None and n - S["son_n"] < KK_ESIK_YENI_N: return S.get("esik")
    skor = sorted(h["model"] for h in Hs); tum = _kk_istat(Hs); eski = S.get("esik"); yeni = None; gerekce = "eşik yok: veri bir eşiği desteklemiyor"
    for q in (.5, .25):   # önce yüksek eşik, sonra düşük; ilk kanıtlanan kullanılır (yüksek eşik seçimi en çok daraltır, bu yüzden kanıt şartı en zor olandır)
        c = round(skor[int(len(skor) * q)], 3); ust = [h for h in Hs if h["model"] >= c]; ist = _kk_istat(ust)
        if ist["n"] >= KK_ESIK_MIN_USTU and ist["isabet"] - tum["isabet"] >= .05 and ist["stop"] <= tum["stop"] and ist["ort_getiri"] - tum["ort_getiri"] >= .4:
            yeni = c; gerekce = f"eşik {c}: üstünde {ist['n']} kayıt, isabet %{ist['isabet']*100:.0f} (tümü %{tum['isabet']*100:.0f}), stop %{ist['stop']*100:.0f} (%{tum['stop']*100:.0f}), ort. getiri %{ist['ort_getiri']:+.2f} (%{tum['ort_getiri']:+.2f})"; gerekce = re.sub(r"(\d)\.(\d)", r"\1,\2", gerekce); break
    ucl = [skor[0]] + [skor[int(len(skor) * q)] for q in (1 / 3, 2 / 3)] + [float("inf")]
    dil = [{"aralik": f"{ucl[i]:.2f} ≤ skor < {('%.2f' % ucl[i + 1]) if ucl[i + 1] != float('inf') else '∞'}", **_kk_istat([h for h in Hs if ucl[i] <= h["model"] < ucl[i + 1]])} for i in range(3)]
    S.update({"esik": yeni, "son_n": n, "guncelleme": zaman, "tum": tum, "ustu": _kk_istat([h for h in Hs if yeni is not None and h["model"] >= yeni]) if yeni is not None else None,
              "dilimler": dil, "gerekce": gerekce, "durum": "otomatik gözden geçirildi", "onceki": eski})
    print(f"KK EŞİK (otomatik gözden geçirme, n={n}): {eski} → {yeni} · {gerekce}")
    return yeni

def _ban_listesi():
    """rules.json -> ban (liste ya da {kod: neden}); dosya yoksa boş."""
    try:
        r = json.load(open("rules.json", encoding="utf-8")).get("ban", [])
        return {k: "" for k in r} if isinstance(r, list) else dict(r)
    except Exception: return {}

OGR_MIN_SONUC = 30; OGR_MIN_ISABET = 0.45; OGR_MAX_STOP = 0.45
def _ogrenme_asamasi(V, tarih):
    """Kullanıcı kuralı 17.11: yeni hisse önerisi yalnızca kalite kapısının ileri testi ölçülmüşse açılır.
    Ölçüm: kalite kapısından geçerek seçilen (model skoru kaydı olan) ve sonuçlanan kayıtlar. Eşikler rules.json -> ogrenme_asamasi ile değiştirilir.
    Öneri açık değilken seçimler yine yapılır ve kasada sanal izlenir; sayfa 'öğrenme aşaması' yazar."""
    mn, mi, ms = OGR_MIN_SONUC, OGR_MIN_ISABET, OGR_MAX_STOP
    try:
        o = json.load(open("rules.json", encoding="utf-8")).get("ogrenme_asamasi") or {}
        mn = int(o.get("min_sonuc", mn)); mi = float(o.get("min_isabet", mi)); ms = float(o.get("max_stop", ms))
    except Exception: pass
    R = [h for h in V.get("history", []) if h.get("model") is not None and h.get("sonuc") in ("Başarılı", "Kâr korundu", "Stop", "Başarısız")]
    n = len(R); isa = sum(h["sonuc"] in ("Başarılı", "Kâr korundu") for h in R); st = sum(h["sonuc"] == "Stop" for h in R)
    oran = round(isa / n, 3) if n else None; sor = round(st / n, 3) if n else None
    if n < mn: aktif = True; sebep = f"kalite kapısıyla seçilip sonuçlanan {n}/{mn} kayıt; ileri test için en az {mn} sonuç gerekli"
    elif oran < mi or sor > ms: aktif = True; sebep = f"{n} sonuçta isabet %{oran*100:.1f} (en az %{mi*100:.0f} gerekli), stop %{sor*100:.1f} (en çok %{ms*100:.0f})"
    else: aktif = False; sebep = f"{n} sonuçta isabet %{oran*100:.1f}, stop %{sor*100:.1f}: ileri test koşulları sağlandı"
    return {"aktif": aktif, "sebep": sebep, "sonuc": n, "isabet": oran, "stop": sor, "gerekli_sonuc": mn, "gerekli_isabet": mi, "en_cok_stop": ms, "guncelleme": tarih}

PORTFOY_MAX = 10   # sanal portföy üst sınırı (kullanıcı kuralı). Takip için elle sayı sınırı yoktur: sınırları model öğrenir (gunluk_n, kademe_yuzde)

def cmd_adaylar(a):
    B = json.load(open(a.girdi)); K = {k["kod"]: k for k in json.load(open(a.karar))}; V = json.load(open(a.veri))
    tarih = simdi().strftime("%d.%m %H:%M"); bitis = vade(a.piyasa)
    havuz = []; karar_eksik = []
    BAN = _ban_listesi() if a.piyasa == "bist" else {}   # kural 17.11: yasaklı hisse (SPK tedbiri, kayyım, suç duyurusu vb.) hiçbir koşulda aday olamaz
    ban_elenen = []
    ACIK0 = {h["kod"] for h in (V.get("history", []) if a.piyasa == "bist" else V.get("yurtdisi", {}).get("history", [])) if h.get("sonuc") == "Bekliyor"}
    for s in B["adaylar"]:
        if s["kod"] in BAN: ban_elenen.append(s["kod"]); continue
        if s["kod"] in ACIK0: continue  # tarama sonrası yayınlanan başka çalışmada takibe alınmış hisse tekrar seçilmez
        k = K.get(s["kod"])
        if not k:
            karar_eksik.append(s["kod"]); continue  # KAP/haber kararı yok: seçilmez ama sessiz atlanmaz (aşağıda uyarı + veri.json'a not)
        s = dict(s); hp = float(k.get("haber_puan", 0)); s["pk"] = dict(s["pk"]); s["pk"]["KAP"] = hp; s["puan"] = round(s["puan"] + hp, 2); s["haber"] = k.get("haber", "")
        if s["puan"] >= B["esik"]: havuz.append(s)
    havuz.sort(key=lambda s: (-s["puan"], -s["rv"]))
    KK, MJ = _kalite_kapisi(a, B, V) if a.piyasa == "bist" else (None, None)
    izle = []
    if KK is None:  # model yok ya da ABD (yalnızca laboratuvar): eski davranış
        sec = havuz[:10]
        if a.piyasa == "bist": print("UYARI: model.json yok, kalite kapısı uygulanmadı (eski davranış)")
    else:
        # Seçim kuralı (öğrenilmiş): evren içi sıralamada ilk %kademe_yuzde içinde olan ve radar filtrelerinden (KAP, derinlik, puan) geçen hisseler; günlük sayı ve kademe model tarafından öğrenilir (egit.py)
        dg = MJ.get("dogrulama") or {}; gn = int(dg.get("gunluk_n") or 3); q = int(dg.get("kademe_yuzde") or 3)
        sirali = sorted(KK.items(), key=lambda kv: -kv[1]); sira = {k: i + 1 for i, (k, v) in enumerate(sirali)}; kesim = max(1, round(len(sirali) * q / 100))
        bugun = simdi().strftime("%d.%m"); bugun_n = sum(1 for h in V.get("history", []) if str(h.get("tarama", "")).startswith(bugun))
        kalan = max(0, gn - bugun_n)
        gor = {h["kod"] for h in V.get("history", [])}; dk = simdi().hour * 60 + simdi().minute; ret = {"kademe dışı": 0, "ilk kez 10-12": 0, "sığ": 0, "puan yok": 0}
        gecen = []; kk_e = _kk_esik_gozden(V, tarih)
        for s in havuz:
            s["model"] = KK.get(s["kod"]); s["sira"] = sira.get(s["kod"])
            if s["model"] is None: ret["puan yok"] += 1; continue
            if kk_e is not None and s["model"] < kk_e: ret["model eşiği"] = ret.get("model eşiği", 0) + 1; continue
            if s["sira"] > kesim: ret["kademe dışı"] += 1; continue
            if s["kod"] not in gor and dk < 720: ret["ilk kez 10-12"] += 1; continue   # kasa kuralı: ilk kez seçilen hisse 10:00-11:59 arası alınmaz (canlı isabet %40, stop %52); seçimle portföy aynı kalsın diye burada uygulanır
            if s.get("derinlik") == "Sığ": ret["sığ"] += 1; continue
            gecen.append(s)
        gecen.sort(key=lambda s: -s["model"]); sec = gecen[:kalan]
        print(f"KALİTE KAPISI: evren {len(sirali)} hisse, ilk %{q} = {kesim} hisse · radar havuzu {len(havuz)} → kuralı geçen {len(gecen)} → seçilen {len(sec)} (bugün {bugun_n}/{gn}) · elenenler {ret} · evrenin en iyisi: {', '.join(f'{k} {v}' for k, v in sirali[:5])}")
    picks = []; hist = []
    H0 = V.get("history", []) if a.piyasa == "bist" else V.get("yurtdisi", {}).get("history", [])
    son_basari = {h["kod"]: h for h in H0 if h.get("sonuc") == "Başarılı"}
    for i, s in enumerate(sec):
        yz = f"{s['stop_yuzde'] * 100:.1f}".replace(".", ","); nd = (", ".join(s["why"]) or "çoklu periyot uyumu") + f". Stop {s['stop_neden']}, %{yz}" + (f". Derinlik: {s['derinlik'].lower()}, günlük ort. ciro ~{int(s['likit_mn'])} mn ₺" if s.get("likit_mn") is not None else "")
        p = {"tarama": tarih, "sira": i + 1, "kod": s["kod"], "ad": s.get("ad"), "sektor": s["sektor"], "fiyat": s["fiyat"], "skor": s["puan"], "hedef": s["hedef"], "stop": s["stop"],
             "stop_yuzde": s["stop_yuzde"], "rsi": s["rsi"], "neden": nd, "bitis": bitis, "pk": s["pk"], "tk": s["tk"],
             "uyari": ", ".join(x for x in s["sebep"].split(", ") if x.startswith("günlük") or x.startswith("1S")),
             "likit_mn": s.get("likit_mn"), "kapasite_tl": s.get("kapasite_tl"), "derinlik": s.get("derinlik"), "model": s.get("model")}
        hist_model = s.get("model")
        if s.get("model") is not None: p["neden"] = f"Kalite kapısı: model skoru {s['model']:.2f}, evrende {s.get('sira')}. sırada. " + p["neden"]
        if s["kod"] in son_basari:
            b0 = son_basari[s["kod"]]; p["trend_devam"] = {"onceki_tarama": b0["tarama"], "onceki_max": b0.get("max_degisim"), "onceki_giris": b0.get("giris")}
            yz2 = f"{(b0.get('max_degisim') or 0) * 100:.1f}".replace(".", ","); p["neden"] = f"Trend devam ediyor: {b0['tarama']} seçimi hedefe ulaştı (+%{yz2}). " + p["neden"]
        p["kap" if a.piyasa == "bist" else "haber"] = s["haber"]; picks.append(p)
        hist.append({"trend_devam": bool(p.get("trend_devam")), "model": hist_model, "tarama": tarih, "kod": s["kod"], "giris": s["fiyat"], "stop": s["stop"], "bitis": bitis, "kontrol": None, "kontrol_fiyat": None, "degisim": None,
                     "max_degisim": None, "min_degisim": None, "hedef_tarih": None, "stop_tarih": None, "sonuc": "Bekliyor", "hata": None,
                     "likit_mn": s.get("likit_mn"), "kapasite_tl": s.get("kapasite_tl"), "derinlik": s.get("derinlik")})
    izl = [{"kod": s["kod"], "fiyat": s["fiyat"], "skor": s["puan"], "model": s.get("model"), "neden": (s.get("kk_neden") or "eşik üstü, ilk 10 dışında") + ": " + (", ".join(s["why"][:2]) or s["sebep"]) + (f"; {s['haber']}" if s["haber"] else "")} for s in izle]
    # İzleme listesi en az 10 hisse: eşik üstü ama ilk 10 dışında kalanlar + eşiğe yakın (eşik-1,5) ya da filtreye takılan güçlü hisseler
    alinan = {x["kod"] for x in sec} | {x["kod"] for x in izl} | {h["kod"] for h in H0 if h.get("sonuc") == "Bekliyor"}
    yakin = sorted([s for s in B.get("tum", []) if s["kod"] not in alinan and not s.get("acik") and s["puan"] >= B["esik"] - 1.5],
                   key=lambda s: (-s["puan"], -(s.get("rv") or 0)))
    for s in yakin[:max(0, 10 - len(izl))]:
        neden = ("eşiğe yakın" if s["puan"] < B["esik"] else "eşik üstü ama filtreye takıldı") + ": " + (s.get("sebep") or ", ".join(s.get("why", [])[:2]))
        izl.append({"kod": s["kod"], "fiyat": s["fiyat"], "skor": s["puan"], "neden": neden})
    if a.piyasa == "bist": izl = []   # izleme listesi kaldırıldı (17.11): yalnızca kuralları geçen seçimler görünür
    sc = {"tarama": tarih, "taranan": B["ozet"]["taranan"], "uygun": B["ozet"]["uygun"], "aday": len(picks), "kontrol": 0, "basarili": 0, "stop": 0}
    if a.piyasa == "bist":
        V["picks"] = picks; V["history"] = V.get("history", []) + hist; V["izleme"] = izl; V["guncelleme"] = tarih
        V["son_tarama"] = {"tarama": tarih, "oturum": "Bulut tarama", "taranan": B["ozet"]["taranan"], "kap_kontrol": len(K), "puan_esigi": B["esik"]}
        sc["piyasa"] = {"xu100": B["ozet"]["xu100"]["gun"], "yukselen": B["ozet"]["yukselen"]}; V.setdefault("scans", []).append(sc)
    else:
        Y = V.setdefault("yurtdisi", {}); Y["picks"] = picks; Y["history"] = Y.get("history", []) + hist; Y["izleme"] = izl
        Y["son_tarama"] = {"tarama": tarih, "oturum": "Bulut tarama", "taranan": B["ozet"]["taranan"], "uygun": B["ozet"]["uygun"], "haber_kontrol": len(K), "puan_esigi": B["esik"]}
        Y["piyasa"] = B["ozet"]["piyasa"]; Y.setdefault("scans", []).append(sc)
    if a.piyasa == "bist":
        V["ogrenme_asamasi"] = _ogrenme_asamasi(V, tarih)
        for p_ in V.get("picks", []): p_["asama"] = "öğrenme" if V["ogrenme_asamasi"]["aktif"] else "öneri"
        if ban_elenen: V["son_tarama"]["ban_elenen"] = ban_elenen; print(f"YASAKLI LİSTE: aday olamayan hisseler {ban_elenen}")
        print(f"AŞAMA: {'ÖĞRENME (öneri değildir, sanal izleme)' if V['ogrenme_asamasi']['aktif'] else 'ÖNERİ AÇIK'} · {V['ogrenme_asamasi']['sebep']}")
    if karar_eksik:
        (V["son_tarama"] if a.piyasa == "bist" else V["yurtdisi"]["son_tarama"])["karar_eksik"] = karar_eksik
        print(f"UYARI: karar dosyasında KAP/haber kararı olmayan aday(lar) elendi: {karar_eksik}. karar.json'a ekleyip adaylar'ı tekrar çalıştır.")
    json.dump(V, open(a.veri, "w"), ensure_ascii=False)
    if a.piyasa == "bist" and a.girdi and os.path.exists(a.girdi):  # öğrenme döngüsü otomatik: gözlem arşivi + öğren (MOTOR.md §6)
        try:
            a.arsiv = getattr(a, "arsiv", None) or "arsiv"
            cmd_gozlem(a); cmd_ogren(a)
        except Exception as e: print("UYARI: gözlem/öğren adımı başarısız:", e)
        try: cmd_ozlab(a)  # özellik laboratuvarı: her grafik taramasından sonra güncellenir
        except Exception as e: print("UYARI: özellik laboratuvarı başarısız:", e)
    print(f"ADAYLAR ({a.piyasa}): {[p['kod'] for p in picks]} · izleme {len(izl)} · bitiş {bitis}")


def cmd_kaydet(a):
    """cikti/kripto.json, cikti/sektor.json ve cikti/endeks.json sonuçlarını veri.json'a işler (eskiler geçmişe taşınır)."""
    V = json.load(open(a.veri)); t = simdi().strftime("%d.%m %H:%M"); bitis = vade("abd"); bitis_b = vade("bist"); yap = []
    kp = os.path.join(a.out, "kripto.json")
    if os.path.exists(kp) and "kripto" in a.kodlar:
        C = json.load(open(kp)); K = V.setdefault("kripto", {})
        K.setdefault("gecmis", []).append({"tarama": K.get("tarama"), "btc": K.get("btc"), "grup": K.get("grup")})
        K["tarama"] = t; K["btc"] = {**C["btc"], "puan": None}; K["grup"] = C["grup"]
        acik = {h["kod"]: h for h in K.get("hisseler", []) if h.get("sonuc") == "Bekliyor"}
        yeni = []
        for h in C["hisseler"]:
            if h["kod"] in acik: yeni.append(acik[h["kod"]]); continue
            yeni.append({"kod": h["kod"], "kategori": next((x.get("kategori") for x in K.get("hisseler", []) if x["kod"] == h["kod"]), ""), "fiyat": h["fiyat"], "degisim_gun": round(h["ch"] / 100, 4),
                         "rv": h["rv"], "puan": h["puan"], "pk": h["pk"], "tk": h["tk"], "stop": h["stop"], "stop_yuzde": h["stop_yuzde"], "hedef": h["hedef"], "rsi": h["rsi"],
                         "neden": ", ".join(h["why"]), "sebep": h["sebep"], "uygun": h["uygun"], "tarama": t, "bitis": bitis, "sonuc": "Bekliyor",
                         "kontrol_fiyat": None, "max_degisim": None, "min_degisim": None})
        yeni += [h for k, h in acik.items() if k not in {x["kod"] for x in yeni}]
        K.setdefault("arsiv", []).extend([h for h in K.get("hisseler", []) if h.get("sonuc") != "Bekliyor"]); K["hisseler"] = yeni
        K.setdefault("tahminler", []).append({"tarama": t, "btc_giris": C["tahmin"]["btc_giris"], "yon": C["tahmin"]["yon"], "sinyal": C["tahmin"]["sinyal"],
                                             "kontrol": (simdi() + datetime.timedelta(days=1)).strftime("%d.%m %H:%M"), "btc_kontrol": None, "sonuc": "Bekliyor"})
        yap.append("kripto")
    sp = os.path.join(a.out, "sektor.json")
    if os.path.exists(sp) and "sektor" in a.kodlar:
        S = json.load(open(sp)); L = V.setdefault("sektor_lab", {})
        if L.get("bist"):
            L.setdefault("gecmis", []).append({"tarama": L.get("tarama"), "bist": [{k: x[k] for k in ("kod", "kadran", "rs", "ivme", "kayma", "net_akis", "hafta", "ay")} for x in L["bist"]["sektorler"]],
                                               "abd": [{k: x[k] for k in ("kod", "kadran", "rs", "ivme", "kayma", "net_akis", "hafta", "ay")} for x in L["abd"]["sektorler"]], "makro": L.get("makro")})
        L["tarama"] = t; L["veri"] = "TradingView · bulut"; L["bist"] = S["bist"]; L["abd"] = S["abd"]; L["makro"] = S["makro"]
        eski = [p for p in L.get("projeksiyon", []) if p.get("sonuc") == "Bekliyor"]
        L.setdefault("projeksiyon_arsiv", []).extend([p for p in L.get("projeksiyon", []) if p.get("sonuc") != "Bekliyor"])
        L["projeksiyon"] = eski + ([] if eski else S["projeksiyon"]); yap.append("sektor")
    ep = os.path.join(a.out, "endeks.json")
    if os.path.exists(ep) and "endeks" in a.kodlar:
        E = json.load(open(ep)); LB = V.setdefault("lab_bist", {}); acik = [h for h in LB.get("hisseler", []) if h.get("sonuc") == "Bekliyor"]
        if not acik:
            AD = {"XU030": "BIST 30", "XU050": "BIST 50 (BIST 30 dışı)", "XU100": "BIST 100 (BIST 50 dışı)"}
            LB.setdefault("arsiv", []).extend(LB.get("hisseler", []))
            LB["hisseler"] = [{"kod": s["kod"], "katman": k, "katman_ad": AD[k], "grup": s["grup"], "sektor": s["sektor"], "giris": s["fiyat"], "degisim_gun": round(s["ch"] / 100, 4),
                               "rv": s["rv"], "puan": s["puan"], "pk": s["pk"], "tk": s["tk"], "stop": s["stop"], "stop_yuzde": s["stop_yuzde"], "hedef": s["hedef"], "rsi": s["rsi"],
                               "sebep": s["sebep"], "tarama": t, "bitis": bitis_b, "sonuc": "Bekliyor", "degisim": None, "max_degisim": None, "min_degisim": None, "kontrol": None, "kontrol_fiyat": None}
                              for k, L2 in E["secim"].items() for s in L2]
            LB["tarama"] = t; yap.append("endeks")
    json.dump(V, open(a.veri, "w"), ensure_ascii=False); print("KAYDET:", yap or "değişiklik yok")

# ---------------------------------------------------------------------------
# Arka plan gözlem arşivi: her taramada TÜM hisselerin özellikleri saklanır;
# 1-2 işlem günü sonra gerçekleşen hareketle eşleştirilip "neden yükseldi/düştü" öğrenilir.
GZ_COLS = ["kod", "fiyat", "ch", "rv", "puan", "rsi", "rsi1s", "rsi4s", "mt", "uygun", "asiri", "g_trend",
           "RSI-MACD", "Trend", "Hacim", "Uyum", "Dip", "Risk", "tk1S", "tk4S", "tkG", "pw", "p1m", "cfo", "h1m", "l1m",
           "sektor", "katman", "mcap_mlr", "why", "likit_mn"]

def cmd_gozlem(a):
    """cikti/<piyasa>.json → arsiv/gozlem_<piyasa>_YYYY-MM-DD.json içine bu taramanın tüm hisse anlık görüntüsünü ekler."""
    B = json.load(open(a.girdi)); n = simdi(); os.makedirs(a.arsiv, exist_ok=True)
    yol = os.path.join(a.arsiv, f"gozlem_{a.piyasa}_{n.strftime('%Y-%m-%d')}.json")
    G = json.load(open(yol)) if os.path.exists(yol) else {"piyasa": a.piyasa, "tarih": n.strftime("%Y-%m-%d"), "cols": GZ_COLS, "taramalar": []}
    if len(G["cols"]) < len(GZ_COLS):  # eski arşiv: yeni sütunlar eklenir, eski satırlar boş doldurulur
        eks = len(GZ_COLS) - len(G["cols"]); G["cols"] = list(GZ_COLS)
        for t in G["taramalar"]:
            for r in t["rows"]: r.extend([None] * eks)
    rows = []
    for s in B["tum"]:
        oz = s.get("oz") or {}; pk = s.get("pk") or {}; tk = s.get("tk") or {}
        rows.append([s["kod"], s["fiyat"], s["ch"], s["rv"], s["puan"], s.get("rsi"), oz.get("rsi1s"), oz.get("rsi4s"), s.get("mt"),
                     int(bool(s.get("uygun"))), oz.get("asiri", int("aşırı" in (s.get("sebep") or ""))),
                     oz.get("g_trend", int("günlük trend aşağı" not in (s.get("sebep") or ""))),
                     pk.get("RSI-MACD"), pk.get("Trend"), pk.get("Hacim"), pk.get("Uyum"), pk.get("Dip"), pk.get("Risk"),
                     (tk.get("1S") or [None] * 3)[2], (tk.get("4S") or [None] * 3)[2], (tk.get("G") or [None] * 3)[2],
                     oz.get("pw"), oz.get("p1m"), oz.get("cfo"), oz.get("h1m"), oz.get("l1m"),
                     s.get("sektor"), s.get("katman"), r2((s.get("mcap") or 0) / 1e9), "|".join(s.get("why") or []), s.get("likit_mn")])
    oz = B.get("ozet", {})
    pz = {k: oz.get(k) for k in ("yukselen", "hacim_ort", "uygun")}
    pz.update({"xu100": oz.get("xu100"), "piyasa": oz.get("piyasa")})
    an = (B.get("tarih") or "").split(" ")[-1] or n.strftime("%H:%M")
    G["taramalar"] = [t for t in G["taramalar"] if t["saat"] != an] + [{"saat": an, "ts": int(n.timestamp()), "seans_ici": B.get("seans_ici"), "piyasa": pz, "rows": rows}]
    json.dump(G, open(yol, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"GÖZLEM: {len(rows)} hisse → {yol} ({len(G['taramalar'])} tarama, {os.path.getsize(yol) // 1024} KB)")

def _kova(ad, v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return None
    B = {"puan": [(-99, 3, "<3"), (3, 5, "3-5"), (5, 6, "5-6"), (6, 7, "6-7"), (7, 8, "7-8"), (8, 99, "≥8")],
         "rv": [(0, .5, "<0,5x"), (.5, .8, "0,5-0,8x"), (.8, 1.5, "0,8-1,5x"), (1.5, 3, "1,5-3x"), (3, 1e9, "≥3x")],
         "ch": [(-99, -3, "<-%3"), (-3, -1, "-%3/-%1"), (-1, 1, "-%1/+%1"), (1, 3, "+%1/+%3"), (3, 4.7, "+%3/+%4,7"), (4.7, 9.5, "+%4,7/+%9,5"), (9.5, 99, "tavan")],
         "rsi": [(0, 30, "<30"), (30, 45, "30-45"), (45, 55, "45-55"), (55, 65, "55-65"), (65, 75, "65-75"), (75, 101, "≥75")],
         "rsi1s": [(0, 30, "<30"), (30, 50, "30-50"), (50, 70, "50-70"), (70, 82, "70-82"), (82, 101, "≥82")],
         "mt": [(0, 4, "0-3"), (4, 8, "4-7"), (8, 11, "8-10"), (11, 13, "11-12")],
         "tk": [(-1.01, -.5, "Güçlü Sat"), (-.5, -.1, "Sat"), (-.1, .1, "Nötr"), (.1, .5, "Al"), (.5, 1.01, "Güçlü Al")],
         "pw": [(-99, -5, "<-%5"), (-5, 0, "-%5/0"), (0, 5, "0/+%5"), (5, 10, "+%5/+%10"), (10, 999, "≥+%10")],
         "p1m": [(-99, -10, "<-%10"), (-10, 0, "-%10/0"), (0, 10, "0/+%10"), (10, 25, "+%10/+%25"), (25, 9999, "≥+%25")],
         "h1m": [(-9, -.15, "zirveye >%15"), (-.15, -.05, "zirveye %5-15"), (-.05, -.005, "zirveye <%5"), (-.005, 9, "1 ay zirvesinde")],
         "likit": [(0, 5, "<5 mn"), (5, 20, "5-20 mn"), (20, 50, "20-50 mn"), (50, 100, "50-100 mn"), (100, 1e9, "≥100 mn")],
         "mcap": [(0, 1.5, "<1,5 mlr"), (1.5, 10, "1,5-10 mlr"), (10, 50, "10-50 mlr"), (50, 1e9, "≥50 mlr")]}
    for lo, hi, et in B[ad]:
        if lo <= v < hi: return et
    return None

def _ozellikler(r, C, piyasa):
    x = dict(zip(C, r)); F = []
    def ek(k, e):
        if e is not None: F.append(f"{k}={e}")
    ek("puan", _kova("puan", x["puan"])); ek("hacim", _kova("rv", x["rv"])); ek("gün", _kova("ch", x["ch"]))
    ek("RSI G", _kova("rsi", x["rsi"])); ek("RSI 1S", _kova("rsi1s", x["rsi1s"])); ek("3P kriter", _kova("mt", x["mt"]))
    for t in ("tk1S", "tk4S", "tkG"): ek("teknik " + t[2:], _kova("tk", x[t]))
    ek("hafta", _kova("pw", x["pw"])); ek("1 ay", _kova("p1m", x["p1m"])); ek("1 ay zirve", _kova("h1m", x["h1m"]))
    ek("piyasa değeri", _kova("mcap", x["mcap_mlr"]) if piyasa == "bist" else None)
    ek("likidite (günlük ciro)", _kova("likit", x.get("likit_mn")) if piyasa == "bist" else None)
    for m in ("RSI-MACD", "Trend", "Hacim", "Dip"):
        if x[m] is not None: F.append(f"modül {m}={'+' if x[m] > 0 else '-' if x[m] < 0 else '0'}")
    F.append("radar uygun=" + ("evet" if x["uygun"] else "hayır")); F.append("günlük trend=" + ("yukarı" if x["g_trend"] else "aşağı"))
    if x["asiri"]: F.append("aşırı ısınma=evet")
    if x["sektor"]: F.append("sektör=" + x["sektor"])
    if x["katman"]: F.append("endeks=" + x["katman"])
    for w in (x["why"] or "").split("|"):
        if w: F.append("sinyal=" + ("hacimle yükseldi" if "hacimle yükseldi" in w else w))
    return F

def cmd_ogren(a):
    """Arşivdeki gözlemleri 2 işlem günü sonraki fiyatlarla eşleştirir; özellik bazında yükseliş (+%5) / düşüş (-%3) oranlarını biriktirir."""
    V = json.load(open(a.veri)); piyasa = a.piyasa
    L = V.setdefault("gozlem_lab", {}); P = L.setdefault(piyasa, {"islenen": [], "taban": {"n": 0, "yuk": 0, "dus": 0, "getiri": 0.0},
                                                                   "ozellik": {}, "hareketler": [], "bulgular": []})
    D = {}
    for f in sorted(os.listdir(a.arsiv)) if os.path.isdir(a.arsiv) else []:
        if f.startswith(f"gozlem_{piyasa}_") and f.endswith(".json"):
            G = json.load(open(os.path.join(a.arsiv, f))); D[G["tarih"]] = G
    gunler = sorted(D); bugun = simdi().strftime("%Y-%m-%d"); yeni = 0
    for i, gun in enumerate(gunler):
        G = D[gun]; C = G["cols"]
        if not G["taramalar"]: continue
        sonra = [g for g in gunler[i + 1:]]
        # 2 işlem günü tamamlanmış mı? (2. günün kapanış gözlemi var ya da o gün geçmiş)
        if len(sonra) < 2 or (sonra[1] == bugun and simdi().hour * 60 + simdi().minute < (1090 if piyasa == "bist" else 1380)): continue
        ufuk = sonra[:2]
        fiyat_serisi = {}
        for g2 in ufuk:
            for t in D[g2]["taramalar"]:
                for r in t["rows"]: fiyat_serisi.setdefault(r[0], []).append(r[1])
        son1 = {r[0]: r[1] for r in D[ufuk[0]]["taramalar"][-1]["rows"]}
        for etiket, tar in (("açılış", G["taramalar"][0]), ("kapanış", G["taramalar"][-1])):
            kimlik = f"{gun} {tar['saat']} {etiket}"
            if kimlik in P["islenen"] or (etiket == "kapanış" and len(G["taramalar"]) == 1 and f"{gun} {tar['saat']} açılış" in P["islenen"]): continue
            hareket = []
            for r in tar["rows"]:
                kod, f0 = r[0], r[1]; S = fiyat_serisi.get(kod)
                if not S or not f0: continue
                mx, mn, sn = max(S) / f0 - 1, min(S) / f0 - 1, S[-1] / f0 - 1
                yuk, dus = mx >= a.esik_yuk, mn <= -a.esik_dus
                b = P["taban"]; b["n"] += 1; b["yuk"] += yuk; b["dus"] += dus; b["getiri"] = round(b["getiri"] + sn, 4)
                for ft in _ozellikler(r, C, piyasa):
                    o = P["ozellik"].setdefault(ft, [0, 0, 0, 0.0]); o[0] += 1; o[1] += yuk; o[2] += dus; o[3] = round(o[3] + sn, 4)
                hareket.append((sn, mx, mn, r, son1.get(kod)))
            P["islenen"].append(kimlik); yeni += 1
            hareket.sort(key=lambda h: h[0])
            ozet_r = lambda h: {"kod": h[3][0], "getiri_2g": r2(h[0] * 100), "en_yuksek": r2(h[1] * 100), "en_dusuk": r2(h[2] * 100),
                                "giris": h[3][1], "ozellik": [f for f in _ozellikler(h[3], C, piyasa) if not f.startswith("sektör=")][:14],
                                "sektor": dict(zip(C, h[3])).get("sektor")}
            P["hareketler"].append({"gozlem": kimlik, "ufuk": ufuk, "yukselenler": [ozet_r(h) for h in hareket[::-1][:10]],
                                    "dusenler": [ozet_r(h) for h in hareket[:10]]})
    P["hareketler"] = P["hareketler"][-20:]; P["islenen"] = P["islenen"][-400:]
    # bulgular: taban orana göre en ayırt edici özellikler (n ≥ min_n)
    b = P["taban"]
    if b["n"]:
        ty, td = b["yuk"] / b["n"], b["dus"] / b["n"]; R = []
        for ft, (n, y, d, g) in P["ozellik"].items():
            if n < a.min_n: continue
            R.append({"ozellik": ft, "n": n, "yukselis": round(y / n, 3), "dusus": round(d / n, 3), "ort_getiri": round(g / n * 100, 2),
                      "kaldirac_yuk": round((y / n) / ty, 2) if ty else None, "kaldirac_dus": round((d / n) / td, 2) if td else None})
        P["tablo"] = sorted(R, key=lambda r: -(r["kaldirac_yuk"] or 0))
        P["bulgular"] = ([f"Yükseliş öncesi öne çıkan: {r['ozellik']} · +%{int(a.esik_yuk*100)} oranı %{r['yukselis']*100:.0f} (taban %{ty*100:.0f}, x{r['kaldirac_yuk']}) · n={r['n']}" for r in P["tablo"][:5]] +
                         [f"Düşüş öncesi öne çıkan: {r['ozellik']} · -%{int(a.esik_dus*100)} oranı %{r['dusus']*100:.0f} (taban %{td*100:.0f}, x{r['kaldirac_dus']}) · n={r['n']}"
                          for r in sorted(R, key=lambda r: -(r["kaldirac_dus"] or 0))[:5]])
        P["taban_oran"] = {"yukselis": round(ty, 3), "dusus": round(td, 3), "ort_getiri": round(b["getiri"] / b["n"] * 100, 2), "gozlem": b["n"]}
    if piyasa == "bist" and b["n"]:  # likidite eşiğini veriden öğren: zayıf kalan 20-50 / 50-100 mn bantları eşiğin altında bırakılır (taban 20 mn, tavan 100 mn)
        tg = b["getiri"] / b["n"]; bant = {}; mn = 20
        for ad, ust in (("20-50 mn", 50), ("50-100 mn", 100)):
            o = P["ozellik"].get("likidite (günlük ciro)=" + ad)
            if not o or o[0] < a.min_n: break
            zayif = (o[3] / o[0] < tg) and (o[2] / o[0] > b["dus"] / b["n"])
            bant[ad] = {"n": o[0], "yukselis": round(o[1] / o[0], 3), "dusus": round(o[2] / o[0], 3), "ort_getiri": round(o[3] / o[0] * 100, 2), "zayif": bool(zayif)}
            if zayif: mn = ust
            else: break
        Lk = V.setdefault("likidite", {}); eski = Lk.get("min", 20)
        Lk.update({"min": mn, "taban": 20, "tavan": 100, "guncelleme": simdi().strftime("%d.%m %H:%M"), "bantlar": bant, "katilim": LIK["katilim"]})
        if mn != eski: P["bulgular"].append(f"Likidite eşiği {eski} mn ₺ → {mn} mn ₺ (zayıf kalan sığ bant: ortalama getiri ve düşüş oranı tabanın kötüsü).")
    P["guncelleme"] = simdi().strftime("%d.%m %H:%M")
    json.dump(V, open(a.veri, "w"), ensure_ascii=False, separators=(",", ":"))
    son = P["hareketler"][-1] if P["hareketler"] else None
    yaz(a, f"ogren_{piyasa}.json", {"yeni_gozlem": yeni, "taban": P.get("taban_oran"), "bulgular": P["bulgular"], "son_hareket": son})
    print(f"ÖĞREN ({piyasa}): {yeni} yeni gözlem işlendi · toplam {b['n']} hisse-gözlem · arşiv günleri {gunler}")
    for x in P["bulgular"]: print("  ", x)
    if son and yeni:
        print("  Hareket kodları (haber için):", " ".join(h["kod"] for h in son["yukselenler"] + son["dusenler"]))


def _dm(s):
    """'16.11 10:00 mumu' -> (ay, gun, saat, dk) siralama anahtari"""
    m = re.search(r"(\d{2})\.(\d{2})(?:\s+(\d{1,2}):(\d{2}))?", str(s or ""))
    if not m: return (0, 0, 0, 0)
    return (int(m.group(2)), int(m.group(1)), int(m.group(3) or 0), int(m.group(4) or 0))

def cmd_kasa(a):
    """Sanal kasa: history kayitlarindaki sonuc ve fiyatlara gore acik pozisyonlari gunceller (satis), yeni secimleri alir.
    Kural: pozisyon = alim anindaki guncel toplam kasa degerinin %10'u (bilesik), en fazla 10 pozisyon, alim yalniz 10:00-18:00 taramalarinda, komisyon %0,1 (alis+satis).
    Cikis fiyati: hedef -> hedef; stop -> stop_cikis (yoksa kontrol_fiyat); kar korundu -> kar_koruma.fiyat; sure doldu/erken -> kontrol_fiyat."""
    d = json.load(open(a.veri)); K = d.get("kasa")
    for x_ in d.get("learning", []):  # öğrenme madde numaraları her zaman sayı (metin gelirse düzeltilir)
        try: x_["no"] = int(x_["no"])
        except Exception: pass
    if not K or "acik" not in K: print("KASA: kasa verisi yok"); return
    kom = K.get("komisyon", .001); bas = K.get("baslangic", 100000); poz = bas * K.get("pozisyon_orani", .1)
    H = {(r["kod"], r["tarama"]): r for r in d.get("history", [])}
    ILK = {}; gor_ = set()  # ilk kez seçilen hisse: geçmişte daha önce hiç seçilmemiş
    for r_ in sorted(d.get("history", []), key=lambda r: _dm(r["tarama"])):
        if r_["kod"] not in gor_: ILK[(r_["kod"], r_["tarama"])] = True; gor_.add(r_["kod"])
    islenen = set(K.get("islenen", []))
    son = _dm((K.get("ozet") or {}).get("tarih"))
    if not islenen:
        for p_ in K["acik"] + K["kapanan"]: islenen.add(p_["kod"] + "|" + p_["tarama"])
        for h in K.get("son_hareket", []):
            if h.get("tarama"): islenen.add(h["kod"] + "|" + h["tarama"])
        for r in d.get("history", []):
            if _dm(r["tarama"]) <= son: islenen.add(r["kod"] + "|" + r["tarama"])
    for p_ in K["acik"]:  # alim boyutu icin acik pozisyonlari guncel fiyatla degerle (bilesik getiri)
        r_ = H.get((p_["kod"], p_["tarama"])) or {}
        f_ = r_.get("kontrol_fiyat") if r_.get("kontrol_fiyat") is not None else (p_["giris"] * (1 + r_["degisim"]) if r_.get("degisim") is not None else None)
        if f_ is not None: p_["deger"] = round(p_["adet"] * f_, 2)
    olaylar = []
    for p_ in K["acik"]:
        r = H.get((p_["kod"], p_["tarama"]))
        if r and r["sonuc"] != "Bekliyor":
            sn = r["sonuc"]
            if sn == "Başarılı": cik, tur, zaman = p_["hedef"], "hedef", r.get("hedef_tarih") or r.get("kontrol")
            elif sn == "Stop": cik, tur, zaman = r.get("stop_cikis") or r.get("kontrol_fiyat") or p_["stop"], "stop", r.get("stop_tarih") or r.get("kontrol")
            elif sn == "Kâr korundu":
                kk = r.get("kar_koruma") or {}; cik = kk.get("fiyat") or r.get("kontrol_fiyat"); tur, zaman = "kâr korundu", kk.get("zaman") or r.get("kontrol")
            else: cik, tur, zaman = r.get("kontrol_fiyat") or p_["giris"], ("süre doldu" if sn == "Başarısız" else "erken kapandı"), r.get("bitis") and (r["bitis"] + " 18:00") or r.get("kontrol")
            olaylar.append((_dm(zaman), 0, "sat", p_, cik, tur, zaman))
    for r in d.get("history", []):
        k = r["kod"] + "|" + r["tarama"]
        if k in islenen: continue
        olaylar.append((_dm(r["tarama"]), 1, "al", r, None, None, r["tarama"]))
        islenen.add(k)
    olaylar.sort(key=lambda e: (e[0], e[1], 0 if (e[2] == "al" and not ILK.get((e[3]["kod"], e[3]["tarama"]))) else 1))
    hareket = []
    for _, _, tip, x, cik, tur, zaman in olaylar:
        if tip == "sat":
            if x not in K["acik"]: continue
            K["acik"].remove(x); gel = x["adet"] * cik * (1 - kom); K["nakit"] = round(K["nakit"] + gel, 2)
            kt = round(gel - x["maliyet"], 2)
            h = {"kod": x["kod"], "tarama": x["tarama"], "adet": x["adet"], "giris": x["giris"], "cikis": cik, "tur": tur, "alindi": x.get("alindi"), "maliyet": x["maliyet"], "kar_tl": kt, "kar_yuzde": round(kt / x["maliyet"], 4), "kapanis": zaman}
            K["kapanan"].append(h); hareket.append(dict(h, islem="sat"))
        else:
            hm = _dm(x["tarama"]); saat = hm[2] * 60 + hm[3]
            if not (600 <= saat <= 1080): hareket.append({"islem": "atlandı", "kod": x["kod"], "tarama": x["tarama"], "neden": "seans dışı (10:00-18:00 dışı alım yapılmaz)"}); continue
            ilk_ = ILK.get((x["kod"], x["tarama"]))
            if ilk_ and saat < 720: hareket.append({"islem": "atlandı", "kod": x["kod"], "tarama": x["tarama"], "neden": "ilk kez seçilen hisse 10:00-11:59 arası alınmaz (canlı veride isabet %40, stop %52)"}); continue
            if any(p_["kod"] == x["kod"] for p_ in K["acik"]): hareket.append({"islem": "atlandı", "kod": x["kod"], "tarama": x["tarama"], "neden": "zaten açık pozisyon"}); continue
            if len(K["acik"]) >= PORTFOY_MAX: hareket.append({"islem": "takipte", "kod": x["kod"], "tarama": x["tarama"], "neden": "portföy dolu, alım kararı verilmedi: takipte bekliyor (daha iyi olursa değiştirilir)"}); continue
            eq = K["nakit"] + sum((q.get("deger") or q.get("maliyet") or 0) for q in K["acik"]); poz = round(eq * K.get("pozisyon_orani", .1), 2)  # bilesik: guncel toplam degerin %10'u
            kap = x.get("kapasite_tl")  # likidite kapasitesi: pozisyon günlük cironun %1'ini aşmaz; sığ hisse alınmaz
            if x.get("derinlik") == "Sığ": hareket.append({"islem": "atlandı", "kod": x["kod"], "tarama": x["tarama"], "neden": "sığ hisse (günlük ciro eşik altı)"}); continue
            kisit = bool(kap and poz > kap)
            if kisit: poz = float(kap)
            adet = int(poz / (x["giris"] * (1 + kom)))
            mal = round(adet * x["giris"] * (1 + kom), 2)
            if adet < 1 or mal > K["nakit"]: hareket.append({"islem": "takipte", "kod": x["kod"], "tarama": x["tarama"], "neden": "nakit yetersiz, takipte bekliyor"}); continue
            K["nakit"] = round(K["nakit"] - mal, 2)
            p_ = {"kod": x["kod"], "tarama": x["tarama"], "adet": adet, "giris": x["giris"], "maliyet": mal, "hedef": x.get("hedef") or round(x["giris"] * 1.05, 2), "stop": x["stop"], "likit_mn": x.get("likit_mn"), "derinlik": x.get("derinlik"), "kapasite_tl": kap, "kapasite_siniri": kisit}
            K["acik"].append(p_); hareket.append(dict(p_, islem="al"))
    # TAKİP -> PORTFÖY: takip = alım kararı verilmemiş, izlenen adaylar; boş yer varsa en iyi aday alınır, yoksa portföydeki en zayıftan belirgin iyiyse onunla değiştirilir
    SK = (d.get("kalite_kapisi") or {}).get("skor") or {}; MARJ = .25; DEG = 0; DEG_MAX = 2; hm_ = simdi(); sa_ = hm_.hour * 60 + hm_.minute
    def _fy(p_):
        r_ = H.get((p_["kod"], p_["tarama"])) or {}
        return r_.get("kontrol_fiyat") if r_.get("kontrol_fiyat") is not None else (p_["giris"] * (1 + r_["degisim"]) if r_.get("degisim") is not None else p_["giris"])
    if SK and 600 <= sa_ <= 1080:
        tut = {p_["kod"] for p_ in K["acik"]}; ad_ = {}
        for r_ in d.get("history", []):
            if r_.get("sonuc") != "Bekliyor" or r_["kod"] in tut or r_["kod"] not in SK or r_.get("derinlik") == "Sığ": continue
            if (r_["kod"] not in ad_) or _dm(r_["tarama"]) > _dm(ad_[r_["kod"]]["tarama"]): ad_[r_["kod"]] = r_
        adaylar_ = sorted(ad_.values(), key=lambda r_: -SK[r_["kod"]])
        for r_ in adaylar_:
            fy = r_.get("kontrol_fiyat") or r_["giris"]
            hd_ = r_.get("hedef") or round(r_["giris"] * 1.05, 2)
            if fy >= hd_ or fy <= r_["stop"]: continue
            if ILK.get((r_["kod"], r_["tarama"])) and sa_ < 720: continue
            sebep = None
            if len(K["acik"]) >= PORTFOY_MAX:
                pu = [p_ for p_ in K["acik"] if p_["kod"] in SK]
                if not pu: break
                w = min(pu, key=lambda p_: SK[p_["kod"]])
                if SK[r_["kod"]] - SK[w["kod"]] < MARJ or DEG >= DEG_MAX: break   # çalışma başına en fazla 2 değiştirme (komisyon ve gereksiz hareket sınırı)
                DEG += 1
                fw = _fy(w); gel = w["adet"] * fw * (1 - kom); K["acik"].remove(w); K["nakit"] = round(K["nakit"] + gel, 2); kt = round(gel - w["maliyet"], 2)
                hw = H.get((w["kod"], w["tarama"]))
                if hw and hw.get("sonuc") == "Bekliyor": hw["sonuc"] = "Erken kapandı"; hw["kontrol_fiyat"] = fw; hw["degisim"] = round(fw / w["giris"] - 1, 4)
                h = {"kod": w["kod"], "tarama": w["tarama"], "adet": w["adet"], "giris": w["giris"], "cikis": fw, "tur": "değiştirildi", "alindi": w.get("alindi"), "maliyet": w["maliyet"], "kar_tl": kt, "kar_yuzde": round(kt / w["maliyet"], 4), "kapanis": zm_ if (zm_ := hm_.strftime("%d.%m %H:%M")) else ""}
                K["kapanan"].append(h); hareket.append(dict(h, islem="sat", neden=f"takipteki {r_['kod']} (skor {SK[r_['kod']]}) portföydeki {w['kod']} (skor {SK[w['kod']]}) hissesinden daha iyi"))
            eq = K["nakit"] + sum((q.get("deger") or q.get("maliyet") or 0) for q in K["acik"]); poz = round(eq * K.get("pozisyon_orani", .1), 2)
            kap = r_.get("kapasite_tl"); kisit = bool(kap and poz > kap)
            if kisit: poz = float(kap)
            adet = int(poz / (fy * (1 + kom))); mal = round(adet * fy * (1 + kom), 2)
            if adet < 1 or mal > K["nakit"]: continue
            K["nakit"] = round(K["nakit"] - mal, 2)
            p_ = {"kod": r_["kod"], "tarama": r_["tarama"], "adet": adet, "giris": fy, "maliyet": mal, "hedef": hd_, "stop": r_["stop"], "likit_mn": r_.get("likit_mn"), "derinlik": r_.get("derinlik"), "kapasite_tl": kap, "kapasite_siniri": kisit, "alindi": hm_.strftime("%d.%m %H:%M")}
            K["acik"].append(p_); hareket.append(dict(p_, islem="al", neden="takipten alındı (alım kararı)"))
            H[(p_["kod"], p_["tarama"])] = r_
    toplam_acik = 0; ak = 0
    for p_ in K["acik"]:
        r = H.get((p_["kod"], p_["tarama"])) or {}
        f = r.get("kontrol_fiyat") if r.get("kontrol_fiyat") is not None else (p_["giris"] * (1 + r["degisim"]) if r.get("degisim") is not None else p_["giris"])
        p_["fiyat"] = f; p_["deger"] = round(p_["adet"] * f, 2); p_["kar_tl"] = round(p_["deger"] * (1 - kom) - p_["maliyet"], 2); p_["kar_yuzde"] = round(p_["kar_tl"] / p_["maliyet"], 4)
        toplam_acik += p_["deger"]; ak += p_["kar_tl"]
    ger = round(sum(k["kar_tl"] for k in K["kapanan"]), 2); top = round(K["nakit"] + toplam_acik, 2)
    zm = simdi().strftime("%d.%m %H:%M")
    K["ozet"] = {"tarih": zm, "toplam": top, "nakit": K["nakit"], "acik_deger": round(toplam_acik, 2), "acik_sayi": len(K["acik"]), "acik_kar_tl": round(ak, 2), "gerceklesen_tl": ger, "gerceklesen_yuzde": round(ger / bas, 4), "toplam_kar_tl": round(top - bas, 2), "toplam_kar_yuzde": round((top - bas) / bas, 4), "islem": len(K["kapanan"]), "kazanan": sum(1 for k in K["kapanan"] if k["kar_tl"] > 0), "kaybeden": sum(1 for k in K["kapanan"] if k["kar_tl"] <= 0)}
    # gunluk seyir: her gunun son degeri (kapanis) tutulur; gunluk degisim = simdiki toplam - onceki gunun kapanisi
    g_ = K.setdefault("gunluk", []); gun_ = zm.split()[0]
    if g_ and g_[-1]["gun"] == gun_: g_[-1]["kapanis"] = top
    else: g_.append({"gun": gun_, "kapanis": top})
    K["gunluk"] = g_[-60:]
    onc_ = [e for e in K["gunluk"] if e["gun"] != gun_]
    if onc_:
        ob_ = onc_[-1]["kapanis"]; K["ozet"]["gun_oncesi"] = ob_; K["ozet"]["gun_oncesi_tarih"] = onc_[-1]["gun"]
        K["ozet"]["gun_kar_tl"] = round(top - ob_, 2); K["ozet"]["gun_yuzde"] = round((top - ob_) / ob_, 4)
    try:  # laboratuvar ileri testi (tarihsel, stopsuz +%5 vurma) ile canlı sonucun yan yana kıyası
        Hs = [h for h in d.get("history", []) if h.get("sonuc") != "Bekliyor" and not (h["sonuc"] == "Erken kapandı" and h.get("degisim") is None)]
        if Hs and (d.get("lab_ozellik") or {}).get("model"):
            ok_ = sum(1 for h in Hs if h["sonuc"] in ("Başarılı", "Kâr korundu") or (h["sonuc"] == "Erken kapandı" and h["degisim"] > 0))
            d["lab_ozellik"]["model"]["canli_kiyas"] = {"n": len(Hs), "isabet": round(ok_ / len(Hs), 3), "stop": round(sum(1 for h in Hs if h["sonuc"] == "Stop") / len(Hs), 3),
                "guncelleme": zm, "not": "ileri_test: tarihsel 60 gün, +%5'e değme oranı (stop kuralı ve gap kaybı uygulanmaz). Canlı: gerçek saatlik stop, gap ve komisyonlu sonuç. İkisi aynı ölçü değildir; kararlar canlı sonuca göre verilir."}
    except Exception: pass
    if hareket: K["son_hareket"] = (hareket + K.get("son_hareket", []))[:60]
    K["islenen"] = sorted(islenen)[-600:]
    json.dump(d, open(a.veri, "w"), ensure_ascii=False)
    print("KASA: toplam %.2f (%+.2f%%) · nakit %.2f · %d açık · %d işlem · bu çalışmada %d hareket" % (top, (top - bas) / bas * 100, K["nakit"], len(K["acik"]), len(K["kapanan"]), len(hareket)))
    for h in hareket: print("  ", h["islem"], h["kod"], h.get("tur") or h.get("neden") or "", h.get("kar_tl", ""))

# ---------------------------------------------------------------- Özellik laboratuvarı (her grafik taramasından sonra)
OZ_ACIKLAMA = {}


# Yeni formasyon havuzu: her turda sıradaki 3 tanesi deneme listesine eklenir ve geçmiş 2 yıl üzerinde geriye dönük ölçülür (sürekli üstüne koyarak büyür).
def _ek(ad, acik, fn): OZ_EKSTRA[ad] = (acik, fn); OZ_SIRA.append(ad)
OZ_EKSTRA = {}; OZ_SIRA = []
_ek("yutan_mum", "Yükselen yutan mum (önceki kırmızı mumu tamamen yuttu)", lambda X: X["C"][X["i"]] > X["O"][X["i"]] and X["C"][X["i"]-1] < X["O"][X["i"]-1] and X["C"][X["i"]] >= X["O"][X["i"]-1] and X["O"][X["i"]] <= X["C"][X["i"]-1])
_ek("cekic_mumu", "Çekiç mumu: uzun alt gölge (gövdenin 2 katı), yeşil kapanış", lambda X: X["C"][X["i"]] > X["O"][X["i"]] and (min(X["O"][X["i"]], X["C"][X["i"]]) - X["L"][X["i"]]) > 2 * (X["C"][X["i"]] - X["O"][X["i"]]))
_ek("donchian20_kirilim", "20 günlük zirve yukarı kırıldı", lambda X: X["c"] > max(X["H"][X["i"]-20:X["i"]]))
_ek("zirve52h_yakin", "52 hafta zirvesine %3'ten yakın kapanış", lambda X: X["c"] >= .97 * max(X["H"][max(0, X["i"]-251):X["i"]+1]))
_ek("ema9_20_kesisim", "EMA9, EMA20'yi bugün yukarı kesti", lambda X: X["e9"][X["i"]] > X["e20"][X["i"]] and X["e9"][X["i"]-1] <= X["e20"][X["i"]-1])
_ek("rsi_30_donus", "RSI 30 altından yukarı döndü", lambda X: X["rsi"][X["i"]-1] is not None and X["rsi"][X["i"]-1] < 30 and X["rsi"][X["i"]] > X["rsi"][X["i"]-1])
_ek("bollinger_ust_kirilim", "Kapanış Bollinger (20,2) üst bandının üstünde", lambda X: X["c"] > X["s20"][X["i"]] + 2 * X["sd20"][X["i"]])
_ek("ema200_ustu", "Fiyat EMA200'ün üstünde", lambda X: X["c"] > X["e200"][X["i"]])
_ek("macd_pozitif", "MACD sıfırın ve sinyal çizgisinin üstünde", lambda X: X["macd"][X["i"]] > 0 and X["macd"][X["i"]] > X["sig"][X["i"]])
_ek("dusuk_hacimli_artis", "Düşük hacimle (ortalamanın yarısından az) yükseliş", lambda X: X["av20"] and X["V"][X["i"]] < .5 * X["av20"] and X["chg"] > 0)
_ek("5_kirmizi_sonrasi_yesil", "5 kırmızı mum sonrası yeşil kapanış", lambda X: all(X["C"][k] < X["O"][k] for k in range(X["i"]-5, X["i"])) and X["C"][X["i"]] > X["O"][X["i"]])
_ek("ardisik_2_guclu_gun", "İki gün üst üste +%4 üstü yükseliş", lambda X: X["chg"] >= .04 and X["C"][X["i"]-1] / X["C"][X["i"]-2] - 1 >= .04)
_ek("10_gun_dip_testi", "Son 10 günün dibini test edip yeşil kapanış", lambda X: X["L"][X["i"]] <= min(X["L"][X["i"]-10:X["i"]]) * 1.005 and X["C"][X["i"]] > X["O"][X["i"]])
_ek("aralik_daralmasi", "Son 5 günün ortalama aralığı 20 günlüğün yarısından dar (sıkışma)", lambda X: sum(X["rng"][X["i"]-4:X["i"]+1]) / 5 < .5 * sum(X["rng"][X["i"]-19:X["i"]+1]) / 20)
_ek("hacimli_orta_ustu_kapanis", "Kapanış günün orta noktasının üstünde ve hacim 1,5 kat", lambda X: X["av20"] and X["c"] > (X["H"][X["i"]] + X["L"][X["i"]]) / 2 and X["V"][X["i"]] >= 1.5 * X["av20"])
_ek("ic_mum", "İç mum: günün aralığı önceki günün aralığının içinde", lambda X: X["H"][X["i"]] <= X["H"][X["i"]-1] and X["L"][X["i"]] >= X["L"][X["i"]-1])
for _k in (55, 60, 65, 70, 75): _ek(f"rsi_{_k}_ustu", f"Günlük RSI {_k} üstü", (lambda k: lambda X: X["rsi"][X["i"]] is not None and X["rsi"][X["i"]] > k)(_k))
for _k in (3, 4, 5, 6): _ek(f"hacim_{_k}x_yukselis", f"Hacim ortalamanın {_k} katı ve yükseliş günü", (lambda k: lambda X: X["av20"] and X["V"][X["i"]] >= k * X["av20"] and X["chg"] > 0)(_k))
for _k in (4, 5, 7, 8): _ek(f"gun_{_k}_ustu_yukselis", f"Gün içi +%{_k} üstü yükseliş", (lambda k: lambda X: X["chg"] >= k / 100)(_k))
for _k in (2, 3, 4): _ek(f"atr_{_k}_{_k+1}_bandi", f"Günlük ortalama oynaklık (ATR) %{_k}-%{_k+1} bandında", (lambda k: lambda X: X["atr"][X["i"]] and k / 100 <= X["atr"][X["i"]] / X["c"] < (k + 1) / 100)(_k))
for _k in (2, 3, 5): _ek(f"{_k}_gun_ust_uste_artis", f"Üst üste {_k} gün yükselen kapanış", (lambda k: lambda X: all(X["C"][X["i"]-j] > X["C"][X["i"]-j-1] for j in range(k)))(_k))

def _oz_gunluk(kod):
    """Yahoo günlük mumlar (2 yıl): (t, a, h, l, c, v) listesi."""
    for host in ("query1", "query2"):
        try:
            j = http(f"https://{host}.finance.yahoo.com/v8/finance/chart/{kod}.IS?range=2y&interval=1d", deneme=2, bekle=1.5)
            r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
            M = [(t, o, h, l, c, v or 0) for t, o, h, l, c, v in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if None not in (o, h, l, c)]
            if len(M) > 160: return M
        except Exception: continue
    return None

def _gunluk_hepsi(kodlar, yol="gunluk_onbellek.pkl", dk=45):
    """Günlük grafik önbelleği: aynı çalışmada (egit, adaylar, ozlab) 600 hissenin grafiği bir kez indirilir."""
    import pickle
    from concurrent.futures import ThreadPoolExecutor
    try:
        if os.path.exists(yol) and time.time() - os.path.getmtime(yol) < dk * 60:
            C = pickle.load(open(yol, "rb"))
            if all(k in C for k in kodlar): return {k: C[k] for k in kodlar if C.get(k)}
    except Exception: pass
    with ThreadPoolExecutor(max_workers=12) as ex: R = list(ex.map(_oz_gunluk, kodlar))
    C = {k: M for k, M in zip(kodlar, R) if M}
    try: pickle.dump(C, open(yol, "wb"))
    except Exception: pass
    return C

def _ema(x, n):
    k = 2 / (n + 1); o = []; e = None
    for v in x:
        e = v if e is None else e + k * (v - e); o.append(e)
    return o

def _wilder(x, n):
    o = [None] * len(x)
    if len(x) < n: return o
    s = sum(x[:n]); o[n - 1] = s / n
    for i in range(n, len(x)): o[i] = (o[i - 1] * (n - 1) + x[i]) / n
    return o

def _oz_ozellikler(M, extra=(), canli=False):
    """Her gün için özellik kümesi ve +%5 / stop sonucu. Döner: [(gün_idx, tarih, {özellik: bool}, sonuc)]  sonuc: 'h' hedef, 's' stop, 'n' ikisi de değil."""
    n = len(M); O = [m[1] for m in M]; Hh = [m[2] for m in M]; L = [m[3] for m in M]; C = [m[4] for m in M]; V = [m[5] for m in M]
    tr = [max(Hh[i] - L[i], abs(Hh[i] - C[i - 1]), abs(L[i] - C[i - 1])) if i else Hh[i] - L[i] for i in range(n)]
    atr = _wilder(tr, 14)
    pdm = [max(Hh[i] - Hh[i - 1], 0) if (Hh[i] - Hh[i - 1] > L[i - 1] - L[i]) else 0 for i in range(1, n)]; pdm = [0] + pdm
    mdm = [max(L[i - 1] - L[i], 0) if (L[i - 1] - L[i] > Hh[i] - Hh[i - 1]) else 0 for i in range(1, n)]; mdm = [0] + mdm
    sp, sm, st_ = _wilder(pdm, 14), _wilder(mdm, 14), atr
    pdi = [100 * sp[i] / st_[i] if st_[i] else None for i in range(n)]; mdi = [100 * sm[i] / st_[i] if st_[i] else None for i in range(n)]
    dx = [abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) * 100 if pdi[i] is not None and (pdi[i] + mdi[i]) else 0 for i in range(n)]
    adx = _wilder(dx, 14)
    e12, e26 = _ema(C, 12), _ema(C, 26); macd = [a - b for a, b in zip(e12, e26)]; sig = _ema(macd, 9)
    e20, e50 = _ema(C, 20), _ema(C, 50)
    g = [max(C[i] - C[i - 1], 0) if i else 0 for i in range(n)]; z = [max(C[i - 1] - C[i], 0) if i else 0 for i in range(n)]
    ag, az = _wilder(g, 14), _wilder(z, 14); rsi = [100 - 100 / (1 + ag[i] / az[i]) if ag[i] is not None and az[i] else (100 if ag[i] else None) for i in range(n)]
    obv = [0.0] * n
    for i in range(1, n): obv[i] = obv[i - 1] + (V[i] if C[i] > C[i - 1] else -V[i] if C[i] < C[i - 1] else 0)
    mfv = [((C[i] - L[i]) - (Hh[i] - C[i])) / (Hh[i] - L[i]) * V[i] if Hh[i] > L[i] else 0 for i in range(n)]
    # supertrend (10,3)
    atr10 = _wilder(tr, 10); fu = [None] * n; fl = [None] * n; trend = [1] * n
    for i in range(10, n):
        mid = (Hh[i] + L[i]) / 2; bu, bl = mid + 3 * atr10[i], mid - 3 * atr10[i]
        pu, pl = fu[i - 1], fl[i - 1]
        fu[i] = bu if (pu is None or bu < pu or C[i - 1] > pu) else pu
        fl[i] = bl if (pl is None or bl > pl or C[i - 1] < pl) else pl
        if pu is None: trend[i] = 1
        elif trend[i - 1] == -1 and C[i] > fu[i]: trend[i] = 1
        elif trend[i - 1] == 1 and C[i] < fl[i]: trend[i] = -1
        else: trend[i] = trend[i - 1]
    e9, e200 = _ema(C, 9), _ema(C, 200)
    s20 = [None] * n; sd20 = [None] * n
    for k in range(19, n):
        w = C[k - 19:k + 1]; m = sum(w) / 20; s20[k] = m; sd20[k] = (sum((x - m) ** 2 for x in w) / 20) ** .5
    rng = [Hh[k] - L[k] for k in range(n)]
    out = []
    for i in (range(n - 1, n) if canli else range(130, n - 2)):
        c, pc = C[i], C[i - 1]; chg = c / pc - 1
        av20 = sum(V[i - 20:i]) / 20 if i >= 20 else 0
        bw = []
        for k in range(i - 119, i + 1):
            w = C[k - 19:k + 1]; m = sum(w) / 20; sd = (sum((x - m) ** 2 for x in w) / 20) ** .5; bw.append(4 * sd / m if m else 9)
        ich = None
        if i >= 78:
            j = i - 26; t9 = (max(Hh[j - 8:j + 1]) + min(L[j - 8:j + 1])) / 2; k26 = (max(Hh[j - 25:j + 1]) + min(L[j - 25:j + 1])) / 2
            sa = (t9 + k26) / 2; sb = (max(Hh[j - 51:j + 1]) + min(L[j - 51:j + 1])) / 2; ich = c > max(sa, sb)
        cmf = sum(mfv[i - 19:i + 1]) / (sum(V[i - 19:i + 1]) or 1)
        F = {
            "adx_guclu_yukari": bool(adx[i] and adx[i] > 25 and pdi[i] > mdi[i]),
            "bollinger_sikisma": bw[-1] <= min(bw) * 1.1,
            "bosluklu_acilis": O[i] / pc - 1 >= .03,
            "cmf_pozitif": cmf > 0,
            "dipte_macd": bool(macd[i] < 0 and macd[i] - sig[i] > 0 and macd[i - 1] - sig[i - 1] <= 0),
            "dunku_yukselis_ertesi": C[i - 1] / C[i - 2] - 1 >= .06,
            "dusuk_oynaklik": bool(atr[i] and atr[i] / c < .03),
            "gun_ici_6_ustu": chg >= .06,
            "hacim2x_artida": bool(av20 and V[i] >= 2 * av20 and chg > 0),
            "hacimsiz_bekleyis": bool(av20 and V[i] < av20 and abs(chg) < .01),
            "ichimoku_bulut_ustu": bool(ich),
            "kilitli_tavan": chg >= .095 and c >= Hh[i] * .9995,
            "rsi_80_ustu": bool(rsi[i] and rsi[i] > 80),
            "supertrend_gunluk_yukari": trend[i] == 1,
            "tavan": chg >= .095,
            "yuksek_oynaklik": bool(atr[i] and atr[i] / c > .06),
            "gun_3_6": .03 <= chg < .06,
            "gun_yuksegi_kapanis": Hh[i] > L[i] and (c - L[i]) / (Hh[i] - L[i]) >= .9,
            "ema20_50_trend": e20[i] > e50[i],
            "obv_artiyor": obv[i] > obv[i - 20],
            "3_yesil_mum": all(C[k] > O[k] for k in (i, i - 1, i - 2)),
            "zirveden_50_asagi": c < .5 * max(Hh[max(0, i - 251):i + 1]),
        }
        if extra:
            X = dict(i=i, n=n, O=O, H=Hh, L=L, C=C, V=V, c=c, pc=pc, chg=chg, av20=av20, e9=e9, e20=e20, e200=e200, rsi=rsi, macd=macd, sig=sig, s20=s20, sd20=sd20, rng=rng, atr=atr)
            for ad in extra:
                fn = OZ_EKSTRA.get(ad)
                try: F[ad] = bool(fn[1](X)) if fn else False
                except Exception: F[ad] = False
        hed = c * 1.05; stp = c * .97; sonuc = "n"
        for d in (() if canli else (1, 2)):
            if Hh[i + d] >= hed: sonuc = "h"; break
            if C[i + d] <= stp: sonuc = "s"; break
        out.append((i, time.strftime("%Y-%m-%d", time.gmtime(M[i][0])), F, sonuc, chg))
    return out

# ---------------------------------------------------------------- Kalite kapısı (öğrenilmiş sıralama modeli, MOTOR.md §16)
STOP_TAVAN = 0.025   # 17.11: %3 → %2,5 (ileri doğru test: sabit %2-2,5 stop, %3'e göre işlem başına ortalama getiriyi artırıyor; MOTOR.md §16). Veri destekledikçe adım adım daraltılır, alt sınır %1.

def _oz_vektor(M, F, gen, i=None):
    """Günlük mum serisi M, bar i (varsayılan son bar), özellik bayrakları F ve piyasa genişliği → {özellik: sayı}. Eğitim (egit.py) ve canlı tarama aynı fonksiyonu kullanır."""
    n = len(M); i = n - 1 if i is None else i
    C = [m[4] for m in M]; O = [m[1] for m in M]; Hh = [m[2] for m in M]; L = [m[3] for m in M]; V = [m[5] for m in M]
    av = sum(V[i - 20:i]) / 20
    rec = {k: float(bool(v)) for k, v in F.items() if k not in ("zayif_piyasa", "guclu_piyasa")}
    rec.update(chg=C[i] / C[i - 1] - 1, rv=(V[i] / av) if av > 0 else float("nan"), gap=O[i] / C[i - 1] - 1,
               pos=(C[i] - L[i]) / (Hh[i] - L[i]) if Hh[i] > L[i] else .5, r5=C[i] / C[i - 5] - 1, r20=C[i] / C[i - 20] - 1,
               zv=C[i] / max(Hh[max(0, i - 251):i + 1]) - 1, rg=(Hh[i] - L[i]) / C[i], lt=math.log(max(V[i] * C[i], 1)), genislik=gen)
    return rec

def _agac_tahmin(model, rec):
    """Dışa aktarılmış gradyan artırma modeli (model.json) için saf Python değerlendirici."""
    x = [rec.get(a, float("nan")) for a in model["names"]]; t = model["base"]
    for ag in model["trees"]:
        k = 0
        while True:
            nd = ag[k]
            if nd[0] < 0: t += nd[1]; break
            v = x[nd[0]]
            k = nd[3] if (v != v and nd[4] == 1) else nd[5] if v != v else (nd[3] if v <= nd[2] else nd[5])
    return t

def cmd_ozlab(a):
    """Özellik laboratuvarı (birikimli): tüm BIST hisselerinin 2 yıllık günlük grafiğinde her özelliğin +%5 (2 işlem günü) / stop oranını ölçer.
    Her grafik taramasından sonra otomatik çalışır (adaylar komutu çağırır). Sayaçlar (grafik, örnek, özellik) her turda ÜSTÜNE EKLENİR; her turda 3 yeni formasyon denenir.
    Aynı gün-hisse örneği ikinci kez sayılmaz (özellik başına işlenen son gün tutulur); yeni eklenen özellik tüm geçmiş üzerinde bir kez geriye dönük ölçülür."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time(); V = json.load(open(a.veri)); LO = V.setdefault("lab_ozellik", {})
    kodlar = []
    if a.girdi and os.path.exists(a.girdi):
        try: kodlar = sorted({s["kod"] for s in json.load(open(a.girdi)).get("tum", [])})
        except Exception: kodlar = []
    if not kodlar and os.path.isdir(a.arsiv):
        fs = sorted(f for f in os.listdir(a.arsiv) if f.startswith("gozlem_bist_") and f.endswith(".json"))
        if fs:
            G = json.load(open(os.path.join(a.arsiv, fs[-1]))); T = (G.get("taramalar") or [{}])[-1]
            kodlar = sorted({r[0] for r in T.get("rows", [])})
    if not kodlar:
        print("ÖZLAB: hisse listesi bulunamadı (cikti/bist.json ya da arsiv/gozlem_bist_*.json yok), atlandı"); return
    # birikim durumu (ilk çalışmada eski laboratuvarın son bilinen toplamları taban alınır: tur 18, 1.869 grafik, 287.785 örnek, 497 özellik)
    B = LO.setdefault("birikim", {"grafik": 1869, "ornek": 287785, "ozellik": 497, "tur": 18, "son": None, "N": 0, "H": 0, "S": 0, "yeni_formasyon": []})
    eski = {o["ad"]: o for o in LO.get("ozellikler", [])}
    for o in eski.values():
        if "_son" not in o and o.get("_n") is None: o["_n"] = o["_h"] = o["_s"] = 0; o["_son"] = None; o["_olculdu"] = False
    # yeni formasyonları etkinleştir (her tur 3)
    yeni_eklenen = []
    for ad in OZ_SIRA:
        if len(yeni_eklenen) >= 3: break
        if ad not in eski:
            eski[ad] = {"ad": ad, "aciklama": OZ_EKSTRA[ad][0], "durum": "test", "yeni": True, "_n": 0, "_h": 0, "_s": 0, "_son": None}
            yeni_eklenen.append(ad); B["yeni_formasyon"].append(ad)
    ok = list(_gunluk_hepsi(kodlar).items())
    if len(ok) < 50:
        print(f"ÖZLAB: yalnızca {len(ok)} grafik alınabildi, önceki sonuçlar korundu"); return
    ekstra = [ad for ad in eski if ad in OZ_EKSTRA]
    tum = []; adv = {}
    for k, M in ok:
        for i, tarih, F, so, chg in _oz_ozellikler(M, ekstra):
            tum.append((tarih, F, so, chg)); adv.setdefault(tarih, [0, 0]); adv[tarih][0] += chg > 0; adv[tarih][1] += 1
    gunler = set(); yeniN = 0
    for tarih, F, so, chg in tum:
        a_, t_ = adv[tarih]; oran = a_ / t_ if t_ else .5
        F["zayif_piyasa"] = oran < .35; F["guclu_piyasa"] = oran > .6
        gunler.add(tarih)
        if B["son"] is None or tarih > B["son"]:
            B["N"] += 1; B["H"] += so == "h"; B["S"] += so == "s"; yeniN += 1
        for ad, v in F.items():
            o = eski.get(ad)
            if o is None or not v: continue
            if o.get("_son") is None or tarih > o["_son"]:
                o["_n"] += 1; o["_h"] += so == "h"; o["_s"] += so == "s"
    son_gun = max(gunler)
    for ad, o in eski.items():
        if ad in {f for f in (tum[0][1] if tum else {})}: o["_son"] = son_gun; o["_olculdu"] = True
    B["son"] = son_gun
    taban = B["H"] / B["N"] if B["N"] else 0
    yeni_liste = []
    for ad, o in eski.items():
        n_ = o.get("_n") or 0
        if n_ <= 0: continue
        oran = o["_h"] / n_; fark = oran - taban; d0 = o.get("durum")
        if n_ < 100: d1 = "az örnek"
        elif fark <= -.04: d1 = "elendi"
        elif d0 == "kullaniliyor": d1 = "kullaniliyor"
        else: d1 = "test"
        if d0 != d1 and d0 not in (None,): o["degisim"] = f"{d0} → {d1}"; yeni_liste.append(ad)
        o.update({"durum": d1, "oran": round(oran, 3), "stop": round(o["_s"] / n_, 3), "fark": round(fark, 3), "ornek": n_})
    aday = [ad for ad, o in eski.items() if (o.get("ornek") or 0) >= 300 and (o.get("fark") or 0) >= .10 and o.get("durum") != "kullaniliyor"]
    LO["ozellikler"] = list(eski.values()); LO["taban"] = round(taban, 3)
    sayac = {"kullaniliyor": 0, "test": 0, "elendi": 0}
    for o in LO["ozellikler"]: sayac[o["durum"]] = sayac.get(o["durum"], 0) + 1
    B["grafik"] += len(ok); B["ornek"] += yeniN; B["ozellik"] += len(yeni_eklenen); B["tur"] += 1; no = B["tur"]; sn = simdi()
    LO["ornek"] = B["ornek"]
    ilk = sorted([(o["ad"], o) for o in eski.values() if (o.get("ornek") or 0) >= 300], key=lambda kv: -(kv[1].get("fark") or -9))[:2]
    bul = []
    if yeni_eklenen: bul.append("Bu tur denenen yeni formasyonlar: " + ", ".join(eski[k]["aciklama"] for k in yeni_eklenen) + f" (havuzda {max(0, len(OZ_SIRA) - len(B['yeni_formasyon']))} formasyon kaldı).")
    if ilk: bul.append("En güçlü sinyaller (n≥300): " + ", ".join(f"{o['aciklama']} (+%5 oranı %{round(o['oran']*100)}, taban %{round(taban*100)})" for k, o in ilk) + ".")
    if aday: bul.append("Ağırlığa aday (fark ≥ +10 puan, n≥300; geçiş için 3 farklı günde aynı yön gerekir): " + ", ".join(aday) + ".")
    if yeni_liste: bul.append("Durumu değişen: " + ", ".join(yeni_liste) + ".")
    bul.append(f"{len(ok)} hissenin günlük grafiği tarandı; toplamlar önceki turların üstüne eklenir (aynı gün-hisse örneği ikinci kez sayılmaz).")
    LO["tur"] = {"tur": no, "zaman": sn.strftime("%d.%m %H:%M"), "at": sn.isoformat(), "sure_sn": int(time.time() - t0),
                 "grafik": {"toplam": B["grafik"], "bu_tur": len(ok)}, "ornek": B["ornek"], "ornek_yeni": yeniN, "gun": len(gunler), "taban": round(taban, 3),
                 "ozellik_toplam": B["ozellik"], "yeni": len(yeni_eklenen), "sayac": sayac, "bulgular": bul}
    if isinstance(LO.get("model"), dict): LO["model"]["ornek"] = B["ornek"]; LO["model"]["egitim"] = simdi().strftime("%d.%m %H:%M")   # her taramada güncellenen laboratuvar eğitim zamanı (terminalde "eğitim ..." etiketi)
    json.dump(V, open(a.veri, "w"), ensure_ascii=False)
    print(f"ÖZLAB: tur #{no} · toplam {B['grafik']} grafik (+{len(ok)}) · {B['ornek']} örnek (+{yeniN}) · {B['ozellik']} özellik (+{len(yeni_eklenen)} yeni formasyon) · taban %{round(taban*100,1)} · {int(time.time()-t0)} sn")

def yaz(a, ad, obj):
    os.makedirs(a.out, exist_ok=True); json.dump(obj, open(os.path.join(a.out, ad), "w"), ensure_ascii=False)

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("komut"); p.add_argument("kodlar", nargs="*")
    p.add_argument("--rules"); p.add_argument("--veri"); p.add_argument("--out", default="cikti"); p.add_argument("--piyasa", default="bist")
    p.add_argument("--girdi"); p.add_argument("--karar"); p.add_argument("--model", default="model.json"); p.add_argument("--n", type=int, default=12)
    p.add_argument("--etiket", default=simdi().strftime("%d.%m") + " tarama"); p.add_argument("--oturum", default="Bulut tarama")
    p.add_argument("--arsiv", default="arsiv"); p.add_argument("--esik_yuk", type=float, default=.05); p.add_argument("--esik_dus", type=float, default=.03)
    p.add_argument("--min_n", type=int, default=30)
    a = p.parse_args()
    if not a.rules and os.path.exists("rules.json"): a.rules = "rules.json"  # motor/rules.json indirilmişse otomatik kullanılır
    f = {"bist": cmd_bist, "abd": cmd_abd, "kripto": cmd_kripto, "endeks": cmd_endeks, "sektor": cmd_sektor, "haber": cmd_haber,
         "kontrol": cmd_kontrol, "paket": cmd_paket, "adaylar": cmd_adaylar, "kaydet": cmd_kaydet,
         "gozlem": cmd_gozlem, "ogren": cmd_ogren, "kasa": cmd_kasa, "ozlab": cmd_ozlab}.get(a.komut)
    if not f: p.print_help(); sys.exit(1)
    f(a)

if __name__ == "__main__":
    main()
