# Contributing an app

1. Author the app in your own source repository. Both Cargo workspaces and
   standalone crates are supported; no restructuring is required.
2. Declare the platform and application manifest paths in `.aomi/config.json`.
   Each app needs an `aomi.toml`, a `cdylib` Cargo target, and the SDK version
   required by the current Aomi runtime. Commit Cargo.lock at its workspace root.
3. Connect the repository through the Aomi GitHub App, or start with the template
   in Aomi Build. Review required configuration and choose Deploy.
4. Manager pins the selected branch's latest commit and stages the complete
   source snapshot in this platform repository. The platform workflow validates,
   builds, publishes, activates, and checks actual runtime readiness.
5. Follow progress in Project → Deployments. A failure shows its stage, app,
   step, commit, diagnostic excerpt and GitHub log link. After fixing code or
   configuration, retry builds the latest code; complete same-commit releases
   are reused. Prior attempts remain available.

No GitHub workflow is required in your source repository. Source snapshots
follow the platform repository's visibility; public platform snapshots remain
public in Git history. See [DEPLOYMENT.md](DEPLOYMENT.md) for limits, rollout
requirements and the platform workflow contract.

## `aomi.toml` reference

```toml
[app]
name         = "my-krexa-app"       # app slug; staged under apps/<installation-id>/<repo-key>/<name>
display_name = "My Krexa App"       # human-readable
platform     = "krexa"              # must match this platform repository
public       = false                # keep partner apps private

# Optional: backend classes allowed to load this app. Omit to default to ["staging"].
# server_tags = ["staging"]
```

Do not put GitHub tokens or a `git` field in `aomi.toml`. Source access is bound
to the repository connected through the Aomi GitHub App; the manifest only
describes the app and its target platform.

`Cargo.toml` must declare `crate-type = ["cdylib"]` and pin `aomi-sdk` to the
exact version the deployment requires (shown in Aomi Build; `platform.json`
records the platform default). Commit `Cargo.lock` at the workspace root.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `commit Cargo.lock at the Cargo workspace root before deploying` | `Cargo.lock` is missing or ignored | commit it at the workspace or package root, push, retry |
| `cargo ... --locked` fails | `Cargo.lock` is stale relative to `Cargo.toml` | run `cargo update` or `cargo generate-lockfile` locally, commit, retry |
| `aomi-sdk X does not match required Y` | the `aomi-sdk` pin differs from the deployment's SDK version | pin the exact required version and redeploy |
| `deployment manifest source repo does not match branch owner/repo` | the staged manifest names a different source repository | redeploy through Aomi Build; do not edit staged files by hand |
| `Source archive contains unsafe paths or links` / `exceeds the build size limit` | symlinks, `..` paths, files over 10 MiB or more than 256 MiB expanded | remove links and large or generated files from the source repository |
| `an incomplete or conflicting immutable release exists` | a release tag for this app and commit exists with missing assets or at another candidate | a platform maintainer repairs or removes the release, or push a new source commit |
| `Push a new source commit and retry` | an older, partially published candidate has no complete source snapshot | push a new commit and deploy again |
| `Configure AOMI_PLATFORM_TOKEN` | the GitHub environment secret is missing on this platform repository | a platform maintainer adds it to the `staging`/`production` environment |
| `Activation needs attention` | required configuration (secrets) is missing for the app | fill the Environment tab in Aomi Build, then retry |
| `Runtime verification timed out` | the runtime never reported the exact release ready | retry the deployment or roll back the app in Aomi Build |
| `Another attempt already owns this deployment request` | a same-commit retry was queued while an earlier attempt was still running | nothing to do; the earlier attempt's result stands |
