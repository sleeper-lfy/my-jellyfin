"""Publish the verified 0.4.26 build and retire the explicitly approved old releases."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

REPO = "sleeper-lfy/my-jellyfin"
TAG = "v0.4.26-preview.1"
SOURCE = "a64f599452bd779c444558c933c57ce4c0183f8f"
BUILD_RUN = 46114710729
BUILD_COMMIT = "0c1acbe683aebba11473cfe94a37ae0c9e7758cc"
LOCAL = Path(".local").resolve()
VERIFICATION = LOCAL / "preview-0.4.26-public-verification.json"
PLAN = LOCAL / "preview-0.4.26-release-cleanup-plan.json"
RESULT = LOCAL / "preview-0.4.26-release-cleanup-result.json"
OLD_RELEASES = {
    "v0.4.25-preview.1": 455609344,
    "v0.4.24-preview.1": 446582932,
    "v0.4.23-preview.1": 445179803,
    "v0.4.22-preview.1": 445021725,
    "v0.4.21-preview.1": 442570305,
    "v0.4.20-preview.3": 441875017,
    "v0.4.19-preview.1": 441204932,
    "v0.4.18-preview.2": 440680185,
    "v0.4.17-preview.1": 440558275,
    "v0.4.16-preview.2": 440456835,
    "v0.4.15-preview.2": 440397056,
    "v0.4.15-preview.1": 440384006,
    "v0.4.14-preview.11": 440317585,
    "v0.4.14-preview.10": 440280428,
    "v0.4.14-preview.7": 438106906,
    "v0.4.14-preview.5": 435196693,
    "v0.4.14-preview.4": 434185655,
    "v0.4.14-preview.3": 434005011,
    "v0.4.14-preview.1": 433866989
}
ARTIFACTS = {
    "windows": (15251222864, "e82805e0fa21142a7dbc9401a6720f90d414b7c7e58e83d476d03b0fa09de973"),
    "android": (15251406215, "eb5e376eb1d5f70262a0db33b327a878eb9533d0360d323f3a88d8a53e0b2d52"),
}
ASSET_NAMES = {
    "Lumen-Setup-x64.exe", "Lumen-Setup-x64.exe.sha256",
    "Lumen-android-debug.apk", "Lumen-android-debug.apk.sha256",
    "windows-acceptance.json", "android-verification.json",
}


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", "api", *args], text=True))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def release_list():
    pages = gh_json("--paginate", "--slurp", f"repos/{REPO}/releases?per_page=100")
    return [release for page in pages for release in page]


def tag_source():
    return gh_json(f"repos/{REPO}/git/ref/tags/{TAG}")["object"]["sha"]


def publish():
    run = gh_json(f"repos/{REPO}/actions/runs/{BUILD_RUN}")
    assert (run["conclusion"], run["head_sha"]) == ("success", BUILD_COMMIT)
    checkout = LOCAL / "release-source"
    subprocess.run(["git", "worktree", "add", "--detach", str(checkout), SOURCE], check=True)
    shutil.copyfile("docs/releases/0.4.26.md", checkout / "docs/releases/0.4.26.md")
    for platform, (artifact_id, checksum) in ARTIFACTS.items():
        metadata = gh_json(f"repos/{REPO}/actions/artifacts/{artifact_id}")
        assert not metadata["expired"] and metadata["workflow_run"]["id"] == BUILD_RUN
        assert metadata["digest"] == f"sha256:{checksum}"
        archive = LOCAL / f"{platform}.zip"
        with archive.open("wb") as output:
            subprocess.run(
                ["gh", "api", f"repos/{REPO}/actions/artifacts/{artifact_id}/zip"],
                stdout=output, check=True,
            )
        assert archive.stat().st_size == metadata["size_in_bytes"] and digest(archive) == checksum
        destination = checkout / ".local" / f"preview-{platform}"
        with ZipFile(archive) as package:
            assert all(Path(name).name == name for name in package.namelist())
            package.extractall(destination)

    windows = checkout / ".local/preview-windows"
    android = checkout / ".local/preview-android"
    subprocess.run(
        [sys.executable, "-c", """
import json
from pathlib import Path
import runpy
import sys

