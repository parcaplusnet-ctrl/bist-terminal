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
import json, sys, os, time, math, argparse, datetime, urllib.request, urllib.error, statistics

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
         "Perf.1M", "High.1M", "Low.1M", "SMA50", "MACD.macd[1]", "MACD.signal[1]", "average_volume_10d_calc"]
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
         "hacim_1_5x_yukselis": 1, "hacimli_ilk_tavan": 1, "kilitli_tavan_1": .5, "kucuk_sirket": -1,
         "mtf_kriter_basina": .25, "yukselen_dip_yapisi": .5}

# seans içi kümülatif hacim payı (yaklaşık U eğrisi); erken saatte göreli hacmi gün sonu eşdeğerine çevirir
PAY_EGRI = {"bist": [(0, 0), (60, .22), (120, .36), (180, .48), (240, .58), (300, .70), (360, .80), (420, .90), (490, 1)],
            "abd": [(0, 0), (60, .25), (120, .38), (180, .48), (240, .58), (300, .69), (360, .82), (390, 1)]}

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
    kucuk = 1.5e9 if piyasa == "bist" else 3e8
    if (o.get("market_cap_basic") or 0) < kucuk: pk["Risk"] += w("kucuk_sirket")
    # stop: en yakın dip (1S, 4S, G) %1-%3 arası, yoksa sınırlar
    lows = [v for v in (o.get("low|60"), o.get("low|240"), o.get("low")) if v]
    aday = [v for v in lows if c * .97 <= v <= c * .99]
    if aday:
        st = max(aday) * (0.998 if piyasa == "bist" else 1) - (0 if piyasa == "bist" else .01); sk = "son dibin altında"
    elif [v for v in lows if v < c * .97]:
        st = c * .97; sk = "en fazla %3 kuralıyla"
    else:
        st = c * .99; sk = "%1 alt sınırı"
    t = tick_bist(c) if piyasa == "bist" else .01
    st = yuvarla(max(st, c * .97), t, yukari=True)
    if st > c * .99: st = yuvarla(c * .99, t)
    puan = round(sum(pk.values()), 2)
    seb = []
    if puan < esik: seb.append(f"puan düşük ({str(puan).replace('.', ',')})")
    if asiri: seb.append("aşırı ısınmış")
    if seans_ici and ch > 4.7: seb.append("gün içi +%4,7 üstünde")
    if not (g("close") > g("EMA20") > g("EMA50")): seb.append("günlük trend aşağı")
    if (yon["|60"] > 0) != (yon["|240"] > 0): seb.append("1S-4S ayrı yön")
    uygun = puan >= esik and not asiri and not (seans_ici and ch > 4.7)
    tk = {"1S": [r2(o.get(k)) for k in ("Recommend.Other|60", "Recommend.MA|60", "Recommend.All|60")],
          "4S": [r2(o.get(k)) for k in ("Recommend.Other|240", "Recommend.MA|240", "Recommend.All|240")],
          "G": [r2(o.get(k)) for k in ("Recommend.Other", "Recommend.MA", "Recommend.All")]}
    hedef = yuvarla(c * 1.05, t, yukari=True)
    return {"kod": o["name"], "ad": o.get("description"), "sektor": o.get("sector"), "fiyat": c, "ch": r2(ch), "rv": r2(rv),
            "puan": puan, "pk": {k: r2(v) for k, v in pk.items()}, "tk": tk, "mt": mt, "stop": st,
            "stop_yuzde": round(st / c - 1, 4), "stop_neden": sk, "hedef": hedef, "rsi": r2(o.get("RSI")),
            "why": why, "sebep": ", ".join(seb), "uygun": uygun, "mcap": o.get("market_cap_basic"),
            "oz": {"pw": r2(o.get("Perf.W")), "p1m": r2(o.get("Perf.1M")), "cfo": r2(o.get("change_from_open")), "rsi1s": r2(o.get("RSI|60")), "rsi4s": r2(o.get("RSI|240")),
                   "g_trend": int(g("close") > g("EMA20") > g("EMA50")), "asiri": int(bool(asiri)),
                   "h1m": r2(c / o["High.1M"] - 1) if o.get("High.1M") else None, "l1m": r2(c / o["Low.1M"] - 1) if o.get("Low.1M") else None}}

def kurallar(yol):
    if yol and os.path.exists(yol):
        R = json.load(open(yol)); return R.get("weights", {}), float(R.get("puan_esigi", 7))
    return {}, 7.0

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
    W, esik = kurallar(a.rules)
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
    W, esik = kurallar(a.rules)
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
    return n > d + (datetime.timedelta(minutes=20) if piyasa == "bist" else datetime.timedelta(hours=1, minutes=10))

def sonuclandir(r, mumlar, piyasa, giris_alan="giris"):
    """Giriş tarihinden SONRAKİ günlerin mumlarıyla (giriş günü kapanıştan girildiği için hariç) sonuç belirler."""
    gi = r.get(giris_alan) or r.get("fiyat"); st = r.get("stop"); hed = gi * 1.05; bas = tarih_ts(r["tarama"])
    M = [m for m in mumlar if m[0] >= bas]  # seçim anından sonra açılan saatlik mumlar
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

