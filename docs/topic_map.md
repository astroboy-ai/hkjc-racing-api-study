# Racing topic map (`RacingConfig.pushTopics`) and the topic-builder rules

Extracted verbatim from `https://bet.hkjc.com/Config/RacingConfig.js`, 2026-10-25.
`{dt}` = meeting date, `{ve}` = venue code, `{no}` = race number.

## Topic-builder rules (from the site bundle)

```js
aj(content, name, allPools, raceNo) {
  topic = content.config.pushTopics[name];

  if (globalConfig.ODDS_PUSH_V2)      topic = topic.replace("evt/01/", "evt/02/");   // ⚠️ ON
  if (globalConfig.EXPRESS_ODDS_PUSH) topic = pushTopics[name+"_EXPRESS"]  || topic; // ⚠️ ON
  if (globalConfig.EXPRESS_ODDS_PUSH2)topic = pushTopics[name+"_EXPRESS2"] || topic; // ⚠️ ON

  raceNo = (raceNo || content.raceNo) >= 10 ? raceNo : "0" + raceNo;   // 2-digit, zero-padded
  topic  = topic.replace("{dt}", meeting.date.replace(/-/g, ""));      // "2026-10-28" -> "20261028"
  topic  = topic.replace("{ve}", meeting.venueCode.toLowerCase());     // "HV" -> "hv"
  topic  = topic.replace("{no}", allPools ? "+" : raceNo);
}
```

**Consequences:**

- `ODDS_PUSH_V2 = true`, so **every `evt/01/` becomes `evt/02/`** — including the
  `hk/d/evnt/racing/evt/01/...` event tree. Subscribe to `evt/02`, not `evt/01`.
- `EXPRESS_ODDS_PUSH` and `EXPRESS_ODDS_PUSH2` are both `true`, so `WIN`/`PLA`/`QIN`/`QPL`/`DBL`
  resolve to their `_EXPRESS`/`_EXPRESS2` variants.
- `{dt}` is **`YYYYMMDD`** with dashes removed.
- `{ve}` is the **lowercase** venue code.
- `{no}` is the **2-digit zero-padded** race number (`01` … `11`), or the literal `+` for
  "all races".

## Odds topics — `hk/d/prdt/wager/evt/01/upd/racing/{dt}/{ve}/{no}/…`

| key | topic suffix after `{no}/` |
|---|---|
| WIN | `win/odds/full` |
| WIN_EXPRESS | `win/+/expr/odds/full` |
| PLA | `pla/odds/full` |
| PLA_EXPRESS | `pla/+/expr/odds/full` |
| PWIN0 | `win/snap/1stboost/odds/full` |
| PWIN1 | `win/snap/slide2m/odds/full` |
| QIN | `qin/odds/full` |
| QIN_EXPRESS2 | `qin/+/expr/odds/full` |
| QPL | `qpl/odds/full` |
| QPL_EXPRESS2 | `qpl/+/expr/odds/full` |
| DBL | `dbl/odds/full` |
| DBL_EXPRESS2 | `dbl/+/expr/odds/full` |
| FCT | `fct/odds/full` |
| IWN | `iwn/odds/full` |
| CWA / CWB / CWC | `cwa|cwb|cwc/odds/full` |
| TCE_TOP / TCE_BANK | `tce/odds/top_n` \| `tce/odds/banker` |
| TRI | `tri/odds/full` |
| TRI_TOP / TRI_BANK | `tri/odds/top_n` \| `tri/odds/banker` |
| QTT_TOP / QTT_BANK | `qtt/odds/top_n` \| `qtt/odds/banker` |
| FF | `f_f/odds/full` |
| FF_TOP / FF_BANK | `f_f/odds/top_n` \| `f_f/odds/banker` |
| (investment) | `…/+/inv`, `…/fct/inv`, `…/iwn/inv`, `…/tce/inv`, `…/tri/inv`, `…/f_f/inv`, `…/qtt/inv`, `…/dbl/inv`, `…/tbl/inv`, `…/d_t/inv`, `…/t_t/inv`, `…/6up/inv` |

Fixed-odds pools (Jockey Challenge / Trainer Challenge) use `{no}` = `00`:

| key | topic |
|---|---|
| JKC_ODD | `…/{dt}/{ve}/00/jkc/+/odds` |
| JKC_DET | `…/{dt}/{ve}/00/jkc/+/detail` |
| JKC_STA | `hk/d/evnt/racing/evt/01/upd/racing/{dt}/{ve}/00/jkc/+` |
| JKC_SEL | `hk/d/evnt/racing/evt/01/upd/racing/{dt}/{ve}/00/jkc/+/sell` |
| TNC_ODD / TNC_DET / TNC_STA / TNC_SEL | same with `tnc` |

## Event / status topics — `hk/d/evnt/racing/evt/01/upd/racing/…`

| key | topic |
|---|---|
| WIN_SEL / PLA_SEL / QIN_SEL / QPL_SEL | `{dt}/{ve}/{no}/{win\|pla\|qin\|qpl}` |
| IWN_SEL / FCT_SEL / TCE_SEL / TRI_SEL | `{dt}/{ve}/{no}/{iwn\|fct\|tce\|tri}` |
| QTT_SEL / FF_SEL / DBL_SEL / TBL_SEL | `{dt}/{ve}/{no}/{qtt\|f_f\|dbl\|tbl}` |
| CWA_SEL / CWB_SEL / CWC_SEL | `{dt}/{ve}/{no}/{cwa\|cwb\|cwc}` |
| DT_SEL / TT_SEL / 6UP_SEL | `{dt}/{ve}/{no}/{dt\|tt\|6up}` |
| **ALL_SEL** | `{dt}/{ve}/{no}/+` — every pool of one race |
| **ALL_RAC** | `{dt}/{ve}/{no}` — the whole race |
| **ALL_MEE** | `{dt}/{ve}` — the whole meeting |

`ALL_MEE` is the single most useful subscription for a data pipeline: one topic, the whole card.

## Racing feature flags (`GlobalConfig.js`)

```
RC_ODDS_PUSH              true
RC_ODDS_PUSH_NO_LOGIN     true          <- racing is the intended no-login path
FB_ODDS_PUSH              true
FB_ODDS_PUSH_NO_LOGIN     false         <- yet football works on the broker anyway
ODDS_PUSH_V2              true          <- evt/01 -> evt/02
EXPRESS_ODDS_PUSH         true
EXPRESS_ODDS_PUSH2        true
EXPRESS_OB_IDA_PUSH       true
MQTT_INACTIVE_DISCONNECT_TIME  30000
```

## Racing config values (`RacingConfig.js`)

```
autoRefreshInterval   30            (seconds)
validVenue            HV ST CH S1 S2 S3 S4 S5 S6 S7 S8 S9
racingPools           ALUP;WIN;PLA;W-P;QIN;QPL;QQP;FCT;TRI;D-T;T-T;DBL;TBL;TCE;6UP;F-F;JKC;TNC;QTT;CWA;CWB;CWC;IWN
singleRacePool        WIN;PLA;QIN;QPL;IWN;CWA;CWB;CWC;FCT;TCE;TRI;FF;QTT
multiRacePool         DBL;TBL;DT;TT;SixUP
fixedOddsPool         JKC;TNC
```

Venue codes: `HV` Happy Valley, `ST` Sha Tin, `CH` (Conghua), `S1`–`S9` simulcast / overseas.
