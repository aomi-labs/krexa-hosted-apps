#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import tomllib
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HEX_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{12,40}$")


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def run(
    cmd: list[str],
    *,
    cwd: pathlib.Path | None = None,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if capture and result.stderr else ""
        command = " ".join(cmd)
        fail(f"command failed ({command}): {detail}")
    return result.stdout.strip() if capture and result.stdout else ""


def git(args: list[str], *, capture: bool = True) -> str:
    return run(["git", *args], capture=capture)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
    except FileNotFoundError:
        fail(f"missing JSON file: {path}")
    except json.JSONDecodeError as err:
        fail(f"invalid JSON in {path}: {err}")
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_prefixed_file(path: pathlib.Path) -> str:
    return f"sha256:{sha256_file(path)}"


def relpath(path: pathlib.Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def current_branch() -> str:
    ref_name = os.environ.get("GITHUB_REF_NAME", "").strip()
    if ref_name:
        return ref_name
    return git(["branch", "--show-current"])


def current_commit() -> str:
    env_sha = os.environ.get("GITHUB_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        return git(["rev-parse", "--verify", "HEAD"])
    except SystemExit:
        return "uncommitted-local"


def normalize_github_repo(value: str) -> str:
    repo = value.strip()
    if repo.startswith("git@github.com:"):
        repo = repo.removeprefix("git@github.com:")
    elif repo.startswith("https://github.com/"):
        repo = repo.removeprefix("https://github.com/")
    elif repo.startswith("http://github.com/"):
        repo = repo.removeprefix("http://github.com/")
    repo = repo.removesuffix(".git").strip("/")
    return repo.lower()


def validate_platform_descriptor(descriptor: dict[str, Any]) -> None:
    required = [
        "name",
        "source_repo",
        "publish_branch",
        "app_path_prefix",
        "release_tag_convention",
        "visibility",
        "review_policy",
        "required_sdk_version",
        "default_target",
    ]
    for key in required:
        if not isinstance(descriptor.get(key), str) or not descriptor[key].strip():
            fail(f"platform descriptor field {key} must be a non-empty string")
    convention = descriptor["release_tag_convention"]
    if "{app_slug}" not in convention or "{short_commit}" not in convention:
        fail("release_tag_convention must contain {app_slug} and {short_commit}")


def expected_release_tag(descriptor: dict[str, Any], app_slug: str, source_commit: str) -> str:
    short_commit = source_commit[:12]
    return (
        descriptor["release_tag_convention"]
        .replace("{app_slug}", app_slug)
        .replace("{short_commit}", short_commit)
    )


def deployment_app_slug(deployment: dict[str, Any]) -> str:
    app = deployment.get("app")
    if not isinstance(app, dict):
        fail("deployment manifest app must be an object")
    value = app.get("name") or app.get("slug")
    if not isinstance(value, str) or not value:
        fail("deployment manifest app.name must be a non-empty string")
    return value


def app_dir_from_path(path: str, prefix: str) -> str | None:
    normalized = pathlib.PurePosixPath(path).as_posix()
    clean_prefix = prefix.strip("/")
    prefix_with_slash = f"{clean_prefix}/"
    if not normalized.startswith(prefix_with_slash):
        return None
    parts = normalized.split("/")
    if len(parts) < 2 or not parts[1]:
        return None
    return f"{clean_prefix}/{parts[1]}"


def changed_paths(base: str, head: str) -> list[str]:
    base = (base or "").strip()
    head = (head or "HEAD").strip()
    if base and not set(base) <= {"0"}:
        return git(["diff", "--name-only", base, head]).splitlines()
    try:
        return git(["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", head]).splitlines()
    except SystemExit:
        return git(["ls-tree", "-r", "--name-only", head]).splitlines()


def ensure_clean_app(app_dir: pathlib.Path, allow_dirty: bool) -> None:
    if allow_dirty:
        return
    status = git(["status", "--porcelain", "--", relpath(app_dir)])
    if status.strip():
        fail(f"{relpath(app_dir)} has uncommitted changes:\n{status}")


def parse_cargo_manifest(app_dir: pathlib.Path) -> tuple[str, str]:
    manifest_path = app_dir / "Cargo.toml"
    if not manifest_path.is_file():
        fail(f"{relpath(app_dir)} must contain Cargo.toml")
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    package = data.get("package")
    if not isinstance(package, dict) or not isinstance(package.get("name"), str):
        fail(f"{relpath(manifest_path)} must define [package].name")
    package_name = package["name"]
    lib = data.get("lib") if isinstance(data.get("lib"), dict) else {}
    lib_name = lib.get("name", package_name)
    crate_types = lib.get("crate-type", [])
    if "cdylib" not in crate_types:
        fail(f"{relpath(manifest_path)} must set [lib].crate-type = [\"cdylib\"]")
    return package_name, lib_name


def target_lib_ext(target: str) -> str:
    if "windows" in target:
        return "dll"
    if "apple" in target or "darwin" in target:
        return "dylib"
    if "linux" in target:
        return "so"
    fail(f"unsupported target triple: {target}")


def cargo_output_file_name(lib_name: str, target: str) -> str:
    base = lib_name.replace("-", "_")
    ext = target_lib_ext(target)
    if ext == "dll":
        return f"{base}.dll"
    return f"lib{base}.{ext}"


def plugin_file_name(plugin_name: str, target: str) -> str:
    return f"{plugin_name.replace('-', '_')}.{target_lib_ext(target)}"


def host_target() -> str:
    if sys.platform == "darwin":
        machine = run(["uname", "-m"])
        if machine == "arm64":
            return "aarch64-apple-darwin"
        if machine == "x86_64":
            return "x86_64-apple-darwin"
    if sys.platform.startswith("linux"):
        machine = run(["uname", "-m"])
        if machine == "x86_64":
            return "x86_64-unknown-linux-gnu"
        if machine in {"aarch64", "arm64"}:
            return "aarch64-unknown-linux-gnu"
    return "unknown"


def resolve_sdk_version(app_dir: pathlib.Path, lock_was_present: bool) -> str:
    manifest_path = (app_dir / "Cargo.toml").resolve()
    output = run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--manifest-path",
            str(manifest_path),
        ]
    )
    metadata = json.loads(output)
    packages = {pkg["id"]: pkg for pkg in metadata.get("packages", [])}
    root_pkg = None
    for pkg in packages.values():
        if pathlib.Path(pkg["manifest_path"]).resolve() == manifest_path:
            root_pkg = pkg
            break
    if root_pkg is None:
        fail(f"cargo metadata did not include root package for {manifest_path}")

    resolve = metadata.get("resolve") or {}
    nodes = {node["id"]: node for node in resolve.get("nodes", [])}
    root_node = nodes.get(root_pkg["id"])
    if root_node is None:
        fail("cargo metadata did not include a dependency graph for the app")

    sdk_pkg = None
    for dep in root_node.get("deps", []):
        package = packages.get(dep.get("pkg"))
        if package and package.get("name") == "aomi-sdk":
            sdk_pkg = package
            break
    if sdk_pkg is None:
        fail("app must depend directly on aomi-sdk so CI can prove SDK compatibility")

    cleanup_generated_lock(app_dir, lock_was_present)
    return sdk_pkg["version"]


def cleanup_generated_lock(app_dir: pathlib.Path, lock_was_present: bool) -> None:
    lock_path = app_dir / "Cargo.lock"
    if not lock_was_present and lock_path.exists():
        lock_path.unlink()


def codesign_if_needed(path: pathlib.Path, target: str) -> None:
    if sys.platform == "darwin" and target_lib_ext(target) == "dylib":
        run(["codesign", "-s", "-", "-f", str(path)], capture=False)


def inspect_plugin(path: pathlib.Path) -> tuple[str, dict[str, Any]]:
    lib = ctypes.CDLL(str(path))

    lib.aomi_sdk_version.restype = ctypes.c_char_p
    sdk_raw = lib.aomi_sdk_version()
    if not sdk_raw:
        fail("aomi_sdk_version returned null")
    sdk_version = sdk_raw.decode("utf-8")

    lib.aomi_create.restype = ctypes.c_void_p
    instance = lib.aomi_create()
    if not instance:
        fail("aomi_create returned null")

    try:
        lib.aomi_manifest.argtypes = [ctypes.c_void_p]
        lib.aomi_manifest.restype = ctypes.c_void_p
        manifest_ptr = lib.aomi_manifest(instance)
        if not manifest_ptr:
            fail("aomi_manifest returned null")
        try:
            manifest_json = ctypes.string_at(manifest_ptr).decode("utf-8")
        finally:
            lib.aomi_free_string.argtypes = [ctypes.c_void_p]
            lib.aomi_free_string(manifest_ptr)
    finally:
        lib.aomi_destroy.argtypes = [ctypes.c_void_p]
        lib.aomi_destroy(instance)

    try:
        manifest = json.loads(manifest_json)
    except json.JSONDecodeError as err:
        fail(f"plugin runtime manifest is invalid JSON: {err}")
    if not isinstance(manifest, dict):
        fail("plugin runtime manifest must be a JSON object")
    return sdk_version, manifest


def validate_runtime_manifest(manifest: dict[str, Any], sdk_version: str) -> str:
    required = ["sdk_version", "name", "version", "preamble", "tools"]
    for key in required:
        if key not in manifest:
            fail(f"plugin runtime manifest missing {key}")
    if manifest["sdk_version"] != sdk_version:
        fail(
            "plugin runtime manifest sdk_version does not match compiled aomi-sdk: "
            f"{manifest['sdk_version']} != {sdk_version}"
        )
    if not isinstance(manifest["name"], str) or not manifest["name"].strip():
        fail("plugin runtime manifest name must be a non-empty string")
    if not isinstance(manifest["tools"], list):
        fail("plugin runtime manifest tools must be an array")
    return manifest["name"]


def validate_deployment_manifest(
    stage: dict[str, Any],
    descriptor: dict[str, Any],
    app_dir: pathlib.Path,
    *,
    allow_fixture_app: bool,
) -> None:
    platform = stage.get("platform")
    if not isinstance(platform, dict):
        fail("deployment manifest platform must be an object")
    if platform.get("name") != descriptor["name"]:
        fail(f"deployment manifest platform.name must be {descriptor['name']}")
    github_repo = platform.get("github_repo")
    if not isinstance(github_repo, str) or normalize_github_repo(github_repo) != normalize_github_repo(
        descriptor["source_repo"]
    ):
        fail(f"deployment manifest platform.github_repo must resolve to {descriptor['source_repo']}")

    source = stage.get("source")
    target = stage.get("target")
    files = stage.get("files")
    if not isinstance(source, dict) or not isinstance(target, dict):
        fail("deployment manifest must contain source and target objects")
    if not isinstance(files, list) or not files:
        fail("deployment manifest files must be a non-empty array")

    app_slug = deployment_app_slug(stage)
    source_commit = source.get("commit")
    if not isinstance(source_commit, str) or not COMMIT_RE.match(source_commit):
        fail("deployment manifest source.commit must be a 12 to 40 character lowercase hex commit")

    expected_app_path = f"{descriptor['app_path_prefix'].strip('/')}/{app_slug}"
    if target.get("app_path") != expected_app_path:
        fail(f"deployment manifest target.app_path must be {expected_app_path}")
    if not allow_fixture_app and relpath(app_dir) != expected_app_path:
        fail(f"app directory must be {expected_app_path}")
    checks = {
        "branch": descriptor["publish_branch"],
        "release_tag": expected_release_tag(descriptor, app_slug, source_commit),
    }
    for key, expected in checks.items():
        if target.get(key) != expected:
            fail(f"deployment manifest target.{key} must be {expected}")

    expected_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if expected_repo and expected_repo != descriptor["source_repo"]:
        fail(f"workflow repository {expected_repo} does not match {descriptor['source_repo']}")

    seen_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            fail("deployment manifest files entries must be objects")
        rel = entry.get("path")
        sha = entry.get("sha256")
        byte_count = entry.get("bytes")
        if not isinstance(rel, str) or rel.startswith("/") or ".." in pathlib.PurePosixPath(rel).parts:
            fail(f"invalid staged file path: {rel!r}")
        if rel in seen_paths:
            fail(f"duplicate staged file path: {rel}")
        seen_paths.add(rel)
        path = app_dir / rel
        if not path.is_file():
            fail(f"staged file missing from app directory: {rel}")
        expected_sha = sha256_prefixed_file(path)
        if sha != expected_sha:
            fail(f"staged file sha256 mismatch for {rel}: {sha} != {expected_sha}")
        if byte_count != path.stat().st_size:
            fail(f"staged file byte count mismatch for {rel}")


def validate_branch(descriptor: dict[str, Any], allow_non_publish_branch: bool) -> None:
    branch = current_branch()
    if not allow_non_publish_branch and branch != descriptor["publish_branch"]:
        fail(f"must run on {descriptor['publish_branch']} branch, got {branch or '<unknown>'}")


def validate_bundle_manifest(
    manifest: dict[str, Any],
    descriptor: dict[str, Any],
    *,
    release_tag: str,
    target: str,
    commit: str,
    plugins_dir: pathlib.Path,
) -> None:
    expected_keys = {"app_release_tag", "sdk_version", "target", "commit", "plugins"}
    missing = expected_keys - set(manifest)
    if missing:
        fail(f"bundle manifest missing fields: {', '.join(sorted(missing))}")
    if manifest["app_release_tag"] != release_tag:
        fail("bundle manifest app_release_tag does not match release tag")
    if manifest["sdk_version"] != descriptor["required_sdk_version"]:
        fail(
            "bundle manifest sdk_version does not match platform required_sdk_version: "
            f"{manifest['sdk_version']} != {descriptor['required_sdk_version']}"
        )
    if manifest["target"] != target:
        fail("bundle manifest target does not match tarball target")
    if manifest["commit"] != commit:
        fail("bundle manifest commit does not match staged source commit")
    plugins = manifest["plugins"]
    if not isinstance(plugins, dict) or not plugins:
        fail("bundle manifest plugins must be a non-empty object")
    for name, entry in plugins.items():
        if not isinstance(name, str) or not name:
            fail("bundle manifest plugin names must be non-empty strings")
        if not isinstance(entry, dict):
            fail(f"bundle manifest plugin {name} entry must be an object")
        file_name = entry.get("file")
        digest = entry.get("sha256")
        if not isinstance(file_name, str) or "/" in file_name or "\\" in file_name:
            fail(f"bundle manifest plugin {name} has invalid file name")
        if not isinstance(digest, str) or not HEX_SHA_RE.match(digest):
            fail(f"bundle manifest plugin {name} sha256 must be lowercase hex without prefix")
        plugin_path = plugins_dir / file_name
        if not plugin_path.is_file():
            fail(f"bundle manifest plugin file is missing: {file_name}")
        if sha256_file(plugin_path) != digest:
            fail(f"bundle manifest plugin {name} sha256 does not match file")


def validate_tarball(tarball: pathlib.Path, manifest: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory(prefix="aomi-bundle-check-") as tmp:
        tmp_path = pathlib.Path(tmp)
        with tarfile.open(tarball, "r:gz") as archive:
            archive.extractall(tmp_path, filter="data")
        plugins_dir = tmp_path / "plugins"
        extracted = load_json(plugins_dir / "manifest.json")
        if extracted != manifest:
            fail("tarball plugins/manifest.json does not match generated bundle manifest")
        for name, entry in manifest["plugins"].items():
            plugin_path = plugins_dir / entry["file"]
            if sha256_file(plugin_path) != entry["sha256"]:
                fail(f"tarball plugin checksum mismatch for {name}")


def build_bundle(args: argparse.Namespace) -> None:
    descriptor = load_json(pathlib.Path(args.platform))
    validate_platform_descriptor(descriptor)
    validate_branch(descriptor, args.allow_non_publish_branch)

    app_dir = (REPO_ROOT / args.app_dir).resolve()
    if not app_dir.is_dir():
        fail(f"app directory does not exist: {args.app_dir}")
    if not str(app_dir).startswith(str(REPO_ROOT)):
        fail("app directory must be inside the repository")

    ensure_clean_app(app_dir, args.allow_dirty)
    stage_path = app_dir / ".aomi" / "deployment.json"
    stage = load_json(stage_path)
    validate_deployment_manifest(stage, descriptor, app_dir, allow_fixture_app=args.allow_fixture_app)

    app_slug = deployment_app_slug(stage)
    source_commit = stage["source"]["commit"]
    release_tag = stage["target"]["release_tag"]
    target = args.target or descriptor["default_target"]
    if args.inspect_plugin and target != host_target():
        fail(f"plugin inspection requires host target {host_target()}, got {target}")

    lock_path = app_dir / "Cargo.lock"
    lock_was_present = lock_path.exists()
    package_name, lib_name = parse_cargo_manifest(app_dir)
    sdk_version = resolve_sdk_version(app_dir, lock_was_present)
    if sdk_version != descriptor["required_sdk_version"]:
        fail(
            "resolved aomi-sdk version does not match product-mono host contract: "
            f"{sdk_version} != {descriptor['required_sdk_version']}"
        )

    target_dir = REPO_ROOT / ".aomi-ci-target"
    dist_dir = (REPO_ROOT / args.dist_dir).resolve()
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    plugins_dir = dist_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    try:
        run(
            [
                "cargo",
                "build",
                "--lib",
                "--release",
                "--target",
                target,
                "--target-dir",
                str(target_dir),
                "--manifest-path",
                str(app_dir / "Cargo.toml"),
            ],
            capture=False,
        )
    finally:
        cleanup_generated_lock(app_dir, lock_was_present)

    built_lib = target_dir / target / "release" / cargo_output_file_name(lib_name, target)
    if not built_lib.is_file():
        fail(f"expected built library not found: {built_lib}")

    copied = plugins_dir / cargo_output_file_name(lib_name, target)
    shutil.copy2(built_lib, copied)
    codesign_if_needed(copied, target)

    if args.inspect_plugin:
        plugin_sdk_version, runtime_manifest = inspect_plugin(copied)
        if plugin_sdk_version != sdk_version:
            fail(f"aomi_sdk_version symbol {plugin_sdk_version} does not match cargo {sdk_version}")
        plugin_name = validate_runtime_manifest(runtime_manifest, sdk_version)
    else:
        plugin_name = package_name

    final_plugin = plugins_dir / plugin_file_name(plugin_name, target)
    if copied != final_plugin:
        copied.rename(final_plugin)

    bundle_manifest = {
        "app_release_tag": release_tag,
        "sdk_version": sdk_version,
        "target": target,
        "commit": source_commit,
        "plugins": {
            plugin_name: {
                "file": final_plugin.name,
                "sha256": sha256_file(final_plugin),
            }
        },
    }
    validate_bundle_manifest(
        bundle_manifest,
        descriptor,
        release_tag=release_tag,
        target=target,
        commit=source_commit,
        plugins_dir=plugins_dir,
    )
    manifest_path = plugins_dir / "manifest.json"
    write_json(manifest_path, bundle_manifest)

    short_commit = source_commit[:12]
    tarball = dist_dir / f"aomi-plugins-{app_slug}-{short_commit}-{target}.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(manifest_path, arcname="plugins/manifest.json")
        archive.add(final_plugin, arcname=f"plugins/{final_plugin.name}")
    validate_tarball(tarball, bundle_manifest)

    standalone_manifest = dist_dir / "manifest.json"
    shutil.copy2(manifest_path, standalone_manifest)

    release_metadata = {
        "platform": descriptor["name"],
        "app_slug": app_slug,
        "visibility": descriptor["visibility"],
        "review_policy": descriptor["review_policy"],
        "source": stage["source"],
        "publish": {
            "repo": descriptor["source_repo"],
            "branch": stage["target"]["branch"],
            "path": stage["target"]["app_path"],
            "commit": current_commit(),
            "release_tag": release_tag,
        },
        "sdk_version": sdk_version,
        "targets": [target],
        "deployment_manifest_sha256": sha256_prefixed_file(stage_path),
        "created_by": os.environ.get("GITHUB_ACTOR", "repo-ci"),
        "status": {
            "ci": "candidate-release-built",
            "runtime_live": False,
            "runtime_boundary": "product-mono fetch/load validation",
        },
        "assets": {
            "tarball": tarball.name,
            "manifest": "manifest.json",
            "release_metadata": "aomi-release.json",
        },
    }
    release_metadata_path = dist_dir / "aomi-release.json"
    write_json(release_metadata_path, release_metadata)

    notes = textwrap.dedent(
        f"""\
        Aomi hosted app candidate release.

        - Platform: {descriptor["name"]}
        - App: {app_slug}
        - Source commit: {source_commit}
        - SDK version: {sdk_version}
        - Target: {target}
        - Runtime status: not live until product-mono fetches, validates, and loads this bundle

        Assets:
        - {tarball.name}
        - manifest.json
        - aomi-release.json
        """
    )
    (dist_dir / "release-notes.md").write_text(notes, encoding="utf-8")

    outputs = {
        "release_tag": release_tag,
        "tarball": relpath(tarball),
        "manifest": relpath(standalone_manifest),
        "release_metadata": relpath(release_metadata_path),
    }
    for key, value in outputs.items():
        print(f"{key}={value}")
    if args.github_output:
        with pathlib.Path(args.github_output).open("a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")


def detect_changed(args: argparse.Namespace) -> None:
    descriptor = load_json(pathlib.Path(args.platform))
    validate_platform_descriptor(descriptor)
    validate_branch(descriptor, args.allow_non_publish_branch)

    prefix = descriptor["app_path_prefix"]
    if args.app_dir:
        app_dirs = [args.app_dir.strip()]
    else:
        paths = changed_paths(args.base, args.head)
        app_dirs = sorted(
            {
                app_dir
                for path in paths
                if (app_dir := app_dir_from_path(path, prefix)) is not None
            }
        )

    valid_app_dirs: list[str] = []
    for app_dir_str in app_dirs:
        app_dir = REPO_ROOT / app_dir_str
        if not app_dir.is_dir():
            fail(f"changed app directory does not exist: {app_dir_str}")
        stage_path = app_dir / ".aomi" / "deployment.json"
        if not stage_path.is_file():
            fail(f"{app_dir_str} is missing .aomi/deployment.json")
        stage = load_json(stage_path)
        validate_deployment_manifest(stage, descriptor, app_dir, allow_fixture_app=False)
        valid_app_dirs.append(app_dir_str)

    apps_json = json.dumps(valid_app_dirs)
    print(apps_json)
    if args.github_output:
        with pathlib.Path(args.github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"apps={apps_json}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish Aomi hosted app bundles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect-changed")
    detect.add_argument("--platform", default="ci/platform.json")
    detect.add_argument("--base", default="")
    detect.add_argument("--head", default="HEAD")
    detect.add_argument("--app-dir", default="")
    detect.add_argument("--github-output")
    detect.add_argument("--allow-non-publish-branch", action="store_true")
    detect.set_defaults(func=detect_changed)

    build = subparsers.add_parser("build")
    build.add_argument("--platform", default="ci/platform.json")
    build.add_argument("--app-dir", required=True)
    build.add_argument("--target")
    build.add_argument("--dist-dir", default="dist")
    build.add_argument("--github-output")
    build.add_argument("--allow-dirty", action="store_true")
    build.add_argument("--allow-fixture-app", action="store_true")
    build.add_argument("--allow-non-publish-branch", action="store_true")
    build.add_argument("--no-inspect-plugin", dest="inspect_plugin", action="store_false")
    build.set_defaults(func=build_bundle, inspect_plugin=True)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
