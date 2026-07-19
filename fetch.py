#!/usr/bin/env python3
"""Fetch Analog Devices (Maxim) SVD files from the msdk repo, incrementally.

On every run the script first does a cheap metadata check: it asks the
remote for its HEAD sha with 'git ls-remote' (no artifact download) and
compares it with the sha recorded in manifest.json. If the shas match and
the local tree is complete, it prints 'up to date' and exits 0 without
touching anything.

Only when the remote moved, or manifest.json / the family tree is missing or
incomplete, does it do a partial sparse clone of analogdevicesinc/msdk,
pull the SVD files from Libraries/CMSIS/Device/Maxim/*/Include/, validate
them with xml.etree (well-formed, root element 'device'), lay them out
under <Family>/ at the repo root, refresh LICENSES/msdk-LICENSE.txt, and
rewrite manifest.json with the new sha and the current date. The temporary
clone in .work/ is removed after a successful run.

Python 3 stdlib only (git is called via subprocess). Works on Linux and
Windows. Run from anywhere: python fetch.py
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / ".work"
MSDK = WORK / "msdk"
# Family folders now live directly at the repo root, so the SVD output base
# is ROOT itself (no 'svd/' subdir any more).
SVD_BASE = ROOT
LICENSES_DIR = ROOT / "LICENSES"
MANIFEST = ROOT / "manifest.json"
REPO_URL = "https://github.com/analogdevicesinc/msdk"
SPARSE_PATH = "Libraries/CMSIS/Device/Maxim"
SOURCE_NAME = "msdk"

# Entries at the repo root that are NOT family directories and must never be
# removed by the full-rebuild cleanup.
PROTECTED = {".git", ".github", ".gitignore", ".work", "LICENSES",
             "README.md", "manifest.json", "fetch.py"}

# Number of artifact downloads performed this run (metadata requests such
# as 'git ls-remote' are not counted). Every artifact download is logged
# with a 'DOWNLOAD' line so runs are auditable.
DOWNLOADS = 0


def run(cmd, **kw):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def capture(cmd):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, capture_output=True,
                          text=True).stdout


def remote_head_sha():
    """Metadata-only check: sha of the remote HEAD via git ls-remote."""
    out = capture(["git", "ls-remote", REPO_URL, "HEAD"])
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "HEAD":
            return parts[0]
    raise RuntimeError("could not parse ls-remote output: %r" % out)


def load_manifest():
    if not MANIFEST.is_file():
        return None
    try:
        with MANIFEST.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("manifest.json unreadable (%s), forcing full fetch" % e)
        return None


def recorded_sha(manifest):
    if not manifest:
        return None
    for src in manifest.get("sources", []):
        if src.get("name") == SOURCE_NAME:
            return src.get("version")
    return None


def tree_complete(manifest):
    """True if every file the manifest lists is actually on disk."""
    if not manifest:
        return False
    entries = manifest.get("files", [])
    if not entries:
        return False
    for entry in entries:
        if not (ROOT / entry["path"]).is_file():
            return False
    if not (LICENSES_DIR / "msdk-LICENSE.txt").is_file():
        return False
    return True


def rmtree_force(path):
    """shutil.rmtree that clears the read-only bit first (git objects on
    Windows are read-only and plain rmtree fails on them)."""
    def onerror(func, p, exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def clean_family_dirs():
    """Full-rebuild cleanup: remove only the family directories at the repo
    root, never the protected top-level entries (.git, LICENSES, fetch.py,
    README.md, manifest.json, ...). The output base is now ROOT itself, so a
    blanket rmtree(SVD_BASE) would delete the whole repo; this walks ROOT and
    deletes just the non-protected subdirectories instead."""
    for child in ROOT.iterdir():
        if child.is_dir() and child.name not in PROTECTED:
            rmtree_force(child)


def clone():
    global DOWNLOADS
    if MSDK.exists():
        print("removing stale clone " + MSDK.as_posix())
        rmtree_force(MSDK)
    WORK.mkdir(parents=True, exist_ok=True)
    DOWNLOADS += 1
    print("DOWNLOAD [%d]: sparse clone of %s (%s)"
          % (DOWNLOADS, REPO_URL, SPARSE_PATH))
    run(["git", "clone", "--filter=blob:none", "--depth", "1",
         "--sparse", REPO_URL, MSDK.as_posix()])
    run(["git", "-C", MSDK.as_posix(), "sparse-checkout", "set",
         SPARSE_PATH])
    sha = capture(["git", "-C", MSDK.as_posix(), "rev-parse",
                   "HEAD"]).strip()
    print("msdk HEAD: " + sha)
    return sha


def family_for(device):
    if device.upper().startswith("MAX78"):
        return "MAX78"
    if device.upper().startswith("MAX32"):
        return "MAX32"
    return "OTHER"


def validate_svd(path):
    """Return None if OK, else an error string."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return "XML parse error: %s" % e
    root_tag = tree.getroot().tag
    # strip a namespace if present
    if "}" in root_tag:
        root_tag = root_tag.split("}", 1)[1]
    if root_tag != "device":
        return "root element is '%s', expected 'device'" % root_tag
    return None


