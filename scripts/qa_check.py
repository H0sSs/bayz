#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""فحص جودة شامل قبل الرفع — bayz repo"""
import os, re, sys, subprocess, html.parser, json

REPO = os.environ.get("BAYZ_REPO", "/home/z/my-project/bayz_repo")
os.chdir(REPO)

VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
errors, warnings, passed = [], [], []

# ---------- 1) فحص توازن وسوم HTML ----------
class TagChecker(html.parser.HTMLParser):
    def __init__(self, fname):
        super().__init__(convert_charrefs=True)
        self.fname, self.stack, self.problems = fname, [], []
    def handle_starttag(self, tag, attrs):
        if tag not in VOID: self.stack.append((tag, self.getpos()))
    def handle_endtag(self, tag):
        if tag in VOID: return
        if not self.stack:
            self.problems.append(f"وسم إغلاق زائد </{tag}> عند سطر {self.getpos()[0]}")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            # دور على أقرب تطابق في الستاك
            names = [t for t,_ in self.stack]
            if tag in names:
                while self.stack and self.stack[-1][0] != tag:
                    t, pos = self.stack.pop()
                    self.problems.append(f"وسم <{t}> مفتوح ومتقفلش (فُتح عند سطر {pos[0]}) — اتقفل بـ </{tag}> عند سطر {self.getpos()[0]}")
                if self.stack: self.stack.pop()
            else:
                self.problems.append(f"وسم إغلاق </{tag}> بلا فتح عند سطر {self.getpos()[0]}")

def check_html(path):
    src = open(path, encoding="utf-8").read()
    # شيل السكربتات عشان الـ parser متتلخبطش في محتوى JS
    src_noscript = re.sub(r"<script.*?</script>", "", src, flags=re.S)
    c = TagChecker(path); c.feed(src_noscript); c.close()
    for t, pos in c.stack:
        c.problems.append(f"وسم <{t}> مفتوح ومتقفلش (سطر {pos[0]})")
    return c.problems

pages = ["index.html", "7-13/index.html", "7-13/jb.html", "13-13.52/index.html", "13-13.52/jb.html",
         "tools/itemzflow/index.html", "tools/pkg-backup/index.html",
         "tools/dns-block/index.html", "tools/rpi/index.html", "tools/fan-control/index.html",
         "tools/cheats/index.html", "tools/cheats/offline-note.html", "tools/goldhen-plugins/index.html",
         "tools/shutdown-fix/index.html", "ps5/index.html"]
for p in pages:
    probs = check_html(p)
    if probs:
        errors.append(f"[HTML] {p}: " + " | ".join(probs[:6]))
    else:
        passed.append(f"توازن وسوم HTML سليم: {p}")

# ---------- 2) فحص الـ JS الداخلي بـ node لكل الصفحات ----------
for p in pages:
    src = open(p, encoding="utf-8").read()
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.S)
    for i, s in enumerate(scripts):
        if not s.strip(): continue
        tmp = f"/tmp/inline_qa_{abs(hash(p))%9999}_{i}.js"
        open(tmp, "w", encoding="utf-8").write(s)
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        if r.returncode == 0:
            passed.append(f"JS سليم (node --check): {p} سكربت #{i+1}")
        else:
            errors.append(f"[JS] {p} سكربت #{i+1}: {r.stderr.strip()[:200]}")

# ---------- 3) فحص ملفات الـ appcache موجودة فعلاً ----------
for mf in ["landing.appcache"]:
    body = open(mf, encoding="utf-8").read()
    section = None
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line in ("CACHE MANIFEST", "CACHE:", "FALLBACK:", "NETWORK:"):
            section = line; continue
        if section == "CACHE:" and " " not in line:
            if os.path.exists(line):
                passed.append(f"ملف الكاش موجود: {line}")
            else:
                errors.append(f"[CACHE] {mf}: ملف مذكور ومش موجود: {line}")

# فحص كاش 7-13 (المسارات نسبية لفولدر 7-13)
for mf, base in [("7-13/host.appcache", "7-13"), ("13-13.52/cache.appcache", "13-13.52"), ("tools/cheats/cheats.appcache", "tools/cheats"), ("ps5/cache.appcache", "ps5")]:
    body = open(mf, encoding="utf-8").read()
    section = None
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line in ("CACHE MANIFEST", "CACHE:", "FALLBACK:", "NETWORK:"):
            section = line; continue
        if section == "CACHE:":
            rel = line.split("#")[0].strip()
            if not rel: continue
            target = os.path.normpath(os.path.join(base, rel))
            if os.path.exists(target):
                passed.append(f"ملف الكاش موجود: {target}")
            else:
                errors.append(f"[CACHE] {mf}: ملف مذكور ومش موجود: {rel}")

# ---------- 5.5) فحص قاعدة الشيتات المحلية (فهرس + أجزاء) ----------
dbdir = "tools/cheats/db"
if not os.path.isdir(dbdir):
    errors.append("[DB] tools/cheats/db مش موجود!")
else:
    idx = None
    try:
        idx = json.load(open(os.path.join(dbdir, "index.json"), encoding="utf-8"))
    except Exception as ex:
        errors.append(f"[DB] index.json مش valid JSON: {ex}")
    if idx is not None:
        if not (isinstance(idx.get("n"), int) and idx["n"] >= 1800):
            errors.append(f"[DB] عدد الملفات غير منطقي: {idx.get('n')}")
        else:
            passed.append(f"فهرس الشيتات سليم: {idx['n']} ملف / {idx.get('games')} لعبة (تحديث {idx.get('date')})")
        files = idx.get("files") or []
        chunk_files = {0: None, 1: None, 2: None, 3: None}
        chunk_data = {}
        for c in range(4):
            p = os.path.join(dbdir, f"bundle{c}.bin")
            if not os.path.exists(p):
                errors.append(f"[DB] {p} مش موجود")
            else:
                chunk_data[c] = open(p, "rb").read()
                if chunk_data[c][:8] != b"BDZB0001":
                    errors.append(f"[DB] magic غلط في bundle{c}.bin")
                else:
                    passed.append(f"magic سليم + {len(chunk_data[c])/1024/1024:.2f}MB: bundle{c}.bin")
        if len(chunk_data) == 4 and files:
            ok_bounds = True
            for e in files:
                if not isinstance(e, dict) or not all(k in e for k in ("f", "g", "c", "o", "l")):
                    errors.append("[DB] عنصر ناقص في الفهرس")
                    ok_bounds = False
                    break
                c = e["c"]
                if c not in chunk_data:
                    errors.append(f"[DB] جزء غير موجود {c} للملف {e['f']}")
                    ok_bounds = False
                    break
                dlen = len(chunk_data[c]) - 8
                if e["o"] < 0 or e["l"] <= 0 or e["o"] + e["l"] > dlen:
                    errors.append(f"[DB] خروج عن الحدود في bundle{c}: {e['f']}")
                    ok_bounds = False
                    break
            if ok_bounds:
                passed.append(f"حدود الأجزاء سليمة 100% ({len(files)} ملف داخل 4 أجزاء)")
        # تحقق عشوائي بايت-ببايت مقابل المصدر الأصلي (لو متاح محليًا)
        src = "/home/z/my-project/research/cheats/repo/json"
        if files and os.path.isdir(src):
            import random
            random.seed(7)
            picks = random.sample(files, min(8, len(files)))
            spot_ok = 0
            for e in picks:
                try:
                    orig = open(os.path.join(src, e["f"]), "rb").read()
                    bd = chunk_data[e["c"]]
                    seg = bd[8 + e["o"]: 8 + e["o"] + e["l"]]
                    if seg == orig:
                        spot_ok += 1
                    else:
                        errors.append(f"[DB] بايتات مختلفة عن المصدر: {e['f']}")
                except Exception as ex:
                    errors.append(f"[DB] فشل التحقق العشوائي {e['f']}: {ex}")
            if spot_ok == len(picks):
                passed.append(f"تطابق بايت-ببايت مع المصدر ✓ (عينة {spot_ok}/{len(picks)})")

# ---------- 5.6) قواعد ربط كاش الشيتات ----------
try:
    cheats_src = open("tools/cheats/index.html", encoding="utf-8").read()
    if 'manifest="cheats.appcache"' in cheats_src:
        passed.append("صفحة الشيتات مرتبطة بالكاش الخاص بيها ✓")
    else:
        errors.append("[CHEATS] صفحة الشيتات مش مرتبطة بـ cheats.appcache!")
except Exception as ex:
    errors.append(f"[CHEATS] فشل قراءة صفحة الشيتات: {ex}")

landing_body = open("landing.appcache", encoding="utf-8").read()
cache_part = landing_body.split("FALLBACK:")[0]
fall_part = landing_body.split("FALLBACK:")[1] if "FALLBACK:" in landing_body else ""
if "tools/cheats/index.html" in cache_part:
    errors.append("[CACHE] tools/cheats/index.html لازم يتشال من قسم CACHE في landing.appcache (عنده كاش منفصل)")
else:
    passed.append("صفحة الشيتات مش في كاش الهبوط (كاش منفصل 8MB اختياري) ✓")
if "tools/cheats/index.html tools/cheats/offline-note.html" in fall_part:
    passed.append("قاعدة FALLBACK لصفحة الشيتات أوفلاين موجودة ✓")
else:
    errors.append("[CACHE] قاعدة FALLBACK لصفحة الشيتات ناقصة في landing.appcache")

