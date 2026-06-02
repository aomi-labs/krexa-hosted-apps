# Krexa FE deploy-proxy — architecture & FE bot spec

> Status: **proposed** · 2026-06-01 · audience: Krexa FE engineers + Aomi platform ops
>
> This is the partner-facing companion to Aomi's internal ADR 0011. It describes
> how Krexa's "deploy your app" frontend deploys + activates apps on the Aomi
> runtime **without ever putting a credential in the browser**, and specs the
> server-side bot code you need to build.

## TL;DR

- Krexa apps are hosted in this repo (`aomi-labs/krexa-hosted-apps`), which is
  going **private** for the B2B model.
- Your FE's **server side** (a "deploy-proxy") holds all secrets and does the
  privileged work: it commits the user's app to `apps/<slug>/` and calls the
  Aomi backend to activate. The browser only ever talks to your proxy.
- Aomi issues you **one platform-wide activation token** for the `krexa`
  platform. A **single bot GitHub account** pushes every app. Therefore **all
  per-user isolation and attribution live in your proxy** — there is no
  per-user granularity on Aomi's or GitHub's side. Read "Authorization &
  attribution" carefully.

## Why a proxy (not raw git access for users)

- `aomi-git` pushes with the local git credential — there's no "push from a
  browser." A server must hold the credential.
- A GitHub PAT can only push if its account is a repo collaborator; "public"
  never grants write, and once private it doesn't grant read either.
- Git write is **repo-wide, not path-scoped**. If users had direct write they
  could edit *other* apps, `platform.json`, or `.github/workflows/` (which CI
  builds releases from). The proxy turns "only touch `apps/<slug>/`" from a
  client convention into a **server-enforced** rule.

## Architecture

```
Browser (Krexa user)              Your FE server (deploy-proxy)            GitHub / Aomi backend
────────────────────              ─────────────────────────────           ─────────────────────
authenticated session  ──POST──▶  /api/deploy {slug, source}
                                  1. authz: does caller own <slug>?  ──▶   (else 403)
                                  2. commit apps/<slug>/ → publish    ──▶   GitHub (bot PAT)
                                                                            → CI builds release tag
                       ◀─202────  {release_tag, ci_url}
       ...poll...      ──GET───▶  /api/deploy/:slug/status            ──▶   GitHub Actions/releases
                       ◀─200────  {ci, release}
                       ──POST──▶  /api/activate {slug, env}
                                  3. authz: does caller own <slug>?
                                  4. POST /api/admin/apps/activate    ──▶   Aomi backend
                                     (platform token + read PAT)
                       ◀─200────  {activated, status_url}
```

The proxy is the **only** holder of every secret. Each user session maps to the
slug(s) they own; steps 1 and 3 reject anything outside that set.

---

## Authorization & attribution — read this first

A single server identity wields two **shared** credentials, so Aomi's backend
and GitHub have **no per-user granularity**:

- **GitHub:** one bot account authors *every* push to this repo. Git history
  attributes all apps to the bot — not the individual Krexa user.
- **Aomi backend:** one platform-wide `krexa` activation token. Aomi authorizes
  by **platform** — it sees "a valid krexa activation," never which of your
  users is behind it. Every activate looks identical to Aomi.

**Therefore:**

1. **All per-user isolation lives in your proxy's per-`slug` ownership check.**
   Aomi and GitHub give no second line of defense for *krexa-internal*
   isolation. Aomi's only guarantee is the platform boundary: a krexa token
   cannot touch `community` or any other platform. If your proxy's authz is
   bypassed, the caller can deploy/activate **any** krexa app.
2. **Revocation is all-or-nothing.** If the activation token or bot PAT leaks,
   Aomi/you revoke it and **all** Krexa deploys stop. There is no per-user
   revoke (that would require Aomi to issue per-release tokens, which we are not
   doing for the one-click flow).
