# Krexa Aomi Launch

This guide shows how a Krexa platform developer publishes a custom Aomi dynamic
app through `krexa-hosted-apps` and makes it load in the production Aomi runtime.
The example app slug is `my-krexa-bot`.

## What This Flow Does

1. Build and validate a Rust `cdylib` app against the production Aomi SDK line.
2. Use `aomi-git` to stage the app into `apps/<app_slug>/` on the `publish`
   branch.
3. Let `krexa-hosted-apps` CI build a Linux plugin bundle release.
4. Activate the release through the Aomi backend admin endpoint.
5. Verify production sees the app source in Supabase, fetches the release, and
   loads the plugin.

Krexa hosted apps are private by default. They should be activated with
`--visibility private` unless the platform intentionally wants public access.

## Repository Contract

- Repo: `aomi-labs/krexa-hosted-apps`
- Branch: `publish`
- Staged app path: `apps/<app_slug>/`
- Release tag shape: `apps-<app_slug>-<short_source_commit>`
- Bundle target: `x86_64-unknown-linux-gnu`
- Runtime source repo value: `aomi-labs/krexa-hosted-apps`

Production `product-mono` must have a GitHub token available as `GITHUB_TOKEN`
inside the backend container so it can fetch private release assets.

## Example App Layout

Keep editable source separate from the staged release copy:

```text
source/my-krexa-bot/
  Cargo.toml
  src/lib.rs
apps/my-krexa-bot/
  Cargo.toml
  src/lib.rs
  .aomi-publish/manifest.json
```

`apps/my-krexa-bot/` is written by `aomi-git`; do not hand-edit the publish
manifest.

Minimal `Cargo.toml`:

```toml
[package]
name = "my-krexa-bot"
version = "0.1.0"
edition = "2024"
description = "My Krexa Bot"
publish = false

[lib]
crate-type = ["cdylib"]

[dependencies]
aomi-sdk = "=0.1.19"
schemars = "1.0"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

Minimal tool/app shape:

```rust
use aomi_sdk::{dyn_aomi_app, DynAomiTool, DynToolCallCtx};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::Value;

#[derive(Clone, Default)]
struct MyKrexaBotApp;

#[derive(Debug, Deserialize, JsonSchema)]
struct ReplyArgs {
    message: String,
}

struct ReplyTool;

impl DynAomiTool for ReplyTool {
    type App = MyKrexaBotApp;
    type Args = ReplyArgs;

    const NAME: &'static str = "my_krexa_bot_reply";
    const DESCRIPTION: &'static str = "Reply from the example Krexa-hosted Aomi bot.";

    fn run(
        _app: &MyKrexaBotApp,
        args: Self::Args,
        _ctx: DynToolCallCtx,
    ) -> Result<Value, String> {
        Ok(serde_json::json!({
            "bot": "my-krexa-bot",
            "reply": format!("Krexa bot heard: {}", args.message),
        }))
    }
}

dyn_aomi_app!(
    app = MyKrexaBotApp,
    name = "my-krexa-bot",
    version = "0.1.0",
    preamble = "You are My Krexa Bot, a minimal Krexa-hosted Aomi dynamic app.",
    tools = [ReplyTool],
    namespaces = ["common"]
);
```

## Publish Steps

Run these from a clean checkout:

```bash
cd /Users/cecilia/Code/krexa-hosted-apps
git switch publish
git pull --ff-only origin publish

cargo check --manifest-path source/my-krexa-bot/Cargo.toml
git add source/my-krexa-bot
git commit -m "Add my-krexa-bot source"
```

Preview the publish plan:

```bash
cd /Users/cecilia/Code/product-mono/aomi
cargo run -p aomi-git -- deploy \
  --path /Users/cecilia/Code/krexa-hosted-apps/source/my-krexa-bot \
  --platform krexa \
  --dry-run
```

Publish through the Krexa repo:

```bash
cargo run -p aomi-git -- deploy \
  --path /Users/cecilia/Code/krexa-hosted-apps/source/my-krexa-bot \
  --platform krexa \
  --platform-repo-dir /Users/cecilia/Code/krexa-hosted-apps