# بيلودات الأدوات لازم تكون في كاش سلاسل التشغيل عشان تشتغل أوفلاين عبر ?bin=
host_body = open("7-13/host.appcache", encoding="utf-8").read()
aio_body = open("13-13.52/cache.appcache", encoding="utf-8").read()
for binp in ["../tools/fan-control/55.bin", "../tools/fan-control/60.bin", "../tools/fan-control/65.bin",
             "../tools/fan-control/70.bin", "../tools/fan-control/75.bin", "../tools/fan-control/80.bin"]:
    if binp in host_body and binp in aio_body:
        passed.append(f"بيلود موجود في كاش السلسلتين (أوفلاين ✓): {os.path.basename(binp)}")
    else:
        errors.append(f"[CACHE] {binp} ناقص من كاش 7-13 أو 13-13.52 — تشغيل ?bin= هيكسر أوفلاين!")
if "../tools/cheats/ps4debug_v1.1.19.bin" in host_body:
    passed.append("ps4debug في كاش سلسلة 7-13 (أوفلاين ✓)")
else:
    errors.append("[CACHE] ps4debug ناقص من كاش 7-13 — تشغيل ?bin= هيكسر أوفلاين!")

# ---------- 4) فحص اللينكات الداخلية في الصفحات المعدلة ----------
def check_links(p):
    src = open(p, encoding="utf-8").read()
    # شيل السكربتات قبل الفحص — محتوى JS مش لينكات HTML
    src = re.sub(r"<script.*?</script>", "", src, flags=re.S)
    base = os.path.dirname(p)
    links = re.findall(r'(?:href|src)="([^"]+)"', src)
    bad = []
    for l in links:
        if l.startswith(("http", "https", "#", "data:", "mailto:", "javascript:")): continue
        path = l.split("#")[0].split("?")[0]
        if not path: continue
        # استثنا svg内部的 path attrs مش لينكات
        target = os.path.normpath(os.path.join(base, path))
        if not os.path.exists(target):
            bad.append(l)
    return bad

for p in pages:
    bad = check_links(p)
    if bad:
        errors.append(f"[LINK] {p}: لينكات مكسورة: {bad}")
    else:
        passed.append(f"كل اللينكات الداخلية شغالة: {p}")

# ---------- 5) فحص البيلودات الجديدة (magic 0xE9 + حجم) ----------
payloads = {
    "tools/fan-control/55.bin": 6552, "tools/fan-control/60.bin": 6552,
    "tools/fan-control/65.bin": 6552, "tools/fan-control/70.bin": 6552,
    "tools/fan-control/75.bin": 6552, "tools/fan-control/80.bin": 6552,
    "tools/cheats/ps4debug_v1.1.19.bin": 84936,
}
for p, exp_size in payloads.items():
    d = open(p, "rb").read()
    if d[0] == 0xE9 and len(d) >= 0x40:
        passed.append(f"بيلود سليم (magic 0xE9): {p} ({len(d)}B)")
    else:
        errors.append(f"[PAYLOAD] {p}: magic/حجم غلط (magic={hex(d[0])}, len={len(d)})")
    if exp_size and len(d) != exp_size:
        errors.append(f"[PAYLOAD] {p}: الحجم متغير عن الأصل ({len(d)} ≠ {exp_size})")
# حزمة البلجنات
zsize = os.path.getsize("tools/goldhen-plugins/GoldPlugins-1.210.zip")
if 100000 < zsize < 160000:
    passed.append(f"حزمة البلجنات موجودة ({zsize}B)")
else:
    errors.append(f"[ZIP] tools/goldhen-plugins/GoldPlugins-1.210.zip: حجم غير متوقع {zsize}B")

# فحص روابط ?bin= في صفحات الأدوات تشاور على ملفات موجودة فعلاً
for p in ["tools/fan-control/index.html", "tools/cheats/index.html", "tools/pkg-backup/index.html"]:
    src = open(p, encoding="utf-8").read()
    # كل الروابط اللي فيها ?bin= (كاملة: ../../7-13/index.html?bin=../tools/x/y.bin)
    full_links = re.findall(r'(?:href|src)=["\']([^"\']*\?bin=[^"\']+)["\']', src)
    # وروابط بيلود مباشرة (نسبية للصفحة الحالية)
    bin_refs = re.findall(r'(?:href|src)=["\']([^"\']+\.bin)["\']', src)
    seen = set()
    for link in full_links:
        if link in seen: continue
        seen.add(link)
        page_part, _, bin_part = link.partition("?bin=")
        bin_part = bin_part.split("&")[0]
        # الصفحة الهدف: مسارها نسبي للصفحة الحالية
        page_target = os.path.normpath(os.path.join(os.path.dirname(p), page_part))
        if not os.path.exists(page_target):
            errors.append(f"[BINLINK] {p}: صفحة الهدف مفقودة: {page_part}")
            continue
        # البيلود: مساره نسبي لفولدر الصفحة الهدف
        bin_target = os.path.normpath(os.path.join(os.path.dirname(page_target), bin_part))
        if os.path.exists(bin_target):
            passed.append(f"رابط تشغيل سليم: {os.path.basename(bin_part)} عبر {page_part.split('?')[0]}")
        else:
            errors.append(f"[BINLINK] {p}: بيلود مذكور ومش موجود: {bin_part} (هدف: {bin_target})")
    for b in set(bin_refs):
        if b in seen: continue
        seen.add(b)
        target = os.path.normpath(os.path.join(os.path.dirname(p), b))
        if os.path.exists(target):
            passed.append(f"بيلود المرجع موجود: {b}")
        else:
            errors.append(f"[BINLINK] {p}: بيلود مذكور ومش موجود: {b}")

# ---------- 6) تقرير الأوزان (سرعة صفحة الهبوط) ----------
weights = {}
for f in ["index.html", "style.css", "logo.png", "landing.appcache"]:
    weights[f] = os.path.getsize(f)
total_landing = sum(weights.values())
print("=" * 60)
print("تقرير أوزان صفحة الهبوط (اللي بيتحمل أول مرة):")
for k, v in weights.items():
    print(f"  {k:20s} {v/1024:8.1f} KB")
print(f"  {'الإجمالي':20s} {total_landing/1024:8.1f} KB")
print("=" * 60)
w2 = os.path.getsize("tools/itemzflow/index.html")
print(f"صفحة ItemzFlow: {w2/1024:.1f} KB (self-contained بدون أي طلبات خارجية)")
for f in ["tools/dns-block/index.html", "tools/rpi/index.html", "tools/fan-control/index.html",
          "tools/cheats/index.html", "tools/goldhen-plugins/index.html", "tools/shutdown-fix/index.html"]:
    print(f"{f}: {os.path.getsize(f)/1024:.1f} KB")
if os.path.isdir("tools/cheats/db"):
    db_total = sum(os.path.getsize(os.path.join('tools/cheats/db', x)) for x in os.listdir('tools/cheats/db'))
    print(f"قاعدة الشيتات (db/): {db_total/1024/1024:.2f} MB (كاش منفصل اختياري — مش في تحميل الهبوط)")

# ---------- 6) فحص ممنوعات الأداء على متصفح PS4 ----------
css = open("style.css", encoding="utf-8").read()
for bad in ["backdrop-filter", "filter: blur", "will-change"]:
    if bad in css:
        warnings.append(f"[PERF] style.css فيه {bad} — تقيل على PS4")
# تحذير دقيق: أنيميشن على عنصر fixed كبير (تكلفة تكوين مستمرة) — الصغيرة زي مدار اللوجو مسموحة
import re as _re2
_anim_fixed = _re2.search(r"position:\s*fixed[^}]*animation:\s*\w|animation:\s*\w[^}]*position:\s*fixed", css)
if _anim_fixed:
    warnings.append("[PERF] style.css: أنيميشن على عنصر fixed كبير — تقيل على PS4")
if "backdrop-filter" in css:
    errors.append("[PERF] backdrop-filter ممنوع — شيله")
else:
    passed.append("مفيش backdrop-filter ولا blur في الستايل — خفيف على PS4")
# فحص الخطوط الخارجية والصور الإضافية
if "@import" in css or "url(" in css.replace("url(#", ""):
    m = re.findall(r"url\((?!#)([^)]+)\)", css)
    if m: warnings.append(f"[PERF] الستايل بيطلب ملفات خارجية: {m}")

# ---------- 7) التحقق من أزرار الرجوع وتوسيط أزرار الكروت ----------
css = open("style.css", encoding="utf-8").read()
if "justify-content: center" in css.split(".card-badge {")[1].split("}")[0]:
    passed.append("زر الكارت (.card-badge) متوسّط ✓")
else:
    errors.append("[UX] .card-badge مش متوسّط!")

back_expect = {
    "7-13/index.html": "backlink",
    "7-13/jb.html": "backlink",
    "tools/pkg-backup/index.html": "page-topbar",
    "tools/itemzflow/index.html": "page-topbar",
    "tools/dns-block/index.html": "page-topbar",
    "tools/rpi/index.html": "page-topbar",
    "tools/fan-control/index.html": "page-topbar",
    "tools/cheats/index.html": "page-topbar",
    "tools/cheats/offline-note.html": "رجوع للصفحة الرئيسية",
    "tools/goldhen-plugins/index.html": "page-topbar",
    "tools/shutdown-fix/index.html": "page-topbar",
    "13-13.52/index.html": "backlink",
    "13-13.52/jb.html": "backlink",
    "ps5/index.html": "page-topbar",
}
for p, marker in back_expect.items():
    src = open(p, encoding="utf-8").read()
    if marker in src and "index.html" in src:
        passed.append(f"زر رجوع واضح موجود: {p}")
    else:
        errors.append(f"[UX] {p}: زر الرجوع ناقص!")

