//! Hand-written companion to the generated `client.rs`.
//!
//! Krexa runs two API tiers:
//!   - Anonymous: 30 req/min, no key needed. The public reads (score,
//!     credit eligibility, vault stats, KYA lookup, …) work in this tier.
//!   - Authenticated: 60+ req/min and access to the Pay.sh authenticated
//!     surface (`call`, `discover`, `history`, `budget`, `confirm`,
//!     `tier`). Carry `X-API-Key: kx_...` on every authed request.
//!
//! Unlike the HMAC-signed venues (Binance, Bybit, OKX, Limitless) Krexa
//! does **not** compute a per-request signature — the key is a static
//! bearer. This module therefore only resolves the key from the
//! environment; there is no `sign(...)` or `current_timestamp_ms()`.
//!
//! Provisioning the key itself requires an Ed25519 signature over a
//! literal challenge message — that would belong in this file under a
//! `sign_provision_message(...)` helper, but Krex does not provision keys
//! at runtime so it is deferred. See `apps/krexa/openapi.meta.json`.

/// Env var that holds the `kx_`-prefixed key. Provisioned via
/// `POST /access/provision-key` (offline, by the operator) or returned
/// from `POST /solana/paysh/onboard`.
pub const API_KEY_ENV: &str = "KREXA_API_KEY";

/// Resolve the API key from (in order) the per-app secret vault and the
/// `KREXA_API_KEY` env var. Returning `Err` only when both miss, with the
/// tool-shaped message the curated tool layer propagates with `?`.
pub fn api_key(ctx: &aomi_sdk::DynToolCallCtx) -> Result<String, String> {
    aomi_sdk::resolve_secret_value(
        ctx,
        None,
        API_KEY_ENV,
        &format!(
            "[krexa] {API_KEY_ENV} not set; Pay.sh authenticated endpoints \
             require an X-API-Key header (`kx_...`)."
        ),
    )
}

// ---------------------------------------------------------------------------
// Owner Ed25519 signing — `POST /solana/credit/{agent}/request`
// ---------------------------------------------------------------------------
//
// The credit-request endpoint requires `ownerSignature` — a base58 Ed25519
// signature over the literal challenge `Krexa credit request for <ownerPubkey>`.
//
// The challenge format is a **best guess** inferred from the analogous
// `/access/provision-key` shape (`Krexa API key provision for <wallet>`).
// We will know it's correct when Krexa returns 200; until then a wrong
// guess returns `403 Invalid owner signature`. Confirm with the Krexa
// team and update `CREDIT_REQUEST_CHALLENGE_PREFIX` if it differs.

/// Env var holding the owner wallet's secret key, base58-encoded as the
/// full 64-byte Solana keypair (the standard format `solana-keygen` and
/// Phantom both emit). Decodes to `[u8; 64]`.
pub const OWNER_SECRET_ENV: &str = "KREXA_OWNER_SECRET_KEY";

/// The challenge string template. The {0} placeholder is substituted with
/// the base58 owner pubkey. Sign over the UTF-8 bytes of the result.
const CREDIT_REQUEST_CHALLENGE_PREFIX: &str = "Krexa credit request for ";

/// Format the credit-request challenge for `owner_pubkey`. Exposed so the
/// tool layer can include it in error messages when the env var is
/// missing — operators can then sign it externally and inject the
/// signature.
pub fn credit_request_challenge(owner_pubkey: &str) -> String {
    format!("{CREDIT_REQUEST_CHALLENGE_PREFIX}{owner_pubkey}")
}

/// Sign the credit-request challenge for `owner_pubkey` using the secret
/// key from `KREXA_OWNER_SECRET_KEY`. Returns a base58-encoded 64-byte
/// Ed25519 signature, ready to drop into `ownerSignature` on the wire.
///
/// Errors:
///   - `KREXA_OWNER_SECRET_KEY` unset
///   - secret key not valid base58 or wrong length (expects 64 bytes —
///     the Solana keypair format, secret + public concatenated)
pub fn sign_credit_request(
    ctx: &aomi_sdk::DynToolCallCtx,
    owner_pubkey: &str,
) -> Result<String, String> {
    use ed25519_dalek::{Signer, SigningKey};

    let secret_b58 = aomi_sdk::resolve_secret_value(
        ctx,
        None,
        OWNER_SECRET_ENV,
        &format!(
            "[krexa] {OWNER_SECRET_ENV} not set; credit_request needs the \
             owner wallet's secret key (base58-encoded 64-byte Solana \
             keypair). To sign externally, the challenge is:\n  {}",
            credit_request_challenge(owner_pubkey)
        ),
    )?;

    let bytes = bs58::decode(&secret_b58)
        .into_vec()
        .map_err(|e| format!("[krexa] {OWNER_SECRET_ENV} is not valid base58: {e}"))?;

    if bytes.len() != 64 {
        return Err(format!(
            "[krexa] {OWNER_SECRET_ENV} decoded to {} bytes; expected 64 \
             (Solana keypair = 32 secret + 32 public)",
            bytes.len()
        ));
    }

    // The first 32 bytes are the secret seed; ed25519-dalek derives the
    // public key from that. The trailing 32 bytes (public key) are
    // redundant for signing.
    let seed: [u8; 32] = bytes[..32]
        .try_into()
        .expect("len check above guarantees 64 bytes");
    let signing_key = SigningKey::from_bytes(&seed);

    let challenge = credit_request_challenge(owner_pubkey);
    let signature = signing_key.sign(challenge.as_bytes());
    Ok(bs58::encode(signature.to_bytes()).into_string())
}
