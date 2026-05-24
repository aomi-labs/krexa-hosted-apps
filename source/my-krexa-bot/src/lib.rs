use aomi_sdk::{DynAomiTool, DynToolCallCtx, dyn_aomi_app};
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