# زر الرجوع في 13-13.52 لازم يمنع تعارض الـ tap-anywhere
src1352 = open("13-13.52/index.html", encoding="utf-8").read()
if "event.stopPropagation()" in src1352:
    passed.append("زر الرجوع في 13-13.52 محمي من تعارض waitForTap ✓")
else:
    errors.append("[UX] 13-13.52/index.html: ينقص stopPropagation على زر الرجوع!")

# ---------- 5.8) فحص سلسلة 7-13: التعريب + شاشة التحميل + عقد السلاسل ----------
idx713 = open("7-13/index.html", encoding="utf-8").read()
jb713 = open("7-13/jb.html", encoding="utf-8").read()
for bad_str in ["Loading GoldHEN", "Installing offline cache", "Cache ready", "Cache failed",
                "Content not Found", "Only for PS4", "Running PKG-BackUP", "Unsupported Firmware",
                "PS4 Host (7.00 - 13.00 FW)"]:
    if bad_str in idx713 or bad_str in jb713:
        errors.append(f"[AR] نص إنجليزي قديم لسه موجود في 7-13: '{bad_str}'")
for ar_str in ["جارٍ اكتشاف إصدار النظام", "اضغط زر X للتشغيل", "مدعوم بالكامل",
               "جارٍ فتح صفحة التشغيل", "تم الحفظ — اضغط X أو المس الشاشة لبدء الجيلبريك"]:
    if ar_str not in idx713:
        errors.append(f"[AR] 7-13/index.html ناقصة نص أساسي: '{ar_str}'")
for ar_str in ["جارٍ تشغيل الجيلبريك", "الجيلبريك اشتغل بنجاح", "لازم تعمل ريستارت للجهاز",
               "متخرجش من الصفحة", "الأداة اشتغلت بنجاح"]:
    if ar_str not in jb713:
        errors.append(f"[AR] 7-13/jb.html ناقصة نص أساسي: '{ar_str}'")
if all(s in idx713 for s in ["جارٍ اكتشاف إصدار النظام", "اضغط زر X للتشغيل", "مدعوم بالكامل"]) and \
   all(s in jb713 for s in ["جارٍ تشغيل الجيلبريك", "الجيلبريك اشتغل بنجاح", "لازم تعمل ريستارت للجهاز"]):
    passed.append("سلسلة 7-13 معرّبة بالكامل (بوابة + شاشات تحميل/نجاح/فشل) ✓")

# عقد السلاسل: #msgs + المتغير العالمي + عناصر الوج
if 'id="msgs"' in jb713 and 'var msgs = document.getElementById("msgs")' in jb713:
    passed.append("عقد السلاسل (#msgs + global) سليم في 7-13/jb.html ✓")
else:
    errors.append("[AR] 7-13/jb.html: عقد msgs للسلاسل ناقص!")
for el in ['id="out"', 'id="state"', 'id="console"']:
    if el not in jb713:
        errors.append(f"[AR] 7-13/jb.html: عنصر لوج السلاسل ناقص: {el}")
if all(el in jb713 for el in ['id="out"', 'id="state"', 'id="console"']):
    passed.append("عناصر لوج السلاسل (out/state/console) موجودة ✓")

# نفس نطاقات السلاسل الخمسة في البوابة وصفحة التشغيل (منطق الكشف الأصلي)
for cond in ["fw >= 7.00 && fw <= 8.52", "fw >= 9.00 && fw <= 9.60", "fw >= 10.00 && fw <= 11.02",
             "fw >= 11.50 && fw <= 12.02", "fw >= 12.50 && fw <= 13.00"]:
    if cond not in idx713 or cond not in jb713:
        errors.append(f"[CHAIN] شرط سلسلة ناقص في 7-13: {cond}")
for chain_src in ["700/alert.js", "900/alert.js", "css/main.js", "slopkit/chain_lapse.js", "slopkit/chain_poops.js"]:
    if chain_src not in jb713:
        errors.append(f"[CHAIN] 7-13/jb.html: سلسلة تشغيل ناقصة: {chain_src}")
if all(c in jb713 for c in ["700/alert.js", "900/alert.js", "css/main.js", "slopkit/chain_lapse.js", "slopkit/chain_poops.js"]):
    passed.append("السلاسل الخمسة كلها محملة في صفحة التشغيل ✓")

# تمرير الباراميترات (?bin= للأدوات) من البوابة لصفحة التشغيل
if '"jb.html" + location.search' in idx713:
    passed.append("البوابة بتمرر كل الباراميترات (?bin= وغيره) لـ jb.html ✓")
else:
    errors.append("[CHAIN] 7-13/index.html: تمرير الباراميترات لـ jb.html ناقص!")
if "event.stopPropagation()" in idx713:
    passed.append("زر الرجوع في 7-13 محمي من تعارض waitForTap ✓")
else:
    errors.append("[UX] 7-13/index.html: ينقص stopPropagation على زر الرجوع!")

# jb.html لازم يكون في الكاش (تشغيل أوفلاين) + style.css الميت اتشال
host_body_v7 = open("7-13/host.appcache", encoding="utf-8").read()
if re.search(r"^jb\.html$", host_body_v7, re.M):
    passed.append("jb.html مسجل في كاش 7-13 (أوفلاين) ✓")
else:
    errors.append("[CACHE] 7-13/host.appcache ناقص jb.html — التشغيل أوفلاين هيكسر!")
if re.search(r"^style\.css$", host_body_v7, re.M):
    errors.append("[CACHE] host.appcache لسه فيه style.css الميت (ملزم للـ manifests القديمة بس)!")
else:
    passed.append("host.appcache نضيف من style.css الميت ✓")

# ---------- 5.7) فحص Task 16: تعريب 13-13.52 + DNS + خصخصة الشعار ----------
# أ) الرسائل الإنجليزية القديمة لازم تكون اتشالت من صفحة 13.02
idx1352 = open("13-13.52/index.html", encoding="utf-8").read()
jb1352 = open("13-13.52/jb.html", encoding="utf-8").read()
for bad_str in ["detecting firmware", "loading jailbreak", "UNSUPPORTED FIRMWARE",
                "press X or tap", "UPDATE READY", "CACHE FAILED", "CACHE OBSOLETE",
                "checking cache", "cache unavailable", "offline -- from cache",
                "caching for offline", "Restart your console"]:
    if bad_str in idx1352 or bad_str in jb1352:
        errors.append(f"[AR] نص إنجليزي قديم لسه موجود: '{bad_str}'")
if "جارٍ اكتشاف إصدار النظام" in idx1352 and "اضغط زر X للتشغيل" in idx1352:
    passed.append("صفحة 13.02 معرّبة بالكامل (حالات + شاشة التحميل) ✓")
else:
    errors.append("[AR] صفحة 13.02 ناقصة نصوص عربية أساسية!")
for ar_str in ["جارٍ تشغيل الجيلبريك", "الجيلبريك اشتغل بنجاح", "لازم تعمل ريستارت للجهاز"]:
    if ar_str not in jb1352:
        errors.append(f"[AR] jb.html ناقصة: '{ar_str}'")
if all(s in jb1352 for s in ["جارٍ تشغيل الجيلبريك", "الجيلبريك اشتغل بنجاح", "لازم تعمل ريستارت للجهاز"]):
    passed.append("jb.html: شاشات تحميل/نجاح/فشل عربية ✓")
# عقد jb.js ما زالت سليمة (IDs + body classes)
if 'id="state"' in jb1352 and 'id="out"' in jb1352 and 'id="msg"' in jb1352 and 'id="okpanel"' in jb1352:
    passed.append("عناصر عقد jb.js (state/out/msg) موجودة + شاشة نجاح ✓")
else:
    errors.append("[AR] jb.html ناقصة عناصر عقد jb.js (state/out/msg)!")
if 'import "./jb.js?v=19"' in jb1352:
    passed.append("استيراد jb.js?v=19 (skipjb2) كما هو ✓")
else:
    errors.append("[AR] jb.html: استيراد jb.js?v=19 مفقود/محروق!")

# ب) صفحة DNS المبسطة (Task 20): الرقم + الدليل المصوّر + الخطوات بس (أمر المستخدم)
dns_page = open("tools/dns-block/index.html", encoding="utf-8").read()
for need in ["62.210.38.117", "copyIp", "Nomadic", "Primary DNS", "Secondary DNS",
             "62.210.38.117'", "الخطوة 1", "الخطوة 2", "الخطوة 3", "dns-guide.jpg", "guideframe",
             "خطوات الضبط على PS4"]:
    if need not in dns_page:
        errors.append(f"[DNS] صفحة منع التحديث ناقصة: '{need}'")
if all(n in dns_page for n in ["62.210.38.117", "copyIp", "Nomadic", "Primary DNS"]):
    passed.append("صفحة DNS: الرقم الأساسي 62.210.38.117 + خطوات + نسخ ✓")
# أقسام اتشالت بأمر المستخدم (تبسيط) — ممنوع ترجع تاني
_gone = ["الطريقة الثانية", "الراوتر", "إزاي تشيله", "4 طبقات", "الطبقة 1", "الخطوة صفر",
         "ملخص الطرق كلها", "إزاي تتأكد", "copyAll", "allDomains", "ps4.update.playstation.net",
         "grid2", "ليه رقم واحد بس", "ليه لازم تمنع", "PiHole"]
for gone in _gone:
    if gone in dns_page:
        errors.append(f"[DNS] قسم اتشال بأمر المستخدم لسه موجود: '{gone}'")
