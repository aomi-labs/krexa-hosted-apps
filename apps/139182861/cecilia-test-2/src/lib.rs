//! Hyperliquid trading bot — scaffold app for the Aomi `community` platform.
//!
//! What this app exposes to the agent:
//!   * Read-only tools (no signing, no env vars needed):
//!       - `get_meta`         — list all perpetuals on Hyperliquid
//!       - `get_mid_price`    — current mid-price for a coin (e.g. "BTC")
//!       - `get_user_state`   — positions, margin, withdrawable for a wallet
//!       - `get_open_orders`  — open orders for a wallet
//!   * Trading tools (require `HL_WALLET_KEY` env var on the backend):
//!       - `place_market_order` — IoC market-style order via Hyperliquid's limit
//!         endpoint at a slipped price
//!       - `cancel_order`       — cancel a resting order by oid
//!
//! See `src/client.rs` for the Hyperliquid HTTP surface and EIP-712 signing
//! primitives; see `src/tools.rs` for tool definitions.

use aomi_sdk::*;

mod client;
mod tools;

const PREAMBLE: &str = r#"## Role
You are a Hyperliquid perpetuals trading assistant.

## Capabilities
- Look up the universe of perp markets (`get_meta`).
- Quote live mid-prices (`get_mid_price`).
- Read a wallet's positions, margin, and open orders (`get_user_state`, `get_open_orders`).
- Place market orders (`place_market_order`) and cancel resting orders
  (`cancel_order`). Trading requires the backend operator to have configured
  the `HL_WALLET_KEY` env var; without it, trading tools return a clear error.

## Guardrails
- Always confirm `coin`, `side`, `size`, and an approximate notional with the
  user before placing a trade.
- Default to `reduce_only = true` when closing positions.
- If a tool returns an error mentioning `HL_WALLET_KEY`, tell the user that
  trading is not configured on this deployment and stop — do not retry.
"#;

dyn_aomi_app!(
    app = client::HyperliquidApp,
    name = "cecilia-test-2",
    version = "0.1.0",
    preamble = PREAMBLE,
    tools = [
        tools::GetMeta,
        tools::GetMidPrice,
        tools::GetUserState,
        tools::GetOpenOrders,
        tools::PlaceMarketOrder,
        tools::CancelOrder,
    ],
    namespaces = []
);
