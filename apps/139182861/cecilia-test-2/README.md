# my-aomi-bots

Hosted app smoke-test source for the `krexa` platform. This branch intentionally
contains two tracked `aomi.toml` files so the deploy path can exercise a
multi-app payload.

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
├── aomi.toml         # app one: cecilia-test-2
├── Cargo.toml        # cdylib + aomi-sdk pinned to platform.json's required_sdk_version
├── apps/
│   └── cecilia-test-3/
│       ├── aomi.toml # app two: cecilia-test-3
│       ├── Cargo.toml
│       └── src/lib.rs
├── src/
│   ├── lib.rs        # dyn_aomi_app! registration + preamble
│   ├── client.rs     # HTTP client, Trader scaffold, arg structs, action builders
│   └── tools.rs      # one impl DynAomiTool per tool
└── .gitignore        # /target, /.aomi/, Cargo.lock
```

## Publishing

Authoring lives here; publishing goes through the hosted deploy commands in
`aomi-build`.

```bash
# 1. Compile check
cargo check
cargo check --manifest-path apps/cecilia-test-3/Cargo.toml

# 2. Deploy both tracked app manifests
aomi-build deploy --platform krexa --branch e2e/krexa-rust-cli-20260609

# 3. Activate from the generated local deployment state
aomi-build activate --path .
```

The deploy command writes `.aomi/deployment.json`; activation reads the release
tags from that file and syncs the activation result back into it.

## TODOs

- [ ] Implement EIP-712 signing in `Trader::submit_action` (see protocol
      reference in the comment block). Reference impl:
      <https://github.com/hyperliquid-dex/hyperliquid-python-sdk>.
- [ ] Add a `set_leverage` tool once signing is wired up.
- [ ] Consider a `place_limit_order` variant with explicit `tif` (Gtc/Ioc/Alo).