if not any(g in dns_page for g in ["الطريقة الثانية", "الراوتر", "copyAll", "ps4.update.playstation.net"]):
    passed.append("صفحة DNS مبسطة زي ما طلب المستخدم: الرقم + الدليل المصوّر + الخطوات بس ✓")

# ج) خصخصة الشعار: نسخة واحدة محسّنة في الجذر
if os.path.exists("7-13/logo.png") or os.path.exists("13-13.52/logo.png"):
    errors.append("[LOGO] نسخ شعار ميتة لسه موجودة في 7-13 أو 13-13.52!")
else:
    passed.append("نسخ الشعار الميتة اتمسحت (باقي نسخة واحدة في الجذر) ✓")
lsz = os.path.getsize("logo.png")
if lsz <= 62000:
    passed.append(f"الشعار محسّن: {lsz/1024:.1f}KB (كان 208KB) ✓")
else:
    errors.append(f"[LOGO] حجم الشعار كبير: {lsz}B — المفروض النسخة المحسّنة ~56KB")
if 'src="../logo.png"' in idx1352 and 'src="../logo.png"' in jb1352:
    passed.append("صفحات 13-13.52 بتشاور على شعار الجذر المشترك ✓")
else:
    errors.append("[LOGO] صفحات 13-13.52 لسه بتطلب logo.png محلي!")
if "../logo.png" in open("13-13.52/cache.appcache", encoding="utf-8").read():
    passed.append("كاش 13-13.52 بيعرف شعار الجذر ✓")
else:
    errors.append("[CACHE] 13-13.52/cache.appcache ناقص ../logo.png!")
host_body2 = open("7-13/host.appcache", encoding="utf-8").read()
if re.search(r"^logo\.png\b", host_body2, re.M):
    errors.append("[CACHE] host.appcache لسه فيه logo.png الميت!")
else:
    passed.append("host.appcache نظيف من نسخة الشعار الميتة ✓")

# د) التحقق من هاشات sha256 في 13-13.52/cache.appcache
ac_body = open("13-13.52/cache.appcache", encoding="utf-8").read()
hash_entries = re.findall(r"^(\S+) #([0-9a-f]{64})$", ac_body, re.M)
for entry, h in hash_entries:
    fp = os.path.normpath(os.path.join("13-13.52", entry.split("?")[0]))
    if not os.path.exists(fp):
        errors.append(f"[HASH] {entry}: الملف مش موجود")
        continue
    import hashlib as _h
    real = _h.sha256(open(fp, "rb").read()).hexdigest()
    if real == h:
        passed.append(f"هاش سليم: {entry}")
    else:
        errors.append(f"[HASH] {entry}: الهاش في المانيفست ({h[:12]}…) ≠ الفعلي ({real[:12]}…)")

# ---------- 5.9) فحص Task 18: دليل حل مشكلة قفل الجهاز بعد GoldHEN ----------
sd_page = open("tools/shutdown-fix/index.html", encoding="utf-8").read()
for need in ["الاتصال بالإنترنت", "Connect to the Internet", "Rest Mode Support",
             "GoldHEN Settings", "فحص مساحة تخزين النظام", "Checking System Storage",
             "Turn Off PS4", "وضع السكون", "البيب", "Issue #187",
             "github.com/GoldHEN/GoldHEN/issues/187", "بيب",
             "7 ثواني", "Restart PS4", 'dir="rtl"', 'lang="ar"']:
    if need not in sd_page:
        errors.append(f"[SHUTDOWN] صفحة الحل ناقصة: '{need}'")
if all(n in sd_page for n in ["الاتصال بالإنترنت", "Rest Mode Support", "فحص مساحة تخزين النظام", "Issue #187"]):
    passed.append("صفحة حل مشكلة القفل: الخطوات + القفل الآمن + المصادر كاملة ✓")
if "<script" in sd_page:
    warnings.append("[SHUTDOWN] صفحة الحل فيها JS — المفروض صفحة ثابتة خالصة (زي dns-block قبل الأزرار)")
else:
    passed.append("صفحة الحل ثابتة بدون JS (صفر أخطاء وقت تشغيل مضمونة) ✓")

# التنبيه (pwrbox) في شاشات النجاح للسلسلتين
for p, marker in [("13-13.52/jb.html", "pwrbox"), ("7-13/jb.html", "pwrbox")]:
    src = open(p, encoding="utf-8").read()
    for need in ["قبل ما تقفل الجهاز", "Rest Mode Support", "../tools/shutdown-fix/index.html"]:
        if need not in src:
            errors.append(f"[SHUTDOWN] {p}: التنبيه ناقص: '{need}'")
    if "pwrbox" in src and "../tools/shutdown-fix/index.html" in src:
        passed.append(f"تنبيه قفل الجهاز مدمج في شاشة النجاح: {p} ✓")

# كارت الهبوط + الأكسنت الجديد
landing_idx = open("index.html", encoding="utf-8").read()
css_src = open("style.css", encoding="utf-8").read()
if "tools/shutdown-fix/index.html" in landing_idx and "accent-teal" in landing_idx:
    passed.append("كارت حل مشكلة القفل موجود في صفحة الهبوط ✓")
else:
    errors.append("[SHUTDOWN] صفحة الهبوط ناقصة كارت حل مشكلة القفل!")
if ".card.accent-teal" in css_src:
    passed.append("ستايل accent-teal للكارت الجديد موجود ✓")
else:
    errors.append("[SHUTDOWN] style.css ناقص تعريف accent-teal!")

# التسجيل في الكاشات التلاتة (أوفلاين من كل المسارات)
ac_landing = open("landing.appcache", encoding="utf-8").read()
ac_host = open("7-13/host.appcache", encoding="utf-8").read()
ac_aio = open("13-13.52/cache.appcache", encoding="utf-8").read()
for name, body in [("landing.appcache", ac_landing), ("7-13/host.appcache", ac_host), ("13-13.52/cache.appcache", ac_aio)]:
    entry = "tools/shutdown-fix/index.html" if name == "landing.appcache" else "../tools/shutdown-fix/index.html"
    if entry in body:
        passed.append(f"صفحة الحل مسجلة في الكاش: {name} ✓")
    else:
        errors.append(f"[CACHE] {name}: صفحة الحل مش مسجلة — الأوفلاين هيكسر!")
if "landing-v17-browserpkg" in ac_landing and "golden-v10" in ac_aio and "7-13-v9-golden" in ac_host:
    passed.append("مراجعات الكاشات التلاتة اترفعت (rev bump) ✓")
else:
    errors.append("[CACHE] واحد أو أكتر من rev bumps ناقص!")

# ---------- 5.10) فحص Task 16b: الهوية الذهبية الجديدة لسلسلة 13.02 ----------
# أ) عناصر التصميم الجديدة في البوابة + شاشات jb.html (CSS خالص بدون أصول جديدة)
for need in ["beacon", "xbtn", "glint", "c-tl", "o1", "drift1", "orbit", "halo", "shim"]:
    if need not in idx1352:
        errors.append(f"[GOLDEN] 13-13.52/index.html: عنصر التصميم الجديد ناقص: '{need}'")
if all(n in idx1352 for n in ["beacon", "xbtn", "glint", "c-tl", "o1", "drift1", "orbit", "halo", "shim"]):
    passed.append("بوابة 13.02: الهوية الذهبية كاملة (منارة + مدار + هالات + HUD) ✓")
for need in ["glint", "c-tl", "o1", "drift1"]:
    if need not in jb1352:
        errors.append(f"[GOLDEN] 13-13.52/jb.html: عنصر الهوية الجديدة ناقص: '{need}'")
if all(n in jb1352 for n in ["glint", "c-tl", "o1", "drift1"]):
    passed.append("jb.html: نفس هوية الخلفية والكارت ✓")
# ب) الخفة: الصفحتين خفيفين (أقل من 16KB) والـ JS الداخلي بدون تغيير وظيفي
for p, src in [("13-13.52/index.html", idx1352), ("13-13.52/jb.html", jb1352)]:
    sz = os.path.getsize(p)
    if sz > 16384:
        errors.append(f"[GOLDEN] {p}: حجم الصفحة {sz}B أكبر من حد الخفة 16KB!")
    else:
        passed.append(f"{p}: خفيفة ({sz/1024:.1f}KB) ✓")
# ج) صفر أصول/صور جديدة — اللوجو المُخزّن فقط
import re as _re
new_imgs = _re.findall(r'src="([^"]+)"', idx1352) + _re.findall(r'src="([^"]+)"', jb1352)
for s in new_imgs:
    if s != "../logo.png":
        errors.append(f"[GOLDEN] أصل صورة جديد غير مسموح: {s}")
if all(s == "../logo.png" for s in new_imgs) and new_imgs:
    passed.append("صفر أصول جديدة — اللوجو المخزّن فقط (كاش موجود) ✓")

# ---------- 5.11) فحص v3: الهوية الذهبية الموحدة (هبوط + 7-13 + أدوات) ----------
# أ) صفحة الهبوط: أورورا + مدار الشعار + الاسم اللاتيني + كروت زجاجية
landing_css = open("style.css", encoding="utf-8").read()
for need in ["aurora", "brand-orbit", "orbit", "ripple", "ELDRA3BAYZ"]:
    if need not in landing_idx and need not in landing_css:
        errors.append(f"[GOLDEN3] صفحة الهبوط ناقصة: '{need}'")
if all((n in landing_idx or n in landing_css) for n in ["aurora", "brand-orbit", "orbit", "ripple", "ELDRA3BAYZ"]):
    passed.append("الهبوط: أورورا ثابتة + مدار الشعار + شارة ELDRA3BAYZ + الكروت الزجاجية ✓")
