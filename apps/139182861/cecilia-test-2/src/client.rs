//! Hyperliquid HTTP client + trader scaffold.
//!
//! Hyperliquid exposes two POST endpoints:
//!   * `/info`     — read-only market & account data, no auth
//!   * `/exchange` — order placement / cancellation, requires an EIP-712
//!                   signature over the action payload
//!
//! Read tools call `InfoClient::post`. Trading tools build a `Trader` from the
//! `HL_WALLET_KEY` env var; submitting a signed action is left as a clearly
//! marked TODO (see `Trader::submit_action`).

use serde_json::{Value, json};
use std::time::Duration;

/// Mainnet endpoint. Switch to <https://api.hyperliquid-testnet.xyz> when you
/// want to point this bot at testnet instead.
pub(crate) const API_BASE: &str = "https://api.hyperliquid.xyz";

/// The plugin "app" handle. Aomi requires one per `dyn_aomi_app!` invocation.
///
/// We construct fresh `InfoClient`/`Trader` instances inside each tool rather
/// than caching them on `HyperliquidApp`, because the env var that gates the
/// trader can change between calls and we want each invocation to re-check.
#[derive(Clone, Default)]
pub(crate) struct HyperliquidApp;

// ---------------------------------------------------------------------------
// Read-only client (no signing)
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub(crate) struct InfoClient {
    http: reqwest::blocking::Client,
}

impl InfoClient {
    pub(crate) fn new() -> Result<Self, String> {
        let http = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(15))
            .build()
            .map_err(|e| format!("failed to build HTTP client: {e}"))?;
        Ok(Self { http })
    }

    /// POST a JSON body to `/info` and decode the response.
    ///
    /// Hyperliquid's read API is "one endpoint, many shapes" — the `type` field
    /// in the body discriminates the request. Examples:
    ///   * `{"type":"meta"}`
    ///   * `{"type":"allMids"}`
    ///   * `{"type":"clearinghouseState","user":"0x..."}`
    ///   * `{"type":"openOrders","user":"0x..."}`
    pub(crate) fn post(&self, body: Value) -> Result<Value, String> {
        let url = format!("{API_BASE}/info");
        let response = self
            .http
            .post(&url)
            .json(&body)
            .send()
            .map_err(|e| format!("Hyperliquid /info request failed: {e}"))?;

        let status = response.status();
        let text = response.text().unwrap_or_default();
        if !status.is_success() {
            return Err(format!("Hyperliquid /info HTTP {status}: {text}"));
        }
        serde_json::from_str(&text)
            .map_err(|e| format!("Hyperliquid /info JSON decode failed: {e} (body: {text})"))
    }
}

// ---------------------------------------------------------------------------
// Trader (signed /exchange calls)
// ---------------------------------------------------------------------------

/// Wallet-bearing client. Construct via `Trader::from_env()` — fails fast if
/// the operator hasn't exported `HL_WALLET_KEY`.
pub(crate) struct Trader {
    /// Hex-encoded secp256k1 private key (without the leading `0x`). Kept in
    /// memory only — never logged, never serialized.
    _secret_hex: String,
}

impl Trader {
    /// Read the wallet key from the env var the backend operator wires in.
    ///
    /// We deliberately use `HL_WALLET_KEY` rather than e.g. `PRIVATE_KEY` so
    /// the env var name is unambiguous in the backend's secret store.
    pub(crate) fn from_env() -> Result<Self, String> {
        let raw = std::env::var("HL_WALLET_KEY").map_err(|_| {
            "HL_WALLET_KEY is not configured on this backend — trading is disabled. \
             Ask the platform operator to export a Hyperliquid wallet key before \
             retrying."
                .to_string()
        })?;
        let secret = raw.trim().trim_start_matches("0x").to_string();
        if secret.len() != 64 || hex_check(&secret).is_err() {
            return Err(
                "HL_WALLET_KEY is set but is not a valid 32-byte hex secret key.".to_string(),
            );
        }
        Ok(Self {
            _secret_hex: secret,
        })
    }

