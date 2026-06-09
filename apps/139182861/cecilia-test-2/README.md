# my-aomi-bots

A Hyperliquid perpetuals trading bot, packaged as an Aomi app for the
[`community`](https://github.com/aomi-labs/community-apps) platform.

## Tools exposed to the agent

| Tool | Auth | What it does |
|---|---|---|
| `get_meta` | none | List every Hyperliquid perp with size/price decimals & max leverage |
| `get_mid_price` | none | Current mid-price for a coin (e.g. `BTC`, `ETH`) |
| `get_user_state` | none | Read positions, margin, withdrawable for any wallet address |
| `get_open_orders` | none | List a wallet's resting orders (with oids for cancel) |
| `place_market_order` | `HL_WALLET_KEY` | IoC limit order at slipped mid (default 0.5%) |
| `cancel_order` | `HL_WALLET_KEY` | Cancel a resting order by oid |

Trading tools fail fast with a clear error when `HL_WALLET_KEY` is not
configured on the backend. **The signing path itself is a TODO** — see the
comments in `src/client.rs::Trader::submit_action` for the protocol reference
before wiring real trades.

## Layout

```
my-aomi-bots/
├── aomi.toml         # platform manifest — slug, platform, target_tags
├── Cargo.toml        # cdylib + aomi-sdk pinned to platform.json's required_sdk_version
├── src/
│   ├── lib.rs        # dyn_aomi_app! registration + preamble
│   ├── client.rs     # HTTP client, Trader scaffold, arg structs, action builders
│   └── tools.rs      # one impl DynAomiTool per tool
└── .gitignore        # /target, /.aomi/, Cargo.lock
```

## Publishing

Authoring lives here; publishing goes through the `aomi-git` CLI.

```bash
# 1. Compile check
cargo check

# 2. Dry-run preflight against staging
AOMI_BACKEND_URL=https://staging-api.aomi.dev \
  aomi-git deploy --dry-run --preflight

# 3. Stage + push to the community publish repo
aomi-git deploy --platform-repo-dir /path/to/community-apps
```

CI builds the cdylib and uploads a release tarball. Activation against the
backend is held by the community platform operator — ping them with the
release tag once CI is green.

See [`community-apps/CONTRIBUTING.md`](https://github.com/aomi-labs/community-apps/blob/main/CONTRIBUTING.md)
for the full pipeline walkthrough.

## TODOs

- [ ] Implement EIP-712 signing in `Trader::submit_action` (see protocol
      reference in the comment block). Reference impl:
      <https://github.com/hyperliquid-dex/hyperliquid-python-sdk>.
- [ ] Add a `set_leverage` tool once signing is wired up.
- [ ] Consider a `place_limit_order` variant with explicit `tif` (Gtc/Ioc/Alo).