if "rgba(15, 18, 24, 0.94)" in landing_css or "rgba(15,18,24,.94)" in landing_css:
    passed.append("الكروت الزجاجية الذهبية في style.css ✓")
else:
    errors.append("[GOLDEN3] style.css: خلفية الكروت الزجاجية ناقصة!")
if "box-shadow: 0 4px 0 #6e5317" in landing_css:
    passed.append("أزرار الكروت ثلاثية الأبعاد ✓")
else:
    errors.append("[GOLDEN3] style.css: العمق ثلاثي الأبعاد لأزرار الكروت ناقص!")

# ب) سلسلة 7-13 بنفس هوية المنارة الذهبية (بوابة + jb)
idx713 = open("7-13/index.html", encoding="utf-8").read()
jb713 = open("7-13/jb.html", encoding="utf-8").read()
for need in ["beacon", "xbtn", "glint", "c-tl", "o1", "drift1", "orbit", "halo", "shim"]:
    if need not in idx713:
        errors.append(f"[GOLDEN3] 7-13/index.html: عنصر الهوية الذهبية ناقص: '{need}'")
if all(n in idx713 for n in ["beacon", "xbtn", "glint", "c-tl", "o1", "drift1", "orbit", "halo", "shim"]):
    passed.append("بوابة 7-13: المنارة الذهبية كاملة (منارة + مدار + هالات + HUD) ✓")
for need in ["glint", "c-tl", "o1", "drift1"]:
    if need not in jb713:
        errors.append(f"[GOLDEN3] 7-13/jb.html: عنصر الهوية ناقص: '{need}'")
if all(n in jb713 for n in ["glint", "c-tl", "o1", "drift1"]):
    passed.append("7-13/jb.html: نفس هوية الخلفية والكارت ✓")

# ج) الخفة: صفحات 7-13 تحت الحدود
sz_gate = os.path.getsize("7-13/index.html")
sz_jb = os.path.getsize("7-13/jb.html")
if sz_gate > 17408:
    errors.append(f"[GOLDEN3] 7-13/index.html: الحجم {sz_gate}B أكبر من حد الخفة 17KB!")
else:
    passed.append(f"7-13/index.html خفيفة ({sz_gate/1024:.1f}KB) ✓")
if sz_jb > 26624:
    errors.append(f"[GOLDEN3] 7-13/jb.html: الحجم {sz_jb}B أكبر من حد الخفة 26KB!")
else:
    passed.append(f"7-13/jb.html خفيفة ({sz_jb/1024:.1f}KB) ✓")

# د) توحيد صفحات الأدوات: طبقة الهوية موجودة في التسعة
TOOL_PAGES = ["tools/pkg-backup/index.html", "tools/fan-control/index.html", "tools/cheats/index.html",
              "tools/goldhen-plugins/index.html", "tools/itemzflow/index.html", "tools/rpi/index.html",
              "tools/dns-block/index.html", "tools/shutdown-fix/index.html", "tools/cheats/offline-note.html"]
missing = [p for p in TOOL_PAGES if "هوية الدراع الذهبية v3" not in open(p, encoding="utf-8").read()]
if missing:
    errors.append(f"[GOLDEN3] صفحات أدوات ناقصة طبقة الهوية: {missing}")
else:
    passed.append(f"طبقة الهوية الذهبية مطبقة على كل صفحات الأدوات ({len(TOOL_PAGES)} صفحات) ✓")

# هـ) كاش الشيتات اترفع (اتغيرت صفحة الشيتات)
if "cheats-v3-golden" in open("tools/cheats/cheats.appcache", encoding="utf-8").read():
    passed.append("كاش الشيتات rev v3-golden ✓")
else:
    errors.append("[CACHE] كاش الشيتات محتاج rev bump!")

# ---------- 5.12) فحص Task 19: الدليل المصوّر الرسمي (12 خطوة) في صفحة منع التحديثات ----------
dns_img = "tools/dns-block/dns-guide.jpg"
dns_page18 = open("tools/dns-block/index.html", encoding="utf-8").read()

def _jpeg_size(path):
    """قراءة أبعاد JPEG من ماركرات SOF بدون مكتبات خارجية."""
    with open(path, "rb") as f:
        data = f.read()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return w, h
        if m == 0xD8 or m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        seglen = (data[i + 2] << 8) | data[i + 3]
        i += 2 + seglen
    return None

if os.path.exists(dns_img):
    dsz = os.path.getsize(dns_img)
    if dsz > 120 * 1024:
        errors.append(f"[DNSIMG] {dns_img}: الحجم {dsz}B أكبر من حد الخفة 120KB!")
    else:
        passed.append(f"الدليل المصوّر الرسمي خفيف: {dsz/1024:.1f}KB ✓")
    jd = _jpeg_size(dns_img)
    if jd != (1070, 978):
        errors.append(f"[DNSIMG] {dns_img}: الأبعاد الفعلية {jd} مش مطابقة للعقد 1070x978 (الدليل الرسمي 12 خطوة)!")
    else:
        passed.append("أبعاد الدليل المصوّر الفعلية 1070x978 مطابقة للعقد ✓")
else:
    errors.append(f"[DNSIMG] {dns_img} مش موجود!")
for need in ['src="dns-guide.jpg"', "guideframe", 'width="1070"', 'height="978"', 'alt="دليل مصور', 'href="dns-guide.jpg"', "guidecap", "62.210.38.117"]:
    if need not in dns_page18:
        errors.append(f"[DNSIMG] صفحة منع التحديث ناقصة: '{need}'")
if all(n in dns_page18 for n in ['src="dns-guide.jpg"', "guideframe", 'width="1070"', 'height="978"', 'alt="دليل مصور', 'href="dns-guide.jpg"']):
    passed.append("الدليل المصوّر مدمج بإطار ذهبي عريض (أبعاد مثبتة + alt وصفي + فتح بالحجم الكامل) ✓")
for legacy in ["phoneframe", 'width="480"', 'height="1067"', 'alt="لقطة']:
    if legacy in dns_page18:
        errors.append(f"[DNSIMG] أثر اللقطة القديمة الخاطئة لسه موجود: '{legacy}' — لازم يتشال!")
if "tools/dns-block/dns-guide.jpg" in ac_landing:
    passed.append("الدليل المصوّر مسجل في كاش الهبوط (أوفلاين ✓)")
else:
    errors.append("[DNSIMG] الدليل المصوّر مش مسجل في landing.appcache — الأوفلاين هيكسر!")

# روابط المصادر الخارجية في صفحة الحل لازم تكون https + rel=noopener
ext_links = re.findall(r'href="(https?://[^"]+)"[^>]*>', sd_page)
for link in ext_links:
    if not link.startswith("https://"):
        errors.append(f"[SHUTDOWN] رابط خارجي مش https: {link}")
if ext_links and all(l.startswith("https://") for l in ext_links):
    passed.append(f"كل روابط المصادر خارجية آمنة https ({len(ext_links)} روابط) ✓")
if 'target="_blank" rel="noopener"' in sd_page:
    passed.append("الروابط الخارجية بـ rel=noopener ✓")


# ---------- 5.13) فحص Task 23: قسم PS5 (Relapse) — صفحة تفعيل عربية موحدة جوه ps5/ مباشرة + مزامنة بعقود سلوك ----------
ps5_page = open("ps5/index.html", encoding="utf-8").read()
# أ) عقود المحتوى الأساسية للصفحة العربية الموحدة (دليل + تفعيل في صفحة واحدة)
for need in ["Relapse", "PS5", "7.00", "13.60", "45.56.67.85", "copyDns", "copyUrl",
             "h0sss.github.io/bayz/ps5/", "https://h0sss.github.io/bayz/ps5/", "R2", "9021",
             "elfldr", "etaHEN", "kstuff", "shadowmountplus", "الخطوة 1", "الخطوة 2", "الخطوة 3",
             "هوية الدراع الذهبية v3", "runbtn", "دليل المستخدم", "Guide &amp; Tips",
             "بيحجب سيرفرات تحديث سوني", "الجيلبريك مؤقت مش دائم",
             'id="jbStart"', 'id="arabStatus"', 'id="console"', 'id="fwChip"',
             "src/firmware.js", "src/site.js", "src/utils/syscalls.js",
             "MutationObserver", "s.type = \"module\""]:
    if need not in ps5_page:
        errors.append(f"[PS5] صفحة PS5 ناقصة: '{need}'")
if all(n in ps5_page for n in ['id="jbStart"', "runbtn", 'id="console"', 'id="arabStatus"', "src/site.js"]):
    passed.append("زر تفعيل الجيلبريك في أول الصفحة (jbStart) + شريط الحالة العربي + السجل التقني متصلين بكود الاستغلال (src/site.js) ✓")
# ب) المسار الموحد: ملفات الاستغلال جوه ps5/ مباشرة (أمر صاحب الموقع — إلغاء مسار relapse/)
if "relapse/" in ps5_page:
    errors.append("[PS5] ممنوع مسار relapse/ في صفحة PS5 — الملفات جوه ps5/ مباشرة (أمر صاحب الموقع)!")
if os.path.isdir("ps5/relapse"):
    errors.append("[PS5] المجلد القديم ps5/relapse/ لسه موجود — الملفات لازم تبقى جوه ps5/ مباشرة!")
if not os.path.isdir("ps5/relapse") and "relapse/" not in ps5_page:
    passed.append("مسار relapse/ اتلغى — ملفات الاستغلال جوه ps5/ مباشرة + الرابط الموحد h0sss.github.io/bayz/ps5/ ✓")