windows, android = map(Path, sys.argv[1:3])
report = json.loads((windows / 'acceptance.json').read_text(encoding='utf-8-sig'))
proof = json.loads((android / 'android-verification.json').read_text())
assert proof['version_code'] == 45
runpy.run_path('scripts/preview-release.py')['validate_artifacts'](
    windows / 'Lumen-Setup-x64.exe', android / 'Lumen-android-debug.apk',
    report, proof, sys.argv[3], '0.4.26',
)
""", str(windows), str(android), SOURCE],
        cwd=checkout, check=True,
    )
    matches = subprocess.check_output(["git", "ls-remote", "origin", f"refs/tags/{TAG}"], text=True)
    if not matches:
        gh_json(f"repos/{REPO}/git/refs", "--method", "POST",
                "-f", f"ref=refs/tags/{TAG}", "-f", f"sha={SOURCE}")
    assert tag_source() == SOURCE
    subprocess.run(
        [sys.executable, "scripts/preview-release.py", "publish"],
        cwd=checkout, check=True,
        env={**os.environ, "GITHUB_REF_NAME": TAG, "GITHUB_SHA": SOURCE},
    )


def current_preview(releases):
    release, = (item for item in releases if item["tag_name"] == TAG)
    assert release["prerelease"] and not release["draft"] and tag_source() == SOURCE
    assert {asset["name"] for asset in release["assets"]} == ASSET_NAMES
    return release


def asset_identity(release):
    return sorted(
        [asset["id"], asset["name"], asset["size"], asset["digest"]]
        for asset in release["assets"]
    )


def verify():
    release = current_preview(release_list())
    checkout = LOCAL / "release-source/.local"

    def check(asset):
        name = asset["name"]
        platform = "android" if "android" in name else "windows"
        original = checkout / f"preview-{platform}" / name
        expected_digest = digest(original)
        expected_size = original.stat().st_size
        assert asset["size"] == expected_size and asset["digest"] == f"sha256:{expected_digest}"
        for attempt in range(4):
            try:
                with urlopen(asset["browser_download_url"], timeout=60) as response:
                    assert response.status == 200
                    count = 0
                    checksum = hashlib.sha256()
                    while data := response.read(1024 * 1024):
                        count += len(data)
                        assert count <= expected_size
                        checksum.update(data)
                break
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        assert count == expected_size and checksum.hexdigest() == expected_digest, name
        print(f"Verified public download: {name} {count} {expected_digest}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(check, release["assets"]))
    write_json(VERIFICATION, {
        "id": release["id"], "source": SOURCE, "tag": TAG, "assets": asset_identity(release)
    })


def releases_for_cleanup():
    releases = release_list()
    preview = current_preview(releases)
    verification = json.loads(VERIFICATION.read_text())
    assert verification == {
        "id": preview["id"], "source": SOURCE, "tag": TAG, "assets": asset_identity(preview)
    }
    older = [item for item in releases if item["id"] != preview["id"]]
    for item in older:
        assert item["prerelease"] and not item["draft"]
        assert OLD_RELEASES.get(item["tag_name"]) == item["id"], item["tag_name"]
    return preview, older


def tag_refs():
    refs = subprocess.check_output(["git", "ls-remote", "--tags", "origin"], text=True)
    return sorted(refs.splitlines())


def plan():
    preview, older = releases_for_cleanup()
    write_json(PLAN, {"preview": preview, "older": older, "tag_refs": tag_refs()})
    print("Retained:", TAG, "Old previews:", [item["tag_name"] for item in older], flush=True)


def cleanup():
    saved = json.loads(PLAN.read_text())
    preview, older = releases_for_cleanup()
    identity = lambda releases: sorted((item["id"], item["tag_name"]) for item in releases)
    assert preview["id"] == saved["preview"]["id"] and identity(older) == identity(saved["older"])
    result = {"deleted": [], "remaining": [], "tags_preserved": False}
    try:
        for item in older:
            release_id = item["id"]
            endpoint = f"repos/{REPO}/releases/{release_id}"
            fresh = gh_json(endpoint)
            assert fresh["tag_name"] == item["tag_name"] and fresh["prerelease"] and not fresh["draft"]
            subprocess.run(["gh", "api", "--method", "DELETE", endpoint], check=True)
            result["deleted"].append(item["tag_name"])
            print("Removed release:", item["tag_name"], flush=True)
        remaining, still_older = releases_for_cleanup()
        assert not still_older
        result["remaining"] = [remaining["tag_name"]]
        result["tags_preserved"] = tag_refs() == saved["tag_refs"]
        assert result["tags_preserved"]
    finally:
        write_json(RESULT, result)


if __name__ == "__main__":
    assert os.environ["GH_REPO"] == REPO
    LOCAL.mkdir(exist_ok=True)
    {"publish": publish, "verify": verify, "plan": plan, "cleanup": cleanup}[sys.argv[1]]()