def cmd_adaylar(a):
    B = json.load(open(a.girdi)); K = {k["kod"]: k for k in json.load(open(a.karar))}; V = json.load(open(a.veri))
    tarih = simdi().strftime("%d.%m %H:%M"); bitis = vade(a.piyasa)
    havuz = []
    for s in B["adaylar"]:
        k = K.get(s["kod"])
        if not k: continue
        s = dict(s); hp = float(k.get("haber_puan", 0)); s["pk"] = dict(s["pk"]); s["pk"]["KAP"] = hp; s["puan"] = round(s["puan"] + hp, 2); s["haber"] = k.get("haber", "")
        if s["puan"] >= B["esik"]: havuz.append(s)
    havuz.sort(key=lambda s: (-s["puan"], -s["rv"])); sec = havuz[:10]; izle = havuz[10:20]
    picks = []; hist = []
    H0 = V.get("history", []) if a.piyasa == "bist" else V.get("yurtdisi", {}).get("history", [])
    son_basari = {h["kod"]: h for h in H0 if h.get("sonuc") == "Başarılı"}
    for i, s in enumerate(sec):
        yz = f"{s['stop_yuzde'] * 100:.1f}".replace(".", ","); nd = (", ".join(s["why"]) or "çoklu periyot uyumu") + f". Stop {s['stop_neden']}, %{yz}"
        p = {"tarama": tarih, "sira": i + 1, "kod": s["kod"], "ad": s.get("ad"), "sektor": s["sektor"], "fiyat": s["fiyat"], "skor": s["puan"], "hedef": s["hedef"], "stop": s["stop"],
             "stop_yuzde": s["stop_yuzde"], "rsi": s["rsi"], "neden": nd, "bitis": bitis, "pk": s["pk"], "tk": s["tk"],
             "uyari": ", ".join(x for x in s["sebep"].split(", ") if x.startswith("günlük") or x.startswith("1S"))}
        if s["kod"] in son_basari:
            b0 = son_basari[s["kod"]]; p["trend_devam"] = {"onceki_tarama": b0["tarama"], "onceki_max": b0.get("max_degisim"), "onceki_giris": b0.get("giris")}
            yz2 = f"{(b0.get('max_degisim') or 0) * 100:.1f}".replace(".", ","); p["neden"] = f"Trend devam ediyor: {b0['tarama']} seçimi hedefe ulaştı (+%{yz2}). " + p["neden"]
        p["kap" if a.piyasa == "bist" else "haber"] = s["haber"]; picks.append(p)
        hist.append({"trend_devam": bool(p.get("trend_devam")), "tarama": tarih, "kod": s["kod"], "giris": s["fiyat"], "stop": s["stop"], "bitis": bitis, "kontrol": None, "kontrol_fiyat": None, "degisim": None,
                     "max_degisim": None, "min_degisim": None, "hedef_tarih": None, "stop_tarih": None, "sonuc": "Bekliyor", "hata": None})
    izl = [{"kod": s["kod"], "fiyat": s["fiyat"], "skor": s["puan"], "neden": "eşik üstü, ilk 10 dışında: " + (", ".join(s["why"][:2]) or s["sebep"]) + (f"; {s['haber']}" if s["haber"] else "")} for s in izle]
    # İzleme listesi en az 10 hisse: eşik üstü ama ilk 10 dışında kalanlar + eşiğe yakın (eşik-1,5) ya da filtreye takılan güçlü hisseler
    alinan = {x["kod"] for x in sec} | {x["kod"] for x in izl} | {h["kod"] for h in H0 if h.get("sonuc") == "Bekliyor"}
    yakin = sorted([s for s in B.get("tum", []) if s["kod"] not in alinan and not s.get("acik") and s["puan"] >= B["esik"] - 1.5],
                   key=lambda s: (-s["puan"], -(s.get("rv") or 0)))
    for s in yakin[:max(0, 10 - len(izl))]:
        neden = ("eşiğe yakın" if s["puan"] < B["esik"] else "eşik üstü ama filtreye takıldı") + ": " + (s.get("sebep") or ", ".join(s.get("why", [])[:2]))
        izl.append({"kod": s["kod"], "fiyat": s["fiyat"], "skor": s["puan"], "neden": neden})
    sc = {"tarama": tarih, "taranan": B["ozet"]["taranan"], "uygun": B["ozet"]["uygun"], "aday": len(picks), "kontrol": 0, "basarili": 0, "stop": 0}
    if a.piyasa == "bist":
        V["picks"] = picks; V["history"] = V.get("history", []) + hist; V["izleme"] = izl; V["guncelleme"] = tarih
        V["son_tarama"] = {"tarama": tarih, "oturum": "Bulut tarama", "taranan": B["ozet"]["taranan"], "kap_kontrol": len(K), "puan_esigi": B["esik"]}
        sc["piyasa"] = {"xu100": B["ozet"]["xu100"]["gun"], "yukselen": B["ozet"]["yukselen"]}; V.setdefault("scans", []).append(sc)
    else:
        Y = V.setdefault("yurtdisi", {}); Y["picks"] = picks; Y["history"] = Y.get("history", []) + hist; Y["izleme"] = izl
        Y["son_tarama"] = {"tarama": tarih, "oturum": "Bulut tarama", "taranan": B["ozet"]["taranan"], "uygun": B["ozet"]["uygun"], "haber_kontrol": len(K), "puan_esigi": B["esik"]}
        Y["piyasa"] = B["ozet"]["piyasa"]; Y.setdefault("scans", []).append(sc)
    json.dump(V, open(a.veri, "w"), ensure_ascii=False)
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
           "sektor", "katman", "mcap_mlr", "why"]