# ج) صفر روابط خارجية في صفحة PS5 (أمر المستخدم — رابطنا فقط)
if "ntfargo" in ps5_page:
    errors.append("[PS5] ممنوع ذكر المصدر الخارجي (ntfargo) في صفحة PS5 — أمر المستخدم: رابطنا فقط!")
if "github.com" in ps5_page:
    errors.append("[PS5] ممنوع github.com في صفحة PS5 — أمر المستخدم: رابطنا فقط!")
_ext5 = [m for m in re.findall(r"https?://[^\s\"'<>]+", ps5_page) if not m.startswith("https://h0sss.github.io")]
if _ext5:
    errors.append(f"[PS5] روابط خارجية ممنوعة في صفحة PS5: {_ext5[:3]}")
if "ntfargo" not in ps5_page and "github.com" not in ps5_page and not _ext5:
    passed.append("صفر روابط خارجية في صفحة PS5 — رابطنا فقط (أمر المستخدم) ✓")
# د) عقود السلوك: آلية R2 + إرسال البيلودات لازم تفضل موجودة (النسخة الكاملة المثبتة)
_main5 = open("ps5/src/main.js", encoding="utf-8").read()
if "watchR2" not in _main5:
    errors.append("[PS5] آلية R2 مش موجودة في ps5/src/main.js — النسخة الكاملة المثبتة اتكسرت!")
_kexp5 = open("ps5/src/kexp.js", encoding="utf-8").read()
if "loadOptionalPayloads" not in _kexp5:
    errors.append("[PS5] آلية إرسال البيلودات (loadOptionalPayloads) مش موجودة في ps5/src/kexp.js — النسخة المثبتة اتكسرت!")
if "watchR2" in _main5 and "loadOptionalPayloads" in _kexp5:
    passed.append("عقود السلوك سليمة: آلية R2 + إرسال البيلودات (kstuff ← shadowmountplus ← etaHEN) موجودة في كود الاستغلال ✓")
# هـ) تكامل ملفات الاستغلال مع المانيفست (نسخة حرفية بايت-بايت من المصدر — جوه ps5/ مباشرة)
import hashlib as _h23
_mf5 = "ps5/relapse-sync.json"
if not os.path.exists(_mf5):
    errors.append("[PS5] ps5/relapse-sync.json (مانيفست التكامل) مش موجود!")
else:
    _mfdata = json.load(open(_mf5, encoding="utf-8"))
    _bad5 = 0
    for rel, meta in _mfdata["files"].items():
        p = os.path.join("ps5", rel)
        if not os.path.exists(p):
            errors.append(f"[PS5] ملف استغلال ناقص: {rel}"); _bad5 += 1; continue
        if os.path.getsize(p) != meta["size"] or _h23.sha256(open(p, "rb").read()).hexdigest() != meta["sha256"]:
            errors.append(f"[PS5] تكامل مكسور (مش مطابق للمانيفست): {rel}"); _bad5 += 1
    if _bad5 == 0:
        passed.append(f"تكامل Relapse: {len(_mfdata['files'])} ملف مطابق للمانيفست بايت-بايت جوه ps5/ ✓ ({_mfdata['total_bytes']/1048576:.2f}MB)")
    if "jbStart" not in ps5_page:
        errors.append("[PS5] صفحة التفعيل العربية الموحدة (ps5/index.html) ناقصة أو مش صفحتنا!")
    else:
        passed.append("صفحة التفعيل العربية الموحدة موجودة ومستبدلة صفحة المصدر (محمية من المزامنة) ✓")
    _our5 = {"index.html", "relapse-sync.json", "cache.appcache"}
    _local5 = set()
    for _dp, _dd, _fns in os.walk("ps5"):
        for _fn in _fns:
            _local5.add(os.path.relpath(os.path.join(_dp, _fn), "ps5").replace(os.sep, "/"))
    _extra5 = _local5 - set(_mfdata["files"]) - _our5
    if _extra5:
        errors.append(f"[PS5] ملفات زيادة في ps5/ مش موجودة في المصدر ولا ملكنا: {sorted(_extra5)[:5]}")
    else:
        passed.append("صفر تعديلات يدوية في ملفات الاستغلال (مطابقة للمانيفست حرفيًا) ✓")
    _fw5 = open("ps5/src/firmware.js", encoding="utf-8").read()
    for fw in ["13.60", "7.00", "PlayStation 5"]:
        if fw not in _fw5:
            errors.append(f"[PS5] firmware.js ناقصة إشارة أساسية: '{fw}'")
    if all(fw in _fw5 for fw in ["13.60", "7.00", "PlayStation 5"]):
        passed.append("نطاق الفيرمويرات 7.00 → 13.60 سليم في كود الاستغلال ✓")
    _paymin5 = {"payloads/etaHEN.elf": 1000000, "payloads/shadowmountplus.elf": 500000,
                "payloads/kstuff.elf": 500000, "payloads/elfldr-ps5-1360.elf": 100000}
    _pbad5 = False
    for _pp, _mn in _paymin5.items():
        _sz = os.path.getsize(os.path.join("ps5", _pp))
        if _sz < _mn:
            errors.append(f"[PS5] بيلود مشتبه (صغير جدًا — ممكن فاسد): {_pp} ({_sz}B)")
            _pbad5 = True
    if not _pbad5:
        passed.append("أحجام البيلودات الأربعة منطقية (etaHEN + shadowmountplus + kstuff + elfldr) ✓")
    print(f"صفحة PS5 الموحدة (ps5/index.html): {os.path.getsize('ps5/index.html')/1024:.1f} KB")
    print(f"ملفات الاستغلال (جوه ps5/ مباشرة): {len(_mfdata['files'])} ملف / {_mfdata['total_bytes']/1048576:.2f} MB — النسخة الكاملة المثبتة (شاملة آلية R2 والبيلودات)")
# و) كارت PS5 في صفحة الهبوط (بعد كارت 13.02 — المركز الثالث في قسم الجيلبريك)
if 'href="ps5/index.html"' in landing_idx:
    _p5 = landing_idx.find('href="ps5/index.html"')
    _p13 = landing_idx.find('href="13-13.52/index.html"')
    if _p13 != -1 and _p13 < _p5:
        passed.append("كارت PS5 في مكانه الصح (بعد كارت 13.02 — الترتيب اللي اعتمده المستخدم) ✓")
    else:
        errors.append("[PS5] كارت PS5 لازم يجي بعد كارت 13-13.52 في قسم الجيلبريك!")
else:
    errors.append("[PS5] صفحة الهبوط ناقصة كارت جيلبريك PS5!")
for need in ["PS5 · جيلبريك جديد", "7.00 → 13.60", "Relapse", "etaHEN", "دليل عربي خطوة بخطوة"]:
    if need not in landing_idx:
        errors.append(f"[PS5] كارت الهبوط ناقص: '{need}'")
if "Nathan Fargo" in landing_idx and "Relapse Team" in landing_idx:
    passed.append("شكرات فريق Relapse (Nathan Fargo) موجودة في فوتر الهبوط ✓")
else:
    errors.append("[PS5] الفوتر ناقص شكرات فريق Relapse (Nathan Fargo & Relapse Team)!")
# ز) صفحة التفعيل خارج كاش الهبوط عمدًا (عندها كاش أوفلاين مستقل ps5/cache.appcache — مش نكرر 9.6MB جوه كاشين)
if "ps5/index.html" not in ac_landing and "landing-v17-browserpkg" in ac_landing:
    passed.append("صفحة تفعيل PS5 خارج كاش الهبوط (كاشها المستقل ps5/cache.appcache) + rev v17-browserpkg ✓")
else:
    errors.append("[PS5] ps5/index.html لازم يفضل خارج landing.appcache (عندها كاش مستقل ps5/cache.appcache) و rev v17-browserpkg مطلوب!")

if "ps5/src" in ac_landing or "ps5/offsets" in ac_landing or "ps5/payloads" in ac_landing or "relapse-sync" in ac_landing or "ps5/relapse" in ac_landing:
    errors.append("[PS5] ممنوع تسجيل ملفات الاستغلال (9.3MB) في كاش الهبوط — تقيلة بلا فايدة!")
else:
    passed.append("ملفات الاستغلال خارج كاش الهبوط (عندها كاش مستقل ps5/cache.appcache — من غير تكرار 9.6MB) ✓")
# ز2) عقود كاش أوفلاين PS5 المستقل (2026-10-04 بأمر صاحب الموقع: الصفحة لازم تفتح وتشتغل بعد فصل النت)
_pcache_path = "ps5/cache.appcache"
if not os.path.exists(_pcache_path):
    errors.append("[PS5-CACHE] ps5/cache.appcache ناقص — صفحة PS5 مش هتفتح أوفلاين!")