3. **Attribution is yours to keep.** Since Aomi sees one token and GitHub sees
   one bot, the record of "user X deployed slug Y at time Z" exists **only in
   your proxy's audit log**. You **must** log `user + slug + action +
   release_tag + timestamp` on every deploy/activate, or traceability is lost.

This is the accepted B2B trade: Aomi trusts Krexa to police its own tenant; the
clean boundary is the platform.

---

## Credentials (all server-side; never shipped to the browser)

| Credential | Who issues | Purpose | Scope (least privilege) |
|---|---|---|---|
| **Bot GitHub PAT** | Krexa creates a bot account; Aomi/Krexa add it as a write collaborator here | (a) commit `apps/<slug>/` to `publish`; (b) the transient read token Aomi uses to fetch your private release | **fine-grained** PAT, **Contents: read+write on `aomi-labs/krexa-hosted-apps` only** — not a classic all-repos `repo` PAT |
| **Krexa activation token** | **Aomi** issues one platform-wide token | authorize `POST /api/admin/apps/activate` | authorizes **only** krexa activations; cannot touch other platforms |

Store both in a secret manager (not in the image/`.env` committed to git).
**Never** expose either to the browser bundle — a leaked write PAT or activation
token is a full repo / platform compromise.

## Repo settings (Aomi/Krexa ops do this once)

- Make `krexa-hosted-apps` **private**.
- Add the bot account as a **write collaborator** (or a single-purpose team).
- `publish` branch protection: **block force-push + deletion**, but **allow
  direct pushes** (CI triggers on `push` to `publish`; the bot pushes directly —
  do **not** require PRs/reviews or both deploy and CI break). Optionally
  restrict who-can-push to just the bot.
- No human users are collaborators — they reach the repo only through the proxy.

---

## FE bot spec

### Endpoints (proxy → expose to your authenticated FE)

```ts
// All endpoints require an authenticated Krexa session.
// The proxy resolves session -> ownedSlugs and rejects anything else.

POST /api/deploy
  body:  { slug: string; source: SourceBundle }   // source = the user's app files
  does:  ownershipCheck(session, slug)
         commitAppToPublish(slug, source)          // GitHub API; see deploy contract
  returns 202 { releaseTag: string; ciUrl: string }

GET  /api/deploy/:slug/status
  returns 200 { ci: "pending"|"running"|"success"|"failure";
                release: "absent"|"building"|"ready";
                releaseTag: string }

POST /api/activate
  body:  { slug: string; targetEnv: "staging" | "prod" }
  does:  ownershipCheck(session, slug)
         callAomiActivate(slug, targetEnv)
  returns 200 { activated: true; statusUrl: string }
