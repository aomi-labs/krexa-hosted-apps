use aomi_sdk::{DynAomiTool, DynToolCallCtx, dyn_aomi_app};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::Value;

#[derive(Clone, Default)]
struct HelloCiApp;

#[derive(Debug, Deserialize, JsonSchema)]
struct EchoArgs {
    message: String,
}

struct EchoTool;

impl DynAomiTool for EchoTool {
    type App = HelloCiApp;
    type Args = EchoArgs;

    const NAME: &'static str = "hello_ci_echo";
    const DESCRIPTION: &'static str = "Echo a message for CI bundle validation.";

    fn run(
        _app: &HelloCiApp,
        args: Self::Args,
        _ctx: DynToolCallCtx,
    ) -> Result<Value, String> {
        Ok(serde_json::json!({ "message": args.message }))
    }
}

dyn_aomi_app!(
    app = HelloCiApp,
    name = "hello-ci",
    version = "0.1.0",
    preamble = "You are the CI validation fixture app.",
    tools = [EchoTool],
    namespaces = ["common"]
);
