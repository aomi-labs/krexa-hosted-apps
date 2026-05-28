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
├── apps/               ← generated source per app; one dir per slug
│   └── my-krexa-bot/
├── ci/
│   └── platform.json   ← CI contract: required SDK version, build target, etc.
├── fixtures/
│   └── hello-ci/       ← buildable crate for maintainer ad-hoc dry-runs
└── scripts/
    └── publish_app.py  ← internal build script driven by Actions; not for contributors
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
| Required SDK version | see [`ci/platform.json`](./ci/platform.json) |

Each release contains:

- `aomi-plugins-{app_slug}-{short_commit}-{target}.tar.gz` — the runtime bundle
- `manifest.json` — release metadata
- `aomi-release.json` — provenance metadata (not a runtime trust boundary)

The backend trusts a release only after `PluginFetcher` validates the release
tag, exact SDK version, build target, and plugin SHA-256 hashes inside the
tarball — using a one-shot read PAT supplied at activation time.

## Build internals

CI is driven by [`scripts/publish_app.py`](./scripts/publish_app.py), invoked
from [`.github/workflows/publish-apps.yml`](./.github/workflows/publish-apps.yml)
on push to `publish`. Contributors don't run either directly — `aomi-git
deploy` and the workflow handle it.

## Related

- [`aomi-sdk`](https://github.com/aomi-labs/aomi-sdk) — the SDK and the
  `aomi-git` deploy CLI
- [`aomi-labs/community-apps`](https://github.com/aomi-labs/community-apps) —
  the public community platform's analog of this repo
- [`aomi-launch-my-agent`](https://github.com/aomi-labs/aomi-launch-my-agent) —
  ADRs for the deploy/activate contract (especially 0004, 0009 amended, 0010)
