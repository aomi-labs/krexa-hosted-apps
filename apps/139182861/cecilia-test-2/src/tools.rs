//! Tool definitions. Each tool is a zero-sized type that impls `DynAomiTool`.
//!
//! Read tools call `InfoClient::post` directly with the right `type` discriminator.
//! Trade tools build an action via `client::build_*_action`, then hand it to
//! `Trader::submit_action` — which today returns a clear "not wired" error.

use crate::client::*;
use aomi_sdk::*;
use serde_json::{Value, json};

// ---------------------------------------------------------------------------
// Read tools
// ---------------------------------------------------------------------------

pub(crate) struct GetMeta;

impl DynAomiTool for GetMeta {
    type App = HyperliquidApp;
    type Args = EmptyArgs;
    const NAME: &'static str = "get_meta";
    const DESCRIPTION: &'static str =
        "List every perpetual market on Hyperliquid with its size/price decimals and max leverage.";

    fn run(_app: &Self::App, _args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        InfoClient::new()?.post(json!({ "type": "meta" }))
    }
}

pub(crate) struct GetMidPrice;

impl DynAomiTool for GetMidPrice {
    type App = HyperliquidApp;
    type Args = GetMidPriceArgs;
    const NAME: &'static str = "get_mid_price";
    const DESCRIPTION: &'static str =
        "Return the current mid-price (USDC) for a Hyperliquid perpetual, given its coin symbol.";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        let all = InfoClient::new()?.post(json!({ "type": "allMids" }))?;
        let px = all
            .get(&args.coin)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("no mid-price for coin `{}` — check `get_meta`", args.coin))?;
        Ok(json!({ "coin": args.coin, "mid_price_usdc": px }))
    }
}

pub(crate) struct GetUserState;

impl DynAomiTool for GetUserState {
    type App = HyperliquidApp;
    type Args = WalletArgs;
    const NAME: &'static str = "get_user_state";
    const DESCRIPTION: &'static str =
        "Read a wallet's Hyperliquid clearinghouse state: open positions, margin, withdrawable balance.";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        InfoClient::new()?.post(json!({
            "type": "clearinghouseState",
            "user": args.address,
        }))
    }
}

pub(crate) struct GetOpenOrders;

impl DynAomiTool for GetOpenOrders {
    type App = HyperliquidApp;
    type Args = WalletArgs;
    const NAME: &'static str = "get_open_orders";
    const DESCRIPTION: &'static str =
        "List a wallet's currently resting orders on Hyperliquid (with their oids, ready for cancel).";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        InfoClient::new()?.post(json!({
            "type": "openOrders",
            "user": args.address,
        }))
    }
}

// ---------------------------------------------------------------------------
// Trade tools — gated on HL_WALLET_KEY and the TODO in Trader::submit_action
// ---------------------------------------------------------------------------

pub(crate) struct PlaceMarketOrder;

impl DynAomiTool for PlaceMarketOrder {
    type App = HyperliquidApp;
    type Args = PlaceMarketOrderArgs;
    const NAME: &'static str = "place_market_order";
    const DESCRIPTION: &'static str =
        "Place a market-style (IoC limit) order on Hyperliquid. Requires backend HL_WALLET_KEY.";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        // Load wallet first so the agent gets a useful error before we waste an
        // /info round-trip.
        let trader = Trader::from_env()?;

        // Need a fresh mid-price to derive the IoC limit price.
        let info = InfoClient::new()?;
        let all = info.post(json!({ "type": "allMids" }))?;
        let mid_str = all
            .get(&args.coin)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("no mid-price for coin `{}`", args.coin))?;
        let mid: f64 = mid_str
            .parse()
            .map_err(|e| format!("could not parse mid `{mid_str}`: {e}"))?;

        let action = build_market_order_action(&args, mid);
        trader.submit_action(action)
    }
}

pub(crate) struct CancelOrder;

impl DynAomiTool for CancelOrder {
    type App = HyperliquidApp;
    type Args = CancelOrderArgs;
    const NAME: &'static str = "cancel_order";
    const DESCRIPTION: &'static str =
        "Cancel a resting Hyperliquid order by its oid. Requires backend HL_WALLET_KEY.";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        let trader = Trader::from_env()?;
        let action = build_cancel_action(&args);
        trader.submit_action(action)
    }
}