def rebuild_from_clone(sha):
    """Extract, validate and lay out the SVD files from the fresh clone,
    refresh the license copy, and rewrite manifest.json."""
    found = sorted((MSDK / SPARSE_PATH).glob("*/Include/*.svd"))
    if not found:
        print("ERROR: no SVD files matched %s/*/Include/*.svd"
              % (MSDK / SPARSE_PATH).as_posix())
        return 1
    print("found %d SVD files" % len(found))

    # This repo has a single source, so all families belong to it and are
    # replaced together. Only family directories are removed; the protected
    # top-level entries (and .git) are left untouched.
    clean_family_dirs()

    files_entries = []
    issues = []
    total_bytes = 0
    for src in found:
        err = validate_svd(src)
        device = src.stem.upper()
        if err:
            issues.append("%s skipped: %s" % (src.name, err))
            print("SKIP %s (%s)" % (src.name, err))
            continue
        fam = family_for(device)
        out_dir = SVD_BASE / fam
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / (device + ".svd")
        shutil.copyfile(src, dest)
        total_bytes += dest.stat().st_size
        files_entries.append({
            "path": "%s/%s.svd" % (fam, device),
            "device": device,
            "family": fam,
            "source": SOURCE_NAME,
            "provenance": "pristine",
        })

    # license
    LICENSES_DIR.mkdir(parents=True, exist_ok=True)
    lic_src = MSDK / "LICENSE"
    lic_dest = LICENSES_DIR / "msdk-LICENSE.txt"
    lic_note = "not found"
    if not lic_src.is_file():
        # LICENSE sits at the repo root, outside the sparse cone; in cone
        # mode git still checks out root files, but fall back to a direct
        # git show if it is missing.
        try:
            out = subprocess.run(
                ["git", "-C", MSDK.as_posix(), "show", "HEAD:LICENSE"],
                check=True, capture_output=True).stdout
            lic_dest.write_bytes(out)
            lic_note = "retrieved via git show HEAD:LICENSE"
        except subprocess.CalledProcessError:
            issues.append("msdk root LICENSE not found in clone")
    else:
        shutil.copyfile(lic_src, lic_dest)
        lic_note = "copied from repo root"
    print("license: " + lic_note)

    manifest = {
        "vendor": "Analog Devices (Maxim)",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "sources": [{
            "name": SOURCE_NAME,
            "url": REPO_URL,
            "version": sha,
            "license": "Apache-2.0",
            "files": len(files_entries),
        }],
        "files": files_entries,
        "stats": {
            "total_files": len(files_entries),
            "total_bytes": total_bytes,
        },
    }
    if issues:
        manifest["issues"] = issues
    with MANIFEST.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print("wrote %d files, %.1f MB" %
          (len(files_entries), total_bytes / 1e6))
    for i in issues:
        print("issue: " + i)
    return 0


def main():
    remote_sha = remote_head_sha()
    manifest = load_manifest()
    local_sha = recorded_sha(manifest)

    if local_sha == remote_sha and tree_complete(manifest):
        print("up to date")
        print("artifact downloads: 0")
        return 0

    if local_sha != remote_sha:
        print("msdk changed: %s -> %s" % (local_sha, remote_sha))
    else:
        print("local tree incomplete, rebuilding from msdk")

    sha = clone()
    rc = rebuild_from_clone(sha)
    if WORK.exists():
        rmtree_force(WORK)
        print("cleaned up " + WORK.as_posix())
    print("artifact downloads: %d" % DOWNLOADS)
    return rc


if __name__ == "__main__":
    sys.exit(main())
