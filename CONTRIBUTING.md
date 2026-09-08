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
