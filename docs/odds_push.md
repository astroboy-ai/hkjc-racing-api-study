# Racing odds push — Solace MQTT over WebSocket (probed 2026-10-25)

## 1. Broker

| | value | source |
|---|---|---|
| login broker | `wss://ueb.hkjc.com/` | `GlobalConfig.PUSH_URL` |
| **no-login broker** | **`wss://ueb.hkjc.com:52443/`** | `GlobalConfig.PUSH_URL_NOLOGIN` |
| DNS | `ueb.hkjc.com` → `101.78.206.8` (`ihfa-0090.trafficmanager.net`) | — |
| ports | 443 and 52443 both **open** | — |

Racing is the *intended* no-login path: `GlobalConfig` has `RC_ODDS_PUSH_NO_LOGIN: true`
(and `FB_ODDS_PUSH_NO_LOGIN: false`). Football works on the same broker anyway.

Public config files (note `.js`, not `.json`):

- `/Config/GlobalConfig.js` — broker URLs, `PUSH_NO_LOGIN_SECRET`, feature flags
- `/Config/RacingConfig.js` — `pushTopics`, `autoRefreshInterval: 30`, `validVenue`, pool lists
- `/Config/RacingPageConfig.js`
- `/Config/DeviceConfig.js`

## 2. Transport

WebSocket upgrade returns `101 Switching Protocols` on `/`, `/mqtt` and `/ws` on both ports;
subprotocol `mqtt` is echoed back. **MQTT v5** (`protocolVersion: 5`).

## 3. Connect (no-login)

```
MQTT CONNECT (v5)
  clientId   : "jcbw2_4e_" + 6 random hex + "_" + epoch_ms     (any unique value)
  username   : "jcbw2"
  password   : GlobalConfig.PUSH_NO_LOGIN_SECRET               (public constant)
  keepalive  : 60
  cleanStart : true
```

CONNACK `20 09 00 00 06 25 00 29 00 2a 00` → **reason `0x00` (Success)**,
with `Maximum QoS = 0`, `Retain Available = 0`, `Maximum Packet Size = 0`.

The login path instead uses `username: "jcbw2_4e_user"` and a bearer-style password
(`iA()` → `"OAUTH~OP_CIAM_ARKLE_HIGHPRIV~<access_token>"` when `useArkleAccessTokenInSolace`,
else `"OPENID~CIAM_NORMAL~<acct>~<acct>"`) from
`POST {CIAM_URL}/auth/access_token` with
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&scope=solace_messaging`.
**Not needed** for racing odds.

## 4. Recovery request — REQUIRED

Subscribing alone yields **nothing**. The client must publish a recovery request, exactly as the
site's `pubCacheTopic` does:

```
subscribe : hk/d/prdt/wager/rpy/02/recovery/client/<clientId>        (no-login)
publish   : hk/d/prdt/wager/req/02/recovery/client
payload   : {"systemCode":"JCBW2_4E",
             "senderId":"<clientId>",
             "topics":["<concrete topic>", ...],
             "latestMessageInSeconds":120}
properties: userProperties { "Trace-Id": "<prefix>_<clientId|account>_<epoch_ms>" }
qos 0, retain false
```

The server replies on the recovery topic with the cached messages for those topics.

⚠️ **Two things matter here:**

1. The request needs **concrete topics** (with real `{dt}/{ve}/{no}`), not wildcards. A wildcard
   request returns nothing.
2. The cache is **live-only**. For a **closed** meeting it returns nothing at any window —
   `latestMessageInSeconds` was tested at `120`, `3600`, `43200` and `604800` against the closed
   Sha Tin card and returned **0 messages every time**.

## 5. Payloads

Every payload is **gzip-compressed** (`1f 8b 08 ...`). Football payloads are gzip JSON; racing
payloads are expected to follow the same pattern (not yet captured live — see `probe_log.md`).

Football's decoded shape, for reference (same broker, same envelope conventions):

```json
{"id":"2025232005","updAt":"2026-10-25T20:24:59.182+08:00",
 "lines":{"line":[{"id":"1","typ":"LineCondition","cond":"10.5","main":false,"st":"Available",
   "comb":[{"id":"1","str":"H","st":"Available","esStatus":"Offer",
            "odds":{"cur":{"odds":"2.38","updAt":"2026-10-25T20:31:52.953+08:00"}}}]}]}}
```

Timestamps carry an explicit `+08:00` offset.

## 6. Verification status

| step | result |
|---|---|
| TCP reachable on 443 / 52443 | ✅ |
| WS upgrade on `/`, `/mqtt`, `/ws` | ✅ `101` |
| MQTT v5 CONNECT with `jcbw2` + secret | ✅ `CONNACK 0x00` |
| subscribe `hk/d/prdt/wager/evt/0{1,2}/upd/racing/#` | ✅ `SUBACK 0x00` |
| subscribe `hk/d/evnt/racing/evt/0{1,2}/upd/racing/#` | ✅ `SUBACK 0x00` |
| recovery with wildcard topics | ⚠️ 0 messages |
| recovery with concrete topics, closed meeting, windows 120 s … 7 d | ⚠️ 0 messages (expected) |
| **live meeting capture** | ⏳ pending — next meeting expected Wed 2026-10-28 HV |

## 7. Caveats

1. `PUSH_NO_LOGIN_SECRET` is public (shipped in the site JS) but read it at runtime.
2. Undocumented broker — best-effort; keep a GraphQL/REST fallback.
3. Message ordering is per-topic; use the payload's own timestamp, not arrival time.
4. `Retain Available = 0` — no retained messages, so a late subscriber sees only what the recovery
   request returns.
