#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_relapse.py — مزامنة استغلال Relapse (PS5 7.00–13.60) من المستودع الرسمي إلى ريبونا.

الوظيفة:
  1) ينزّل أحدث نسخة main من المستودع الرسمي (tarball).
  2) يتحقق الأول من عقدين قبل أي كتابة:
     - عقود الملفات: كل الملفات الأساسية موجودة في المصدر.
     - عقود السلوك: آلية إرسال البيلودات (watchR2 في main.js +
       loadOptionalPayloads في kexp.js) والبيلودات الخمسة موجودة بأحجام منطقية.
  3) لو المصدر خالف العقود (زي ما حصل 2026-09-30 لما شطب آلية R2 والبيلودات)
     السكريبت بيقف فورًا بكود خروج 5 (انحراف المصدر) من غير أي كتابة —
     الموقع يفضل شغال على آخر نسخة كاملة، والمراجعة تبقى يدوية.
  4) لو العقود سليمة: يطابق الملفات بايت-بايت مع ps5/ في الريبو (ملفات
     الاستغلال جوه ps5/ مباشرة) ويحدّث المتغيّر/الجديد ويمسح المحذوف.
  5) يولّد ps5/relapse-sync.json (مانيفست تكامل: sha256 + حجم لكل ملف).
  6) يراقب صفحة المصدر الإنجليزية (index.html بتاعتهم) — دي مستبدلة بصفحتنا
     العربية الموحدة ps5/index.html، فلو المصدر غيّر صفحته (سكريبتات جديدة
     مثلًا) السكريبت بيطبع تحذير مراجعة بدل ما يكتب فوق صفحتنا.

أكواد الخروج:
  0 = تمام (اتزامنت أو مفيش تغييرات)
  2 = فشل التنزيل/الفك (عابر — جرّب تاني)
  3 = المصدر ناقص ملفات أساسية (انحراف — حماية)
  4 = فشل التحقق الذاتي بعد الكتابة (خطأ حقيقي)
  5 = المصدر خرق عقود السلوك (انحراف — حماية، محتاج مراجعة يدوية)

الاستخدام:
  python3 scripts/sync_relapse.py            # مزامنة فعلية
  python3 scripts/sync_relapse.py --dry-run  # تقرير فرق فقط بدون كتابة
  python3 scripts/sync_relapse.py --repo PATH  # تحديد مسار الريبو

ملاحظات:
  * ملفات المصدر تُنسخ حرفيًا بدون أي تعديل (LICENSE و README و كل شئ) — عشان
    التزامن يفضل مطابقة بايت-بايت مع المصدر.
  * إحنا مثبّتين على snapshot كاملة بتاريخ 2026-09-29 (قبل شطب upstream
    لآلية البيلودات) — دي اللي شغالة على الموقع، وعقود السلوك بتحميها.
  * ملفاتنا الخاصة (ps5/index.html صفحة التفعيل العربية + ps5/relapse-sync.json)
    محمية بالكامل — المزامنة عمرها ما بتلمسها أو تمسحها.
  * المانيفست (relapse-sync.json) هو مرجع عقد التكامل في qa_check.py —
    QA بيتأكد إن كل ملف على القرص مطابق للمانيفست، فأي فساد أو تعديل
    يدوي هيكتشف فورًا.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request

UPSTREAM_OWNER = "ntfargo"
UPSTREAM_REPO = "Relapse-Exploit"
UPSTREAM_BRANCH = "main"
TARBALL_URL = f"https://codeload.github.com/{UPSTREAM_OWNER}/{UPSTREAM_REPO}/tar.gz/refs/heads/{UPSTREAM_BRANCH}"

# صفحة المصدر الإنجليزية — مستبدلة بصفحتنا العربية الموحدة (مش بتتنسخ)
UPSTREAM_SHELL = "index.html"

# ملفاتنا الخاصة جوه ps5/ — ملكنا ومحمية من المزامنة أبدًا
OUR_FILES = {"index.html", "relapse-sync.json", "cache.appcache"}
# cache.appcache: كاش أوفلاين صفحة التفعيل — ملفنا زي صفحتنا (محمي من المزامنة والحذف)