```

### 1. Per-slug ownership check (the security crux)

```ts
function ownershipCheck(session: Session, slug: string): void {
  const owned = lookupOwnedSlugs(session.userId);   // your own records
  if (!owned.includes(slug)) throw forbidden(`not your app: ${slug}`);
}
```

And before committing, **verify the staged tree only writes `apps/<slug>/`** —
reject any path touching `platform.json`, `.github/`, or another `apps/<other>/`.
`aomi-git` only stages `apps/<slug>/`; your reimplementation must *re-check the
actual file list server-side*, not trust the client.

### 2. Deploy = reproduce the `aomi-git deploy` contract (no git binary)

Use the **GitHub Git Data API** to create one commit on `publish` (blobs → tree
→ commit → update ref). The commit MUST:

1. Write the app source under **`apps/<slug>/`** and nothing else.
2. Write **`apps/<slug>/.aomi/deployment.json`** — the build contract CI reads.
   Minimum shape (mirror what `aomi-git deploy` writes):

   ```jsonc
   {
     "app": {
       "name": "<slug>", "display_name": "<Display Name>",
       "platform": "krexa",
       "git": "https://github.com/aomi-labs/krexa-hosted-apps",
       "public": false,
       "server_tags": ["staging"]          // staging by default — see env story
     },
     "target": {
       "branch": "publish",
       "app_path": "apps/<slug>",
       "release_tag": "apps-<slug>-<short-source-commit>",
       "server_tags": ["staging"]
     }
   }
   ```
3. Let CI derive + publish the release tagged **`apps-<slug>-<short-source-commit>`**.
   Surface that tag back to the FE for the status/activate phases.

> Pin this reimplementation to Aomi's `aomi-git` contract (ADR 0004). Recommended
> guard: a test that deploys a fixture app and diffs your produced `apps/<slug>/`
> tree + `deployment.json` against `aomi-git deploy`'s output, so you catch drift.

### 3. One-click flow = deploy → wait for CI → activate (NOT one call)

"One click = live" is a short **async pipeline**, because CI takes minutes and
the release tag does not exist when the push returns:

```
click → POST /api/deploy → [CI builds, ~min] → poll status → POST /api/activate → live
```

- Model it as a **progress UI** (deploy → building → activating → live), not a
  blocking request.
- Bridge the CI gap by **polling** `/status` (which proxies GitHub
  Actions/releases). A CI `release:published` webhook → auto-activate is a
  cleaner v2.
- **CRITICAL — do not auto-activate at push.** Do not replicate `aomi-git`'s
  "activation token in env → activate during deploy" shortcut: at push time the
  release doesn't exist yet, so that path **502s on a CI race** (see
  `CONTRIBUTING.md`). Always deploy first, activate after the release is ready.

### 4. Activate call (proxy → Aomi backend)

```ts
async function callAomiActivate(slug: string, targetEnv: "staging"|"prod") {
  await fetch(`${AOMI_BACKEND_URL}/api/admin/apps/activate`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${KREXA_ACTIVATION_TOKEN}`,  // platform-wide, server-side
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      app_slug:        slug,                       // alias of `name`
      platform:        "krexa",
      source_repo:     "aomi-labs/krexa-hosted-apps",
      app_release_tag: releaseTagFor(slug),        // apps-<slug>-<commit>
      source_commit:   commitFor(slug),            // provenance (from deployment.json)
      is_public:       false,
      target_tags:     [targetEnv],                // narrow-only; must be ⊆ build's server_tags
      github_token:    BOT_READ_PAT,               // transient one-shot read for the private-repo fetch
    }),
  });
}
```

Field names follow the backend's `ActivateAppRequest` (accepts `app_slug` /
`slug` / `name`). `github_token` is the **transient** read PAT — Aomi uses it
once to fetch the release tarball and never persists it.

### 5. Env story (staging vs prod)

- Default the **Deploy** button to **staging** (`server_tags: ["staging"]`).
- "Go to prod" is a **separate** action: re-deploy with `prod` in `server_tags`,
  then activate `prod`. Aomi enforces **narrow-only** — `target_tags` must be a
  subset of the build's declared `server_tags`, so the proxy **cannot** promote
  an existing staging build to prod without a re-deploy. Surface this as a
  distinct **"Promote to prod"** button, not the same click.

### 6. Audit logging (required — see attribution)

On every `/api/deploy` and `/api/activate`, log:

```
{ userId, slug, action: "deploy"|"activate", releaseTag, targetEnv, ts }
```

This is the **only** place per-user attribution exists. Treat it as a
compliance record, not debug output.

---

## Security checklist

- [ ] Bot PAT is **fine-grained**, Contents read+write, **this repo only**.
- [ ] Activation token + PAT live in a secret manager, **server-side only**;
      never in the browser bundle or client env.
- [ ] Ownership check on **every** deploy/activate; staged-path check rejects
      anything outside `apps/<slug>/`.
- [ ] `publish` protected (no force-push/delete); only the bot pushes.
- [ ] Audit log on every privileged action.
- [ ] No auto-activate at push (CI-race 502).

## Known blocker

Aomi's `POST /api/admin/apps/activate` currently returns a fast **502** *after*
auth succeeds, in the release fetch/install step (observed 2026-06-01 on
`staging-api`). The **deploy** half is unaffected — build that first. The
**activate** half won't work end-to-end until Aomi fixes that 502; coordinate
before promising one-click activation.

## References

- `CONTRIBUTING.md` (this repo) — the builder-facing deploy/activate flow.
- Aomi ADR 0004 (`aomi-git` contract), ADR 0009 (DB-driven platforms +
  deployment.json), ADR 0010 (rollout/smoke runbook), ADR 0011 (internal
  deploy-proxy decision) — in `aomi-launch-my-agent/ralph/adr/`.
