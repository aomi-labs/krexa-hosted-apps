use aomi_sdk::{DynAomiTool, DynToolCallCtx, dyn_aomi_app};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::Value;

#[derive(Clone, Default)]
struct HelloWorldApp;

#[derive(Debug, Deserialize, JsonSchema)]
struct EchoArgs {
    message: String,
}

struct EchoTool;

impl DynAomiTool for EchoTool {
    type App = HelloWorldApp;
    type Args = EchoArgs;

    const NAME: &'static str = "hello_world_echo";
    const DESCRIPTION: &'static str = "Echo a message back — minimal Aomi app example.";

    fn run(
        _app: &HelloWorldApp,
        args: Self::Args,
        _ctx: DynToolCallCtx,
    ) -> Result<Value, String> {
        Ok(serde_json::json!({ "message": args.message }))
    }
}

dyn_aomi_app!(
    app = HelloWorldApp,
    name = "hello-world",
    version = "0.1.0",
    preamble = "You are the minimal Hello World Aomi app — echo whatever the user asks.",
    tools = [EchoTool],
    namespaces = ["common"]
);