# ملفات مطلوبة بجودة qa_check.py — لو اختفت من المصدر ده معناه انحراف
REQUIRED_FILES = [
    "index.html",
    "LICENSE",
    "src/firmware.js",
    "src/site.js",
    "src/main.js",
    "src/rop.js",
    "src/kexp.js",
    "src/relapse_exploit.js",
    "src/webkit.js",
    "src/utils/syscalls.js",
    "offsets/7.00.js",
    "offsets/13.60.js",
    "payloads/etaHEN.elf",
    "payloads/kstuff.elf",
    "payloads/shadowmountplus.elf",
    "payloads/elfldr-ps5-1360.elf",
    "payloads/kexp_2026_05_25.bin",
]

# عقود السلوك — دي اللي بتخلي الموقع يقدّم الجيلبريك الكامل (زر ← R2 ← etaHEN).
# لو المصدر شطبها المزامنة بتقف (خروج 5) من غير أي كتابة.
BEHAVIOR_CONTRACTS = {
    "src/main.js": "watchR2",
    "src/kexp.js": "loadOptionalPayloads",
}

# أحجام دنيا للبيلودات — حماية من ملفات فاسدة/فاضية من المصدر
PAYLOAD_MIN = {
    "payloads/etaHEN.elf": 1000000,
    "payloads/kstuff.elf": 500000,
    "payloads/shadowmountplus.elf": 500000,
    "payloads/elfldr-ps5-1360.elf": 100000,
    "payloads/kexp_2026_05_25.bin": 10000,
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "bayz-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    return os.path.getsize(dest)


def list_files(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = full
    return out


def check_behavior_contracts(upstream_all):
    """فحص عقود السلوك على ملفات المصدر — يرجّع قائمة المخالفات."""
    violations = []
    for rel, marker in BEHAVIOR_CONTRACTS.items():
        p = upstream_all.get(rel)
        if not p:
            violations.append(f"ملف السلوك اختفى من المصدر: {rel}")
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            body = f.read()
        if marker not in body:
            violations.append(f"{rel} فقد الآلية: '{marker}'")
    for rel, min_size in PAYLOAD_MIN.items():
        p = upstream_all.get(rel)
        if not p:
            violations.append(f"بيلود اختفى من المصدر: {rel}")
            continue
        size = os.path.getsize(p)
        if size < min_size:
            violations.append(f"بيلود مشتبه في المصدر (أصغر من {min_size}B): {rel} ({size}B)")
    return violations


def shell_script_srcs(html_text):
    """استخراج مسارات السكريبتات اللي صفحة المصدر بتشغلها (لمقارنتها بصفحتنا)."""
    srcs = []
    for m in re.finditer(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']", html_text):
        src = m.group(1).strip()
        if src.startswith("./"):
            src = src[2:]
        srcs.append(src)
    return srcs


def our_page_script_srcs(html_text):
    """مسارات السكريبتات اللي صفحتنا العربية بتشغلها (السلسلة + الموديول)."""
    srcs = []
    m = re.search(r'CHAIN\s*=\s*\[(.*?)\]', html_text, re.S)
    if m:
        srcs += re.findall(r'["\']([^"\']+)["\']', m.group(1))
    m = re.search(r'MODULE_ENTRY\s*=\s*["\']([^"\']+)["\']', html_text)
    if m:
        srcs.append(m.group(1))
    return srcs


def main():
    ap = argparse.ArgumentParser(description="مزامنة Relapse من المصدر الرسمي إلى ps5/ مباشرة (بعقود سلوك حامية)")
    ap.add_argument("--repo", default="/home/z/my-project/bayz_repo")
    ap.add_argument("--dry-run", action="store_true", help="تقرير فقط بدون كتابة")
    args = ap.parse_args()

    target_dir = os.path.join(args.repo, "ps5")
    manifest_path = os.path.join(args.repo, "ps5", "relapse-sync.json")

    print("=" * 62)
    print(f"[sync] المصدر : {UPSTREAM_OWNER}/{UPSTREAM_REPO}@{UPSTREAM_BRANCH}")
    print(f"[sync] الهدف  : {target_dir} (الملفات جوه ps5/ مباشرة)")
    print(f"[sync] محميّ  : {', '.join(sorted(OUR_FILES))} — ملكنا ومش بتتلمس")
    print(f"[sync] عقود السلوك : {' + '.join(f'{k}~{v}' for k, v in BEHAVIOR_CONTRACTS.items())}")
    print("=" * 62)

    with tempfile.TemporaryDirectory(prefix="relapse_sync_") as tmp:
        tarball = os.path.join(tmp, "relapse.tar.gz")
        print("[sync] جاري تنزيل أحدث نسخة ...")
        try:
            size = download(TARBALL_URL, tarball)
        except Exception as e:
            print(f"[FAIL] تعذّر التنزيل: {e}")
            return 2
        print(f"[sync] اتنزّل {size/1024/1024:.2f} MB")

        extract_dir = os.path.join(tmp, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with tarfile.open(tarball, "r:gz") as tar:
            try:
                tar.extractall(extract_dir, filter="data")  # py3.12+ أرشيف آمن
            except TypeError:
                tar.extractall(extract_dir)  # توافق مع الأقدم
        entries = os.listdir(extract_dir)
        base = os.path.join(extract_dir, entries[0])
        if len(entries) != 1 or not os.path.isdir(base):
            print(f"[FAIL] بنية الأرشيف غير متوقعة: {entries}")
            return 2

        upstream_all = list_files(base)

        # عقد 1: الملفات الأساسية موجودة في المصدر
        missing = [f for f in REQUIRED_FILES if f not in upstream_all]
        if missing:
            print()
            print("[DRIFT] ⚠ المصدر ناقص ملفات أساسية — المزامنة مرفوضة (حماية):")
            for f in missing:
                print(f"   - {f}")
            print("[DRIFT] الموقع هيفضل شغال على النسخة الكاملة المثبتة عندنا — محتاج مراجعة يدوية.")
            return 3

        # عقد 2: عقود السلوك (آلية R2 + البيلودات) سليمة في المصدر
        violations = check_behavior_contracts(upstream_all)
        if violations:
            print()
            print("[DRIFT] ⚠ المصدر خرق عقود السلوك — المزامنة مرفوضة (حماية):")
            for v in violations:
                print(f"   - {v}")
            print("[DRIFT] دي بتحصل لما المصدر يشطب آلية إرسال البيلودات أو يغيّر معماريته.")
            print("[DRIFT] الموقع هيفضل شغال على النسخة الكاملة المثبتة (زر التفعيل ← R2 ← etaHEN).")
            print("[DRIFT] للانتقال لسلوك المصدر الجديد: مراجعة يدوية + تحديث صفحة ps5/index.html أولًا.")
            return 5

        # صفحة المصدر الإنجليزية مستبدلة بصفحتنا — بتتفحص وبتتراقب بس
        upstream = {k: v for k, v in upstream_all.items() if k != UPSTREAM_SHELL}

        local = list_files(target_dir) if os.path.isdir(target_dir) else {}
        local_sync = {k: v for k, v in local.items() if k not in OUR_FILES}

        added = sorted(set(upstream) - set(local_sync))
        removed = sorted(set(local_sync) - set(upstream))
        changed = sorted(
            f for f in set(upstream) & set(local_sync)
            if sha256_file(upstream[f]) != sha256_file(local_sync[f])
        )
        same = len(set(upstream) & set(local_sync)) - len(changed)

        print(f"[sync] ملفات المصدر (غير الصفحة) : {len(upstream)}")
        print(f"[sync] متطابقة                  : {same}")
        print(f"[sync] جديدة                    : {len(added)}")
        print(f"[sync] معدّلة                   : {len(changed)}")
        print(f"[sync] محذوفة                   : {len(removed)}")
        for f in added[:12]:
            print(f"   + {f}")
        for f in changed[:12]:
            print(f"   ~ {f}")
        for f in removed[:12]:
            print(f"   - {f}")

        # مراقبة صفحة المصدر: لو اتغيرت عن آخر مزامنة نحذّر بمراجعة سلسلة السكريبتات
        old_manifest = {}
        if os.path.exists(manifest_path):
            try:
                old_manifest = json.load(open(manifest_path, encoding="utf-8"))
            except Exception:
                old_manifest = {}
        new_shell_sha = sha256_file(upstream_all[UPSTREAM_SHELL])
        old_shell_sha = (old_manifest.get("custom_page") or {}).get("upstream_shell_sha256")
        if old_shell_sha and old_shell_sha != new_shell_sha:
            print()
            print("[REVIEW] ⚠ صفحة المصدر الإنجليزية اتغيرت من آخر مزامنة!")
            shell_html = open(upstream_all[UPSTREAM_SHELL], encoding="utf-8", errors="replace").read()
            theirs = shell_script_srcs(shell_html)
            our_page_path = os.path.join(target_dir, "index.html")
            ours = []
            if os.path.exists(our_page_path):
                ours = our_page_script_srcs(open(our_page_path, encoding="utf-8", errors="replace").read())
            missing_in_ours = [s for s in theirs if s not in ours]
            extra_in_ours = [s for s in ours if s not in theirs]
            if missing_in_ours:
                print(f"[REVIEW] سكريبتات جديدة في صفحة المصدر غير موجودة في صفحتنا: {missing_in_ours}")
                print("[REVIEW] لازم تضيفها لسلسلة التشغيل في ps5/index.html (CHAIN / MODULE_ENTRY)")
            if extra_in_ours:
                print(f"[REVIEW] سكريبتات في صفحتنا مش موجودة في صفحة المصدر الجديدة: {extra_in_ours}")
            if not missing_in_ours and not extra_in_ours:
                print("[REVIEW] سلسلة السكريبتات متطابقة — التغيير شكلي غالبًا (تحديث يدوي غير مطلوب)")
            print()
        elif not old_shell_sha:
            print("[sync] أول تسجيل لمراقبة صفحة المصدر (custom_page.upstream_shell_sha256).")

        if args.dry_run:
            print("[sync] وضع --dry-run: لم يتم أي تغيير.")
            return 0

        if added or removed or changed or not os.path.exists(manifest_path):
            # نسخ حرفية
            for f in added + changed:
                dest = os.path.join(target_dir, f)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(upstream[f], dest)
            for f in removed:
                os.remove(os.path.join(target_dir, f))
            # تنظيف المجلدات الفاضية (من غير ما نلمس ps5/ نفسها ولا ملفاتنا)
            for dirpath, dirs, files in os.walk(target_dir, topdown=False):
                if not dirs and not files and dirpath != target_dir:
                    os.rmdir(dirpath)
            print("[sync] تم تحديث الملفات على القرص.")
        else:
            print("[sync] كل حاجة متطابقة بالفعل — لا تغييرات.")

        # توليد المانيفست (دائمًا يتحدّث بالمزامنة الحقيقية)
        manifest = {
            "source": f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}@{UPSTREAM_BRANCH}",
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "upstream_url": TARBALL_URL,
            "note": "نسخة حرفية بايت-بايت من المستودع الرسمي (رخصة MIT) — الملفات جوه ps5/ مباشرة. صفحة التفعيل العربية ps5/index.html ملكنا وبتستبدل صفحة المصدر الإنجليزية (محمية من المزامنة). عقد التكامل في qa_check.py بيقارن الملفات بالمانيفست ده",
            "custom_page": {
                "path": "index.html",
                "replaces": "صفحة المصدر الإنجليزية — صفحة التفعيل العربية الموحدة (زر تفعيل + شريط حالة + سجل تقني)",
                "protected": True,
                "upstream_shell_sha256": new_shell_sha,
            },
            "file_count": len(upstream),
            "total_bytes": sum(os.path.getsize(p) for p in upstream.values()),
            "files": {
                rel: {"sha256": sha256_file(upstream[rel]), "size": os.path.getsize(upstream[rel])}
                for rel in sorted(upstream)
            },
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print(f"[sync] المانيفست اتحدّث: ps5/relapse-sync.json ({manifest['file_count']} ملف / {manifest['total_bytes']/1024/1024:.2f} MB)")

        # تحقق ذاتي نهائي: القرص == المانيفست + صفحتنا موجودة
        bad = 0
        for rel, meta in manifest["files"].items():
            p = os.path.join(target_dir, rel)
            if not os.path.exists(p) or os.path.getsize(p) != meta["size"] or sha256_file(p) != meta["sha256"]:
                print(f"[FAIL] التحقق الذاتي فشل: {rel}")
                bad += 1
        for ours in sorted(OUR_FILES):
            if not os.path.exists(os.path.join(target_dir, ours)):
                print(f"[FAIL] ملف خاص ناقص: ps5/{ours}")
                bad += 1
        if bad:
            return 4
        print("[sync] التحقق الذاتي: كل ملفات المصدر مطابقة للمانيفست + صفحتنا العربية موجودة ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
