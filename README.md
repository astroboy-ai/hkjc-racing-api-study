# hkjc-racing-api-study

HKJC **racing** — endpoints and the live odds push. Probed 2026-10-25 HKT from a plain HTTP client
(no account, no key, no login).

Sibling repo: [`hkjc-api-study`](https://github.com/astroboy-ai/hkjc-api-study) (football).

## Headline

**The racing odds push is readable without a login.** HKJC pushes every racing pool over
**Solace MQTT v5 on WebSocket** at `wss://ueb.hkjc.com:52443/`, and the broker serves it to an
unauthenticated client that connects with `username: "jcbw2"` and the public
`PUSH_NO_LOGIN_SECRET` from `/Config/GlobalConfig.js`. Racing is the *intended* no-login path
(`RC_ODDS_PUSH_NO_LOGIN = true`); football happens to work too.

Verified 2026-10-25: connection accepted (`CONNACK` reason `0x00`), every racing subscription
granted (`SUBACK 0x00`). **No live messages could be captured that night because the Sha Tin
meeting had already closed** (`raceMeetings` → `status: CLOSED`, all 11 races `RESULT`/`PAYOUT`)
and the broker keeps no cache for a closed meeting (tested `latestMessageInSeconds` up to
7 days — 0 messages). Live capture requires a live meeting; the next one is expected
**Wed 2026-10-28, Happy Valley (HV)**.

## Contents

| file | what |
|---|---|
| `docs/odds_push.md` | the MQTT push contract — broker, auth, topics, recovery request, payloads |
| `docs/topic_map.md` | the complete racing topic map extracted from `RacingConfig.js`, plus the topic-builder rules |
| `docs/endpoint_catalog.md` | the racing GraphQL operations and the REST/OES surface |
| `docs/probe_log.md` | exactly what was run and what came back, including the negative results |
| `queries/raceMeetings.graphql` | the **exact** query the site sends (fragments included) |
| `scripts/racing_push_client.py` | working push client (MQTT v5 over WebSocket, gzip, recovery) |
| `scripts/race_meetings.py` | fetch the race card / meeting list via GraphQL |
| `samples/` | `RacingConfig.js`, the captured query, and the closed-meeting probe result |

## Quick start

```bash
pip install websocket-client

# today's meeting and race list
python scripts/race_meetings.py --date 2026-10-28 --venue HV

# live odds push (run during a meeting)
python scripts/racing_push_client.py --date 20261028 --venue hv --seconds 120 --out push.json
```

## What is verified vs. not

| | status |
|---|---|
| broker reachable, WS upgrade, MQTT v5 CONNECT accepted | ✅ verified |
| racing subscriptions granted (`SUBACK 0x00`) | ✅ verified |
| full topic map + builder rules | ✅ extracted from the shipped config |
| recovery-request protocol | ✅ verified on football, same code path |
| **live racing message payloads** | ⚠️ **not yet captured** — needs a live meeting |

## Caveats

1. `PUSH_NO_LOGIN_SECRET` is a **public constant** in `/Config/GlobalConfig.js`, not an account
   credential. Read it from the config at runtime; never hard-code it.
2. The broker is undocumented. Treat the push as best-effort and keep a REST/GraphQL fallback.
3. The message cache is **live-only** — a closed meeting yields nothing at any
   `latestMessageInSeconds`.
4. Racing and football share the broker and the same credentials; the topic trees differ
   (`.../upd/racing/...` vs `.../upd/fb/fo/...`).