else:
    _pcache_body = open(_pcache_path, encoding="utf-8").read()
    _pcache_sec = None
    _pcache_cache = set()
    _pcache_fb = set()
    for _pl in _pcache_body.splitlines():
        _pl = _pl.strip()
        if not _pl or _pl.startswith("#"):
            continue
        if _pl in ("CACHE MANIFEST", "CACHE:", "FALLBACK:", "NETWORK:"):
            _pcache_sec = _pl[:-1] if _pl.endswith(":") else _pl
            continue
        if _pcache_sec == "CACHE" and " " not in _pl:
            _pcache_cache.add(_pl)
        elif _pcache_sec == "FALLBACK" and " " in _pl:
            _pcache_fb.add(" ".join(_pl.split()))
    _off_list5 = sorted(_fn5 for _fn5 in os.listdir("ps5/offsets") if _fn5.endswith(".js"))
    _need_cache5 = {"index.html", "../index.html", "../style.css", "../logo.png",
                    "../tools/dns-block/dns-guide.jpg", "../tools/ps5-browser/index.html",
                    "src/firmware.js", "src/main.js", "src/rop.js", "src/site.js", "src/webkit.js",
                    "src/relapse_exploit.js", "src/kexp.js",
                    "src/utils/int64.js", "src/utils/mem.js", "src/utils/rop_slave.js", "src/utils/syscalls.js",
                    "payloads/elfldr-ps5-1360.elf", "payloads/etaHEN.elf", "payloads/kexp_2026_05_25.bin",
                    "payloads/kstuff.elf", "payloads/shadowmountplus.elf"} | {"offsets/" + _o5 for _o5 in _off_list5}
    _miss_cache5 = sorted(_need_cache5 - _pcache_cache)
    if _miss_cache5:
        errors.append("[PS5-CACHE] ناقص من قسم CACHE: " + ", ".join(_miss_cache5[:8]))
    else:
        passed.append("كاش أوفلاين PS5 كامل: " + str(len(_need_cache5)) + " ملف (الصفحة + السلسلة + " + str(len(_off_list5)) + " أوفست + 5 بيلودات) ✓")
    _need_fb5 = {"offsets/" + _o5 + " offsets/" + _o5 for _o5 in _off_list5}
    _miss_fb5 = sorted(_need_fb5 - _pcache_fb)
    if _miss_fb5:
        errors.append("[PS5-CACHE] أسطر FALLBACK ناقصة (تغطية طلبات ?v= أوفلاين): " + ", ".join(_miss_fb5[:4]))
    else:
        passed.append("تغطية FALLBACK لكل أوفستات الفيرمويرات (طلبات ?v= بتشتغل أوفلاين) ✓")
    if "NETWORK:" not in _pcache_body:
        errors.append("[PS5-CACHE] قسم NETWORK: ناقص من المانيفيست!")
    if "20261004-ps5-v1" not in _pcache_body:
        errors.append("[PS5-CACHE] علامة rev 20261004-ps5-v1 ناقصة من المانيفيست!")
    _ps5_html_c = open("ps5/index.html", encoding="utf-8").read()
    if 'manifest="cache.appcache"' not in _ps5_html_c:
        errors.append("[PS5-CACHE] صفحة ps5/index.html مش مربوطة بالمانيفيست (سمة manifest ناقصة)!")
    else:
        passed.append("صفحة تفعيل PS5 مربوطة بـ ps5/cache.appcache (كاش مستقل خارج كاش الهبوط) ✓")
    if "no-store" in _ps5_html_c:
        errors.append("[PS5-CACHE] لسه فيه وسم no-store في صفحة PS5 — ده بيمنع التخزين!")
    if 'id="cacheNote"' not in _ps5_html_c or "applicationCache" not in _ps5_html_c:
        errors.append("[PS5-CACHE] مؤشر حالة الكاش (cacheNote + applicationCache) ناقص من الصفحة!")
    else:
        passed.append("مؤشر حالة كاش الأوفلاين شغال جوه كارت التفعيل ✓")
    if 'fwPre.src = "offsets/" + fw + ".js"' not in _ps5_html_c:
        errors.append("[PS5-CACHE] التحميل المبكر لأوفستات الفيرموير من الكاش ناقص من الصفحة!")
    else:
        passed.append("التحميل المبكر للأوفستات من الكاش موجود (تشغيل أوفلاين مضمون حتى مع ?v=) ✓")

# ح) أدوات التزامن التلقائي موجودة داخل الريبو (تشغيلها من GitHub Actions)
for _f in ["scripts/sync_relapse.py", "scripts/qa_check.py", ".github/workflows/sync-relapse.yml"]:
    if not os.path.exists(_f):
        errors.append(f"[PS5] أداة التزامن/الجودة ناقصة من الريبو: {_f}")
if all(os.path.exists(f) for f in ["scripts/sync_relapse.py", "scripts/qa_check.py", ".github/workflows/sync-relapse.yml"]):
    passed.append("أدوات التزامن التلقائي (sync_relapse.py + qa_check.py + workflow) موجودة في الريبو ✓")
    _wf5 = open(".github/workflows/sync-relapse.yml", encoding="utf-8").read()
    if "workflow_dispatch" in _wf5 and "schedule" in _wf5 and "cron" in _wf5:
        passed.append("الـ workflow: جدولة كل 6 ساعات + زر تشغيل يدوي فوري (workflow_dispatch) ✓")
    else:
        errors.append("[PS5] الـ workflow لازم يكون فيه schedule (cron) + workflow_dispatch!")
    if "BAYZ_REPO" not in _wf5:
        errors.append("[PS5] الـ workflow لازم يمرر BAYZ_REPO لـ qa_check.py!")
    else:
        passed.append("الـ workflow بيمرر BAYZ_REPO لبوابة الجودة ✓")
    if "pages/builds" in _wf5:
        passed.append("الـ workflow بطلب إعادة بناء GitHub Pages بعد كل مزامنة ✓")
    else:
        errors.append("[PS5] الـ workflow لازم يطلب إعادة بناء Pages بعد الدفع!")
    if "UPSTREAM_DRIFT" in _wf5:
        passed.append("الـ workflow بيتعامل مع انحراف المصدر بأمان (وقف المزامنة بدون كسر الموقع) ✓")
    else:
        errors.append("[PS5] الـ workflow لازم يتعامل مع أكواد الانحراف (3/5) بوقف آمن!")
    # تحذير لو الـ workflow مش متتبع في git (الـ PAT وقت v3.4 كان ناقص scope الـ workflows)
    try:
        _tr5 = subprocess.run(["git", "ls-files", "--error-unmatch", ".github/workflows/sync-relapse.yml"], capture_output=True, text=True)
        if _tr5.returncode != 0:
            warnings.append("[PS5] ملف الـ workflow موجود على القرص بس مش متسجل في git — محتاج PAT بصلاحية workflows أو إنشاؤه من واجهة GitHub (زي حالة v3.4)")
    except Exception:
        pass
# ط) سكريبت المزامنة نفسه: يستهدف ps5/ مباشرة + يحمي صفحتنا + محمي بعقود السلوك
_sr5 = open("scripts/sync_relapse.py", encoding="utf-8").read()
if 'os.path.join(args.repo, "ps5")' not in _sr5:
    errors.append("[PS5] sync_relapse.py لازم يستهدف ps5/ مباشرة (بدون مجلد فرعي)!")
for _need5 in ["index.html", "relapse-sync.json", "watchR2", "loadOptionalPayloads", "BEHAVIOR_CONTRACTS"]:
    if _need5 not in _sr5:
        errors.append(f"[PS5] sync_relapse.py ناقص عنصر حماية: {_need5}")
if all(n in _sr5 for n in ["BEHAVIOR_CONTRACTS", "watchR2", "loadOptionalPayloads", "index.html", "relapse-sync.json"]) and 'os.path.join(args.repo, "ps5")' in _sr5:
    passed.append("سكريبت المزامنة: يستهدف ps5/ مباشرة + بيحمي صفحتنا + واقف عند عقود السلوك (بيقف لو المصدر شطب آلية R2) ✓")


# ---------- 5.14) فحص Task 24: كارت تشغيل الاستغلال (تصميم كروت PS4) + الدليل المصوّر 12 خطوة جوه صفحة PS5 ----------
# أ) عقود الكارت: نفس عناصر كروت PS4 في صفحة الهبوط (رأس + تاج + نطاق + شيبس + زر التفعيل جوه الكارت)
_card24_need = ['class="jbcard"', 'class="card-head"', 'class="card-tag"', 'class="card-range"',
                'class="card-body"', 'class="card-action"', 'class="card-foot"',
                'id="jbStart"', "runbtn", "Relapse", "etaHEN"]
for _n in _card24_need:
    if _n not in ps5_page:
        errors.append(f"[PS5-كارت] كارت التفعيل ناقص عنصر: '{_n}'")
if all(n in ps5_page for n in _card24_need):
    passed.append("كارت تشغيل الاستغلال (رأس + شيبس + زر تفعيل) بنفس عناصر كروت PS4 في أول صفحة PS5 ✓")
if ps5_page.count('<span class="chip">') < 3:
    errors.append("[PS5-كارت] الكارت لازم يبقى فيه 3 شيبس على الأقل (زي كروت الهبوط)!")
else:
    _nchips = ps5_page.count('<span class="chip">')
    passed.append("شيبس الكارت موجودة (" + str(_nchips) + " شيب — زي كروت الهبوط) ✓")
# ب) الترتيب: الكارت أول عنصر في الصفحة قبل كل الأقسام (زر التفعيل ظاهر من غير سكرول — أمر صاحب الموقع)
_o_card = ps5_page.find('id="jbStart"')
_o_r2sec = ps5_page.find("أثناء التشغيل")
_o_s1 = ps5_page.find("الخطوة 1")
_o_dns = ps5_page.find('id="copyDns"')
_o_guide = ps5_page.find("../tools/dns-block/dns-guide.jpg")
if -1 in (_o_card, _o_r2sec, _o_s1, _o_dns, _o_guide) or not (_o_card < _o_r2sec and _o_card < _o_s1 and _o_card < _o_dns):
    errors.append("[PS5-كارت] كارت التفعيل لازم يبقى أول عنصر في الصفحة قبل كل الأقسام!")
else:
    passed.append("الكارت أول الصفحة قبل كل الأقسام — زر التفعيل ظاهر من غير سكرول ✓")
