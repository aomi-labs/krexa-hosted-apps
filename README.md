# Krexa Hosted Apps

This repo hosts **Aomi app source for the Krexa platform**. It's a private B2B
publishing target — invite-only, not a general open-source contribution
surface. If you weren't granted write access by Krexa's platform ops, the
source you're looking for is somewhere else.

You **do not hand-edit `apps/<slug>/`**. That directory is staged for you by
the `aomi-git` CLI from your own source repo. This repo is the publishing
target — it's where releases get cut from.

## Contributing an app

👉 **Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) first.** It walks you through
the full pipeline tailored to the Krexa private-B2B flow.

The short version:

1. Krexa ops adds you as a collaborator on this repo (one-time).
2. In your own source repo, author your app with an `aomi.toml` declaring
   `platform = "krexa"`, `git = "https://github.com/aomi-labs/krexa-hosted-apps"`,
   and `access_token = "$ENV_VAR_NAME"` referencing a GH PAT env var.
3. Run `aomi-git deploy --platform-repo-dir /path/to/this/repo` — it stages
   your source under `apps/<slug>/`, commits, and pushes to `publish`.
4. GitHub Actions builds the cdylib and uploads a release tarball.
5. Hand off to Krexa ops: release tag + a one-shot read PAT. Ops runs
   `aomi-git activate` against the target backend with the Krexa platform
   token (held by them).

## Trust model

The Krexa flow has two distinct trust gates:

- **Repo write** — managed by GitHub collaborators on this repo. Controls
  who can push source into `apps/<slug>/`.
- **Backend activation** — managed by the Krexa platform's activation token,
  held by Krexa ops. Controls which releases actually load on the runtime.

The fetch GitHub PAT you supply at activation is **transient** per ADR 0009
amended: passed in the activation request body, used once by the backend to
download the tarball, never persisted, never logged, never stored. Krexa ops
should ask you for a fresh PAT each activation rather than holding one
long-lived shared secret.

## Repo layout

```
krexa-hosted-apps/
├── README.md           ← you are here
├── CONTRIBUTING.md     ← E2E Krexa contributor guide
├── platform.json       ← platform descriptor (see below)
├── apps/               ← generated source per app; one dir per slug
│   └── my-krexa-bot/
└── fixtures/
    └── hello-world/    ← buildable crate template; never deployed
```

## Publication contract

These facts are enforced by CI; they exist for reference.

| Field | Value |
|---|---|
| Publication branch | `publish` (protected: no force push, no delete) |
| Staged app path | `apps/<app_slug>/` |
| Build contract file | `apps/<app_slug>/.aomi-publish/manifest.json` (written by `aomi-git deploy`) |
| Release tag convention | `apps-{app_slug}-{short_commit}` |
| Default visibility | `private` |
| Required SDK version | see [`platform.json`](./platform.json) |

Each release contains:

- `aomi-plugins-{app_slug}-{short_commit}-{target}.tar.gz` — the runtime bundle
- `manifest.json` — release metadata
- `aomi-release.json` — provenance metadata (not a runtime trust boundary)

The backend trusts a release only after `PluginFetcher` validates the release
tag, exact SDK version, build target, and plugin SHA-256 hashes inside the
tarball — using a one-shot read PAT supplied at activation time.

## Platform descriptor (`platform.json`)

`platform.json` at the repo root is the **platform contract** — every rule
your app must meet to publish here. It's hand-authored by Krexa platform
ops and read by CI on every push.

| Field | Meaning | Touched by |
|---|---|---|
| `name` | Platform tier label (`krexa`). Match in your `aomi.toml` as `platform = "krexa"`. | Ops on platform bring-up |
| `source_repo` | This repo (`aomi-labs/krexa-hosted-apps`). CI verifies your `aomi.toml`'s `git` resolves here. | Ops |
| `publish_branch` | The branch `aomi-git deploy` pushes to. Protected against force-push and deletion. | Ops |
| `app_path_prefix` | Where staged apps land (`apps`). Combined with your slug → `apps/<slug>/`. | Ops |
| `release_tag_convention` | Pattern for GitHub release tags built from your source commit. | Ops |
| `visibility` | `private` — your apps default to private visibility on the backend. | Ops |
| `review_policy` | `platform-registration` — describes how contributions are vetted. Informational. | Ops |
| `required_sdk_version` | **The aomi-sdk version your app MUST pin in `Cargo.toml`.** Bundle validation fails on mismatch. | Ops on SDK bumps |
| `default_target` | Rust target triple CI builds for (`x86_64-unknown-linux-gnu`). | Ops |

You (the contributor) don't edit `platform.json`. You **read** the
`required_sdk_version` and pin it in your `Cargo.toml`. That's it.

When Krexa ops bumps `required_sdk_version`, you'll need to update your
app's pin to match before your next deploy.

## Build internals

The publish workflow at
[`.github/workflows/publish-apps.yml`](./.github/workflows/publish-apps.yml)
runs on push to `publish` and drives a small Python script tucked under
`.github/scripts/` that no contributor (or anyone) runs by hand — `aomi-git
deploy` and the workflow handle everything.

## Related

- [`aomi-sdk`](https://github.com/aomi-labs/aomi-sdk) — the SDK and the
  `aomi-git` deploy CLI
- [`aomi-labs/community-apps`](https://github.com/aomi-labs/community-apps) —
  the public community platform's analog of this repo
- [`aomi-launch-my-agent`](https://github.com/aomi-labs/aomi-launch-my-agent) —
  ADRs for the deploy/activate contract (especially 0004, 0009 amended, 0010)