```

Expected output includes:

- `publish_app_path : apps/my-krexa-bot`
- `expected_release_tag : apps-my-krexa-bot-<short_source_commit>`
- `visibility : private`
- `pushed : true`

## Verify CI Release

Watch the publish workflow:

```bash
gh run list --repo aomi-labs/krexa-hosted-apps --branch publish --limit 5
gh run watch <run_id> --repo aomi-labs/krexa-hosted-apps --exit-status
```

Inspect the release:

```bash
gh release view apps-my-krexa-bot-<short_source_commit> \
  --repo aomi-labs/krexa-hosted-apps \
  --json tagName,url,assets
```

The release must include:

- `aomi-plugins-my-krexa-bot-<short_source_commit>-x86_64-unknown-linux-gnu.tar.gz`
- `manifest.json`
- `aomi-release.json`

`manifest.json` must report the production SDK version and plugin name:

```json
{
  "version": "aomi-plugin-bundle-v1",
  "app_release_tag": "apps-my-krexa-bot-<short_source_commit>",
  "sdk_version": "0.1.19",
  "target": "x86_64-unknown-linux-gnu",
  "plugins": {
    "my-krexa-bot": {
      "file": "my_krexa_bot.so"
    }
  }
}
```

## Activate In Production

Activation is a platform/admin operation. The backend token is not committed to
the repo.

```bash
cd /Users/cecilia/Code/product-mono/aomi

AOMI_APP_ACTIVATION_TOKEN="<prod activation token>" \
cargo run -p aomi-git -- activate apps-my-krexa-bot-<short_source_commit> \
  --platform krexa \
  --backend-url https://api.aomi.dev \
  --visibility private \
  --label "My Krexa Bot" \
  --source-commit <full_source_commit> \
  --source-tree <source_tree_hash> \
  --source-digest sha256:<source_digest> \
  --json
```

This writes or updates `public.applications` with:

- `name = my-krexa-bot`
- `is_active = true`
- `is_public = false`
- `source_repo = aomi-labs/krexa-hosted-apps`
- `app_release_tag = apps-my-krexa-bot-<short_source_commit>`

## Verify Production Load

Check the backend status surface:

```bash
curl -fsS https://api.aomi.dev/api/control/apps/status | jq '
{
  sources: [.sources[] | select(.descriptor.source_repo == "aomi-labs/krexa-hosted-apps")],
  app: [.apps[] | select(.name == "my-krexa-bot")]
}'
```

The successful state is:

- source `present = true`
- source `cache.app_release_tag = apps-my-krexa-bot-<short_source_commit>`
- source `cache.plugins` contains `my-krexa-bot`
- app `registered = true`
- app `is_active = true`
- app `is_public = false`
- app `source_configured = true`
- app `source_names` contains `krexa-hosted-apps`
- app `loaded = true`
- runtime metadata includes `my_krexa_bot_reply`

Direct DB check:

```bash
psql "$SUPABASE_DB_URL" -P pager=off -x -c "
select name, label, is_active, is_public, source_repo, app_release_tag, metadata
from public.applications
where name = 'my-krexa-bot';
"
```

## Known Failure Modes

- Source row exists but cache is `present=false`: production cannot fetch the
  GitHub release. For private Krexa releases, confirm backend has `GITHUB_TOKEN`
  with access to `aomi-labs/krexa-hosted-apps`.
- Cache is present but app is not loaded: check SDK version, target, plugin
  file hash, and active registry state.
- App is loaded but unavailable to public clients: expected for Krexa private
  apps. Create app keys or platform-scoped access rather than flipping
  `is_public` unless public access is intended.

## Verified Example

The `my-krexa-bot` flow was verified against production with:

- source commit: `05c1c90205de9f1a52435086f9d216661a30d6e3`
- release tag: `apps-my-krexa-bot-05c1c90205de`
- source repo: `aomi-labs/krexa-hosted-apps`
- runtime tool: `my_krexa_bot_reply`
- production state: registered, active, private, source configured, and loaded