# ج) الدليل المصوّر 12 خطوة جوه قسم DNS (الخطوة 2) — من مسارنا tools/dns-block بدون نسخ مكررة
if "dns-guide.jpg" not in ps5_page:
    errors.append("[PS5-دليل] الدليل المصوّر 12 خطوة ناقص من قسم DNS في صفحة PS5 (أمر صاحب الموقع)!")
else:
    if "../tools/dns-block/dns-guide.jpg" not in ps5_page:
        errors.append("[PS5-دليل] الدليل المصوّر لازم ييجي من مسارنا المشترك tools/dns-block/dns-guide.jpg (مش نسخة جوه ps5/)!")
    if "guideframe" not in ps5_page or "guidecap" not in ps5_page or "12 خطوة" not in ps5_page:
        errors.append("[PS5-دليل] الدليل المصوّر ناقص عناصره (guideframe + guidecap + عنوان 12 خطوة)!")
    if _o_dns == -1 or _o_guide < _o_dns:
        errors.append("[PS5-دليل] الدليل المصوّر لازم يبقى جوه قسم DNS بعد رقم الـ DNS (الخطوة 2)!")
    if not ("دوس على الصورة" in ps5_page and 'width="1070"' in ps5_page and 'height="978"' in ps5_page):
        errors.append("[PS5-دليل] الدليل المصوّر لازم يبقى قابل للفتح بالحجم الكامل (دوس على الصورة) بأبعاد 1070x978!")
    if all(x in ps5_page for x in ["../tools/dns-block/dns-guide.jpg", "guideframe", "guidecap", "12 خطوة", "دوس على الصورة", 'width="1070"', 'height="978"']) and _o_guide > _o_dns:
        passed.append("الدليل المصوّر (12 خطوة / 1070x978) جوه قسم DNS — بنفس صورة الدليل الرسمية المشتركة من tools/ من غير نسخ مكررة ✓")
# د) تحذير الرقم: رقم آخر مربع في الدليل بتاع PS4 — على PS5 يتكتب 45.56.67.85
_cap24 = ps5_page.find('class="guidecap"')
if _cap24 == -1 or "45.56.67.85" not in ps5_page[_cap24:_cap24 + 1200] or "PS4" not in ps5_page[_cap24:_cap24 + 1200]:
    errors.append("[PS5-دليل] لازم تحذير واضح تحت الدليل المصوّر: رقم الدليل بتاع PS4 — على PS5 اكتب 45.56.67.85!")
else:
    passed.append("تحذير الرقم موجود تحت الدليل المصوّر (رقم الصورة بتاع PS4 — والـ PS5 يكتب 45.56.67.85) ✓")
# هـ) ممنوع نسخ الصورة جوه ps5/ (بتفضل في tools/dns-block — المانيفست بيمنع الملفات الزيادة)
if os.path.exists("ps5/dns-guide.jpg"):
    errors.append("[PS5-دليل] ممنوع نسخ dns-guide.jpg جوه ps5/ — الصورة بتفضل في tools/dns-block/ (ملف واحد مشترك)!")
else:
    passed.append("صورة الدليل مش متنسوخة جوه ps5/ (محمية عقود المانيفست) — بتتحمّل من tools/dns-block المشتركة ✓")
# و) الـ IDs الوظيفية كلها سليمة جوه الكارت (الـ JS شغال من غير تغيير)
for _id24 in ['id="fwChip"', 'id="arabStatus"', 'id="asMain"', 'id="asSub"', 'id="console"', 'id="consoleWrap"', 'id="retryRow"']:
    if _id24 not in ps5_page:
        errors.append(f"[PS5-كارت] ID وظيفي ناقص من الكارت (الـ JS بيعتمد عليه): {_id24}")
if all(x in ps5_page for x in ['id="fwChip"', 'id="arabStatus"', 'id="asMain"', 'id="asSub"', 'id="console"', 'id="consoleWrap"', 'id="retryRow"']):
    passed.append("كل الـ IDs الوظيفية (الحالة + السجل + إعادة المحاولة) سليمة جوه الكارت — الـ JS من غير أي تغيير ✓")
# ز) CSS الكارت + الدليل موجودين
if ".jbcard" not in ps5_page or ".jbcard .card-head" not in ps5_page or ".guideframe" not in ps5_page:
    errors.append("[PS5-كارت] CSS الكارت (.jbcard .card-head) أو الدليل (.guideframe) ناقص من الصفحة!")
else:
    passed.append("CSS الكارت (jbcard) + CSS الدليل المصوّر (guideframe) متسجلين في الصفحة ✓")



# ---------- 5.15) فحص Task 27/29: متصفح الدراع بايظ («الدراع بايظ | PS5») — تطبيق Media بيفتح صفحة التفعيل ----------
_br_pkg = "tools/ps5-browser/ps5-browser-eldra3bayez.pkg"
_br_page_path = "tools/ps5-browser/index.html"
if not os.path.exists(_br_page_path):
    errors.append("[PS5-براوزر] صفحة الأداة tools/ps5-browser/index.html مش موجودة!")
else:
    _br_page = open(_br_page_path, encoding="utf-8").read()
    _br_needs = ["متصفح الدراع بايظ", "الدراع بايظ | PS5", "ps5-browser-eldra3bayez.pkg", "12800",
                 "Package Installer", "Media", 'id="copyUrl"',
                 "h0sss.github.io/bayz/tools/ps5-browser/ps5-browser-eldra3bayez.pkg",
                 "https://h0sss.github.io/bayz/ps5/", "umtx2", "13.60", "Debug Settings",
                 "FAT32", "etaHen", "بعد قفل الجهاز"]
    _br_missing = [n for n in _br_needs if n not in _br_page]
    if _br_missing:
        errors.append(f"[PS5-براوزر] نصوص ناقصة من صفحة المتصفح: {_br_missing}")
    else:
        passed.append("صفحة متصفح الدراع بايظ: الطريقتين + الرابط + الأقسام كاملة بالعربي ✓")
    import re as _re27
    for _ext27 in _re27.findall(r'href="(https?://[^"]+)"', _br_page):
        if "h0sss.github.io" not in _ext27:
            errors.append(f"[PS5-براوزر] رابط خارجي ممنوع في صفحة المتصفح: {_ext27}")
    if 'id="dlbtn"' not in _br_page and 'class="dlbtn"' not in _br_page:
        errors.append("[PS5-براوزر] زر التحميل المباشر (dlbtn) ناقص من الصفحة!")
if not os.path.exists(_br_pkg):
    errors.append("[PS5-براوزر] ملف الحزمة tools/ps5-browser/ps5-browser-eldra3bayez.pkg مش موجود!")
else:
    _sz27 = os.path.getsize(_br_pkg)
    with open(_br_pkg, "rb") as _f27:
        _head27 = _f27.read(4)
        _f27.seek(0)
        import hashlib as _hl27
        _sha27 = _hl27.sha256(_f27.read()).hexdigest()
    if _head27 != b"\x7fFIH":
        errors.append("[PS5-براوزر] ماجيك الحزمة غلط (لازم \\x7fFIH — حاوية PS5 debug)!")
    if _sz27 < 3000000 or _sz27 > 3800000:
        errors.append(f"[PS5-براوزر] حجم الحزمة غير منطقي: {_sz27} (المتوقع ~3.49MB)")
    if _sha27 != "e47bca38fedb8820b28fa7d448aa54a0a196b8887404d3cc011802b91a7eccfc":
        errors.append("[PS5-براوزر] بصمة SHA256 للحزمة تغيّرت — النسخة الحالية محمية بعقد الجودة (مولّد المشهد)")
    if _head27 == b"\x7fFIH" and _sha27 == "e47bca38fedb8820b28fa7d448aa54a0a196b8887404d3cc011802b91a7eccfc":
        passed.append(f"حزمة المتصفح سليمة: ماجيك \\x7fFIH + SHA256 متطابق + { _sz27:,}B ✓")
if "tools/ps5-browser/index.html" not in ps5_page or "زهدت من كتابة الرابط" not in ps5_page:
    errors.append("[PS5-براوزر] قسم المتصفح ناقص من ps5/index.html (لازم بعد «بعد النجاح» — رابط لأداة التثبيت)!")
else:
    passed.append("قسم متصفح الدراع بايظ موجود في صفحة PS5 (بعد النجاح) مع رابط الأداة ✓")
_lc27 = open("landing.appcache", encoding="utf-8").read()
for _n27 in ["tools/ps5-browser/index.html", "tools/ps5-browser/ps5-browser-eldra3bayez.pkg"]:
    if _n27 not in _lc27:
        errors.append(f"[PS5-براوزر] الملف مش مسجل في CACHE الـ landing.appcache: {_n27}")
if "landing-v17-browserpkg" not in _lc27:
    errors.append("[PS5-براوزر] rev الـ landing.appcache لازم يبقى v17-browserpkg!")
if "landing-v17-browserpkg" in _lc27 and "tools/ps5-browser/ps5-browser-eldra3bayez.pkg" in _lc27:
    passed.append("الكاش محدّث: rev v17-browserpkg + صفحة وحزمة المتصفح مسجلين ✓")

# ---------- النتيجة ----------
print()
print("=" * 60)
print(f"✅ نجح: {len(passed)}")
for p in passed: print("  ✔", p)
if warnings:
    print(f"⚠️ تحذيرات: {len(warnings)}")
    for w in warnings: print("  ⚠", w)
print("=" * 60)
if errors:
    print(f"❌ أخطاء: {len(errors)}")
    for e in errors: print("  ✘", e)
    sys.exit(1)
else:
    print("🎉 النتيجة النهائية: صفر أخطاء — جاهز للرفع")
