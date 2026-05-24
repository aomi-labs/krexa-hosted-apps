# Krexa Hosted Apps

This repository is a private hosted source repo for Krexa Aomi dynamic apps.

## Publication Contract

- Required publication branch: `publish`
- Staged app path: `apps/<app_slug>/`
- Staging manifest: `apps/<app_slug>/.aomi-publish/manifest.json`
- Release tag convention: `apps-{app_slug}-{short_commit}`
- Runtime bundle contract: `aomi-plugin-bundle-v1`
- Required SDK version: see `ci/platform.json`

`short_commit` is the first 12 characters of the source commit recorded by
`aomi-git` in `.aomi-publish/manifest.json`.

## Expected Release Assets

For each changed staged app directory on `publish`, CI builds the configured
target and publishes a GitHub release named by the staged expected release tag.
Each release contains:

- `aomi-plugins-{app_slug}-{short_commit}-{target}.tar.gz`
- `manifest.json`
- `aomi-release.json`

The tarball contains `plugins/manifest.json` plus the compiled plugin library.
`product-mono` trusts the tarball only after `PluginFetcher` validates the
release tag, exact SDK version, target, and plugin SHA-256 hashes.
`aomi-release.json` is provenance/status metadata only; it is not a runtime
trust boundary.

## Local Dry Run

Use the fixture app to exercise the same packaging code without creating a
GitHub release:

```bash
python3 scripts/publish_app.py build \
  --platform ci/platform.json \
  --app-dir examples/hello-ci \
  --target "$(rustc -vV | sed -n 's/^host: //p')" \
  --dist-dir dist \
  --allow-non-publish-branch \
  --allow-fixture-app \
  --allow-dirty
```

The production workflow does not pass the `allow-*` flags. It must run from
the `publish` branch, under `apps/<app_slug>/`, with committed staged source.

Krexa publication uses the same bundle workflow as community publication. The
private-repo difference is on the consuming side: product-mono backend
instances need release read credentials when fetching private GitHub assets.
