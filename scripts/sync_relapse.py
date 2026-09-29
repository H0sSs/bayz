#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_relapse.py — مزامنة استغلال Relapse (PS5 7.00–13.60) من المستودع الرسمي إلى ريبونا.

الوظيفة:
  1) ينزّل أحدث نسخة main من المستودع الرسمي (tarball).
  2) يطابق الملفات بايت-بايت مع ps5/relapse/ في الريبو.
  3) يحدّث الملفات المتغيّرة/الجديدة ويمسح المحذوفة (نسخة حرفية 100%).
  4) يولّد ps5/relapse-sync.json (مانيفست تكامل: sha256 + حجم لكل ملف).
  5) يطبع ملخصًا واضحًا (جديد/معدّل/محذوف/متطابق).

الاستخدام:
  python3 scripts/sync_relapse.py            # مزامنة فعلية
  python3 scripts/sync_relapse.py --dry-run  # تقرير فرق فقط بدون كتابة
  python3 scripts/sync_relapse.py --repo PATH  # تحديد مسار الريبو

ملاحظات:
  * الملفات تُنسخ حرفيًا بدون أي تعديل (LICENSE و README و كل شئ) — عشان
    التزامن يفضل مطابقة بايت-بايت مع المصدر.
  * المانيفست (relapse-sync.json) هو مرجع عقد التكامل في qa_check.py —
    QA بيتأكد إن كل ملف على القرص مطابق للمانيفست، فأي فساد أو تعديل
    يدوي هيكتشف فورًا.
  * صفحاتنا العربية (ps5/index.html و غيرها) مش جزء من المزامنة — دي
    ملكنا وإحنا اللي بنحكم فيها.
"""
import argparse
import hashlib
import json
import os
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

# ملفات مطلوبة بجودة qa_check.py — لو اختفت من المصدر ده معناه كسر عقد
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


def main():
    ap = argparse.ArgumentParser(description="مزامنة Relapse من المصدر الرسمي")
    ap.add_argument("--repo", default="/home/z/my-project/bayz_repo")
    ap.add_argument("--dry-run", action="store_true", help="تقرير فقط بدون كتابة")
    args = ap.parse_args()

    target_dir = os.path.join(args.repo, "ps5", "relapse")
    manifest_path = os.path.join(args.repo, "ps5", "relapse-sync.json")

    print("=" * 62)
    print(f"[sync] المصدر : {UPSTREAM_OWNER}/{UPSTREAM_REPO}@{UPSTREAM_BRANCH}")
    print(f"[sync] الهدف  : {target_dir}")
    print("=" * 62)

    with tempfile.TemporaryDirectory(prefix="relapse_sync_") as tmp:
        tarball = os.path.join(tmp, "relapse.tar.gz")
        print(f"[sync] جاري تنزيل أحدث نسخة ...")
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

        upstream = list_files(base)

        # التحقق من الملفات المطلوبة قبل أي كتابة
        missing = [f for f in REQUIRED_FILES if f not in upstream]
        if missing:
            print(f"[FAIL] المصدر ناقص ملفات أساسية (رفض المزامنة): {missing}")
            return 3

        local = list_files(target_dir) if os.path.isdir(target_dir) else {}

        added = sorted(set(upstream) - set(local))
        removed = sorted(set(local) - set(upstream))
        changed = sorted(
            f for f in set(upstream) & set(local)
            if sha256_file(upstream[f]) != sha256_file(local[f])
        )
        same = len(set(upstream) & set(local)) - len(changed)

        print(f"[sync] ملفات المصدر : {len(upstream)}")
        print(f"[sync] متطابقة      : {same}")
        print(f"[sync] جديدة        : {len(added)}")
        print(f"[sync] معدّلة       : {len(changed)}")
        print(f"[sync] محذوفة       : {len(removed)}")
        for f in added[:12]:
            print(f"   + {f}")
        for f in changed[:12]:
            print(f"   ~ {f}")
        for f in removed[:12]:
            print(f"   - {f}")

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
            # تنظيف المجلدات الفاضية
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
            "note": "نسخة حرفية بايت-بايت من المستودع الرسمي (رخصة MIT) — عقد التكامل في qa_check.py بيقارن الملفات بالمانيفست ده",
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

        # تحقق ذاتي نهائي: القرص == المانيفست
        bad = 0
        for rel, meta in manifest["files"].items():
            p = os.path.join(target_dir, rel)
            if not os.path.exists(p) or os.path.getsize(p) != meta["size"] or sha256_file(p) != meta["sha256"]:
                print(f"[FAIL] التحقق الذاتي فشل: {rel}")
                bad += 1
        if bad:
            return 4
        print("[sync] التحقق الذاتي: كل الملفات مطابقة للمانيفست ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