    /// Submit a signed action to `/exchange`.
    ///
    /// TODO: implement EIP-712 signing. The shape is:
    ///   1. Build the action JSON, e.g.
    ///      `{"type":"order","orders":[{ ... }],"grouping":"na"}`
    ///   2. msgpack-encode the action, append the u64 nonce (millis since epoch)
    ///      and 20-byte vault address (zero for spot wallets), then keccak256
    ///      that buffer to get the `connectionId`.
    ///   3. EIP-712 sign with domain
    ///        { name: "Exchange", version: "1", chainId: 1337,
    ///          verifyingContract: 0x0000…0000 }
    ///      and primary type `Agent { source: "a", connectionId: bytes32 }`
    ///      for mainnet (source is "b" for testnet).
    ///   4. POST `{ action, nonce, signature: {r, s, v}, vaultAddress }`.
    ///
    /// The reference implementation lives in `hyperliquid-python-sdk`:
    /// <https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/main/hyperliquid/utils/signing.py>
    ///
    /// Until that's wired up, trading tools surface a clear error so the agent
    /// stops and tells the user instead of silently no-op'ing.
    pub(crate) fn submit_action(&self, _action: Value) -> Result<Value, String> {
        Err(
            "Hyperliquid order signing is not yet implemented in this scaffold. \
             See the TODO in `src/client.rs::Trader::submit_action` for the protocol \
             reference. Wire up EIP-712 signing before relying on this bot for \
             real trades."
                .to_string(),
        )
    }
}

fn hex_check(s: &str) -> Result<(), ()> {
    if s.bytes().all(|b| b.is_ascii_hexdigit()) {
        Ok(())
    } else {
        Err(())
    }
}

// ---------------------------------------------------------------------------
// Args (shared by tools.rs)
// ---------------------------------------------------------------------------

use aomi_sdk::schemars::JsonSchema;
use serde::Deserialize;

#[derive(Debug, Deserialize, JsonSchema)]
pub(crate) struct EmptyArgs {}

#[derive(Debug, Deserialize, JsonSchema)]
pub(crate) struct GetMidPriceArgs {
    /// Coin symbol on Hyperliquid, e.g. `BTC`, `ETH`, `SOL`. Case-sensitive.
    pub(crate) coin: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub(crate) struct WalletArgs {
    /// 0x-prefixed Ethereum address whose state you want to read.
    pub(crate) address: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub(crate) struct PlaceMarketOrderArgs {
    /// Coin symbol, e.g. `BTC`.
    pub(crate) coin: String,
    /// `buy` opens long / closes short. `sell` opens short / closes long.
    pub(crate) side: Side,
    /// Order size in the coin's base units (e.g. 0.01 = 0.01 BTC).
    pub(crate) size: f64,
    /// Optional slippage cap as a fraction, e.g. 0.005 = 50bps. Used to derive
    /// an aggressive limit price from the current mid. Defaults to 0.5%.
    #[serde(default)]
    pub(crate) max_slippage: Option<f64>,
    /// If true, the order is only allowed to reduce an existing position.
    #[serde(default)]
    pub(crate) reduce_only: bool,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub(crate) enum Side {
    Buy,
    Sell,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub(crate) struct CancelOrderArgs {
    /// Coin the order was placed on.
    pub(crate) coin: String,
    /// `oid` of the resting order, from `get_open_orders`.
    pub(crate) oid: u64,
}

// ---------------------------------------------------------------------------
// Action builders (used by tools.rs; pure functions, no I/O)
// ---------------------------------------------------------------------------

/// Build the unsigned action JSON for a limit-as-market order. The signing
/// layer in `Trader::submit_action` is what wraps this into a /exchange call.
pub(crate) fn build_market_order_action(args: &PlaceMarketOrderArgs, mid_px: f64) -> Value {
    let slip = args.max_slippage.unwrap_or(0.005);
    let limit_px = match args.side {
        Side::Buy => mid_px * (1.0 + slip),
        Side::Sell => mid_px * (1.0 - slip),
    };
    json!({
        "type": "order",
        "orders": [{
            "a": args.coin,                 // asset (Hyperliquid resolves via meta)
            "b": matches!(args.side, Side::Buy),
            "p": format!("{limit_px:.5}"),
            "s": format!("{:.5}", args.size),
            "r": args.reduce_only,
            "t": { "limit": { "tif": "Ioc" } },
        }],
        "grouping": "na",
    })
}

pub(crate) fn build_cancel_action(args: &CancelOrderArgs) -> Value {
    json!({
        "type": "cancel",
        "cancels": [{ "a": args.coin, "o": args.oid }],
    })
}