def cmd_gozlem(a):
    """cikti/<piyasa>.json → arsiv/gozlem_<piyasa>_YYYY-MM-DD.json içine bu taramanın tüm hisse anlık görüntüsünü ekler."""
    B = json.load(open(a.girdi)); n = simdi(); os.makedirs(a.arsiv, exist_ok=True)
    yol = os.path.join(a.arsiv, f"gozlem_{a.piyasa}_{n.strftime('%Y-%m-%d')}.json")
    G = json.load(open(yol)) if os.path.exists(yol) else {"piyasa": a.piyasa, "tarih": n.strftime("%Y-%m-%d"), "cols": GZ_COLS, "taramalar": []}
    rows = []
    for s in B["tum"]:
        oz = s.get("oz") or {}; pk = s.get("pk") or {}; tk = s.get("tk") or {}
        rows.append([s["kod"], s["fiyat"], s["ch"], s["rv"], s["puan"], s.get("rsi"), oz.get("rsi1s"), oz.get("rsi4s"), s.get("mt"),
                     int(bool(s.get("uygun"))), oz.get("asiri", int("aşırı" in (s.get("sebep") or ""))),
                     oz.get("g_trend", int("günlük trend aşağı" not in (s.get("sebep") or ""))),
                     pk.get("RSI-MACD"), pk.get("Trend"), pk.get("Hacim"), pk.get("Uyum"), pk.get("Dip"), pk.get("Risk"),
                     (tk.get("1S") or [None] * 3)[2], (tk.get("4S") or [None] * 3)[2], (tk.get("G") or [None] * 3)[2],
                     oz.get("pw"), oz.get("p1m"), oz.get("cfo"), oz.get("h1m"), oz.get("l1m"),
                     s.get("sektor"), s.get("katman"), r2((s.get("mcap") or 0) / 1e9), "|".join(s.get("why") or [])])
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
    P["guncelleme"] = simdi().strftime("%d.%m %H:%M")
    json.dump(V, open(a.veri, "w"), ensure_ascii=False, separators=(",", ":"))
    son = P["hareketler"][-1] if P["hareketler"] else None
    yaz(a, f"ogren_{piyasa}.json", {"yeni_gozlem": yeni, "taban": P.get("taban_oran"), "bulgular": P["bulgular"], "son_hareket": son})
    print(f"ÖĞREN ({piyasa}): {yeni} yeni gözlem işlendi · toplam {b['n']} hisse-gözlem · arşiv günleri {gunler}")
    for x in P["bulgular"]: print("  ", x)
    if son and yeni:
        print("  Hareket kodları (haber için):", " ".join(h["kod"] for h in son["yukselenler"] + son["dusenler"]))

def yaz(a, ad, obj):
    os.makedirs(a.out, exist_ok=True); json.dump(obj, open(os.path.join(a.out, ad), "w"), ensure_ascii=False)

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("komut"); p.add_argument("kodlar", nargs="*")
    p.add_argument("--rules"); p.add_argument("--veri"); p.add_argument("--out", default="cikti"); p.add_argument("--piyasa", default="bist")
    p.add_argument("--girdi"); p.add_argument("--karar"); p.add_argument("--n", type=int, default=12)
    p.add_argument("--etiket", default=simdi().strftime("%d.%m") + " tarama"); p.add_argument("--oturum", default="Bulut tarama")
    p.add_argument("--arsiv", default="arsiv"); p.add_argument("--esik_yuk", type=float, default=.05); p.add_argument("--esik_dus", type=float, default=.03)
    p.add_argument("--min_n", type=int, default=30)
    a = p.parse_args()
    f = {"bist": cmd_bist, "abd": cmd_abd, "kripto": cmd_kripto, "endeks": cmd_endeks, "sektor": cmd_sektor, "haber": cmd_haber,
         "kontrol": cmd_kontrol, "paket": cmd_paket, "adaylar": cmd_adaylar, "kaydet": cmd_kaydet,
         "gozlem": cmd_gozlem, "ogren": cmd_ogren}.get(a.komut)
    if not f: p.print_help(); sys.exit(1)
    f(a)

if __name__ == "__main__":
    main()
