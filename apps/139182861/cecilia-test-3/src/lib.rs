use aomi_sdk::schemars::JsonSchema;
use aomi_sdk::*;
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Clone, Default)]
struct CeciliaTest3App;

#[derive(Debug, Deserialize, JsonSchema)]
struct SmokeArgs {
    #[serde(default)]
    message: Option<String>,
}

struct SmokeEcho;

impl DynAomiTool for SmokeEcho {
    type App = CeciliaTest3App;
    type Args = SmokeArgs;

    const NAME: &'static str = "smoke_echo";
    const DESCRIPTION: &'static str =
        "Return a deterministic response for hosted double-app deployment smoke tests.";

    fn run(_app: &Self::App, args: Self::Args, _ctx: DynToolCallCtx) -> Result<Value, String> {
        Ok(json!({
            "app": "cecilia-test-3",
            "message": args.message.unwrap_or_else(|| "ok".to_string()),
        }))
    }
}

const PREAMBLE: &str = r#"## Role
You are a minimal smoke-test app for validating multi-app hosted deployments.
"#;

dyn_aomi_app!(
    app = CeciliaTest3App,
    name = "cecilia-test-3",
    version = "0.1.0",
    preamble = PREAMBLE,
    tools = [SmokeEcho],
    namespaces = []
);
