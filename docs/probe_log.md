# Probe log — 2026-10-25

All commands run from the box (Linux aarch64), direct to the internet, no proxy. `curl` for HTTP,
`websocket-client` for the WebSocket, `uv`-managed venv for Python deps.

## 1. Reachability

```
getent hosts ueb.hkjc.com   ->  101.78.206.8  ihfa-0090.trafficmanager.net
/dev/tcp/ueb.hkjc.com/443    -> OPEN
/dev/tcp/ueb.hkjc.com/52443  -> OPEN
```

## 2. WebSocket upgrade

Raw handshake with `Connection: Upgrade`, `Upgrade: websocket`, `Sec-WebSocket-Version: 13`,
`Origin: https://bet.hkjc.com`, with and without `Sec-WebSocket-Protocol: mqtt`, against
`/`, `/mqtt` and `/ws` on ports 443 and 52443.

**Result: `HTTP/1.1 101 Switching Protocols` in all 12 combinations**, `Sec-WebSocket-Accept`
echoed correctly, and `Sec-WebSocket-Protocol: mqtt` echoed when requested.

## 3. MQTT v5 CONNECT

`paho-mqtt` (WebSocket transport, `path="/"`) failed with `WebsocketConnectionError: WebSocket
handshake error`, so a raw MQTT v5 client was written over `websocket-client` instead (full header
control).

CONNECT with `clientId="jcbw2_4e_<6hex>_<epoch_ms>"`, `username="jcbw2"`,
`password=<PUSH_NO_LOGIN_SECRET>`:

```
CONNACK raw: 20 09 00 00 06 25 00 29 00 2a 00
  type = 0x20 (CONNACK)
  reason = 0x00 (Success)
  props: 0x25 Maximum QoS = 0
         0x29 Retain Available = 0
         0x2a Maximum Packet Size = 0
```

## 4. Subscriptions

| topic | SUBACK |
|---|---|
| `hk/d/prdt/wager/rpy/02/recovery/client/<clientId>` | `0x00` granted |
| `hk/d/prdt/wager/evt/02/upd/racing/#` | `0x00` granted |
| `hk/d/prdt/wager/evt/01/upd/racing/#` | `0x00` granted |
| `hk/d/evnt/racing/evt/01/upd/racing/#` | `0x00` granted |
| `hk/d/evnt/racing/evt/02/upd/racing/#` | `0x00` granted |
| `#` (football run, for contrast) | `0x80` not authorised |

## 5. Messages — none (meeting closed)

Two runs, 100 s and 75 s, with recovery requests:

- **Run A** — wildcard topics (`…/evt/0{1,2}/upd/racing/#`, `…/hk/d/evnt/racing/…`),
  `latestMessageInSeconds: 120`. **0 messages.**
- **Run B** — 29 **concrete** topics built for the real card
  (`20261025/st/{01,02,10,11,+}/{win,pla,qin,qpl}/odds/full`,
  `…/20261025/st/{01,02,10,11,+}` event topics, `…/20261025/st`, `…/+/inv`,
  `…/00/jkc/+/odds`, `…/00/jkc/+/detail`), with recovery requests at
  `latestMessageInSeconds` = `120`, `3600`, `43200`, `604800`. **0 messages.**

**Explanation.** `raceMeetings` for 2026-10-25 returned the Sha Tin meeting with
`status: CLOSED`, all 11 races `RESULT`, every `poolInvs[].status` `PAYOUT` — the last race went off
at 18:20 HKT and the probe ran at ~21:0x HKT. The broker's message cache is **live-only**: it
returned nothing even with a 7-day window, so the negative result is a property of the cache, not
of the topics or the auth.

## 6. Race card lookup

`raceMeetings` needed `operationName=raceMeetings`; without it every call returned
`{"errors":[{"message":"Internal server error - BAD_REQUEST"}]}`, including with the exact shipped
query. Hand-written minimal queries were also rejected — the endpoint enforces a whitelist of the
documents the site ships.

Querying future dates (`2026-10-26`, `27`, `28`, `29`, `30`, `31`) returned **0 meetings** — HKJC
had not published the next card yet at probe time. `activeMeetings` returned
`ST:CLOSED S2:CLOSED`.

## 7. What is still open

- **Live racing payload capture.** Needs a live meeting. Expected next: **Wed 2026-10-28,
  Happy Valley (HV)**, first race ~19:15 HKT.
- Racing payload **schema** — assumed to mirror the football envelope
  (`{id, updAt, lines:{line:[{id, typ, cond, main, st, comb:[{id, str, st, esStatus, odds:{cur:{odds, updAt}}}]}]}}`)
  but not yet observed.
- Whether `latestMessageInSeconds` is honoured above 120 for a live meeting.
- Whether the JKC/TNC fixed-odds trees behave like the pari-mutuel trees.
