# Racing endpoint catalogue

Probed 2026-10-25 HKT. The racing site shares the same SPA bundle as football
(`/static/js/main.<hash>.js`), so the GraphQL client, the MQTT client and the config loader are
identical — only the operations and the topic tree differ.

## Hosts

| host | what |
|---|---|
| `bet.hkjc.com` | SPA shell, `/Config/*.js`, static bundles, i18n |
| `info.cld.hkjc.com` | GraphQL — `/graphql/base-get/` (GET with `query`+`variables`+`operationName`) |
| `infoapi.hkjc.com` | OES racing odds — `OES_ENDPOINT: /pmu/odps/racing/v1/opGetSingleQTTOdds/JCBW` |
| `racing.hkjc.com` | `JCRW_URL` (racing content site) |
| `ueb.hkjc.com` | **Solace MQTT odds push** (see `odds_push.md`) |
| `consvc.hkjc.com` | Sitecore CMS GraphQL `/JCBW/api/graph` (display only) |

## Config files (public)

| path | contents |
|---|---|
| `/Config/GlobalConfig.js` | broker URLs, secrets-as-constants, feature flags, `GRAPHQL_URL`, `INFOAPI_URL`, `JCRW_URL`, `OES_ENDPOINT` |
| `/Config/RacingConfig.js` | `pushTopics`, `autoRefreshInterval`, `validVenue`, pool lists |
| `/Config/RacingPageConfig.js` | racing page layout |
| `/Config/DeviceConfig.js` | device flags |
| `/Config/BetSlipConfig.js` | football `pushTopics` + `cacheTopics` (shared bet slip) |
| `/Config/upgrade.json` | version — changes on redeploy; re-extract the queries when it does |

## GraphQL operations (racing)

All on `info.cld.hkjc.com/graphql/base-get/`, sent as **GET** with
`?query=<doc>&variables=<json>&operationName=<name>`.

⚠️ **`operationName` is required.** Without it the server answers
`{"errors":[{"message":"Internal server error - BAD_REQUEST"}]}`. The server also rejects
hand-written minimal queries — only the exact shipped documents are accepted (same whitelist
behaviour as the football endpoint).

| operation | what it returns |
|---|---|
| **`raceMeetings`** | the race card: `activeMeetings` (id, venueCode, date, status, races[{no, postTime, status, wageringFieldSize}], `poolInvs`) and `raceMeetings(date, venueCode)` with the full meeting — races, runners (horse, jockey, trainer, barrier, weight, rating, last6run, winOdds), `poolInvs` (id, leg, status, sellStatus, oddsType, investment, lastUpdateTime), `obSt`, `jpEsts`, penetrometer/hammer readings, `changeHistories`, `jkcInstNo` |
| `racingBlock` | the racing block for a meeting (uses `racingBlockFragment`) |
| `racing` | racing menu/content |
| `racingChanges` | race changes (scratchings, rider changes) |
| `racingFoRaceByRace` | fixed-odds race-by-race |
| `racingFOUserContent` | fixed-odds user content |
| `resultMeetings` | results by meeting |
| `rbcList` / `rbcMeeting` | race-broadcast content |
| `sp4e_racing_pmPool` | pari-mutuel pool config/status |
| `jockeyTrainerRanking` | jockey / trainer championship standings |
| `commonControl` | feature flags (`earlySettlementEnabled`, …) |
| `importantNotices` | remarks/notices (`category: [GL, HR]`) |
| `NavigationMenu` | nav tree |

Fragments used by `raceMeetings`: **`raceFragment`** (on `Race`) and **`racingBlockFragment`**
(on `RaceMeeting`). The exact shipped document — query plus both fragments — is saved verbatim at
`queries/raceMeetings.graphql`.

### Variables

```json
{"date": "2026-10-25", "venueCode": "ST"}
```

- `date` is `YYYY-MM-DD`; `venueCode` is the **uppercase** code (`HV`, `ST`, `CH`, `S1`…`S9`).
- Send `{"date":"", "venueCode":""}` to get `activeMeetings` — the meetings HKJC is currently
  presenting (note: `activeMeetings` is the alias used by the shipped document for an unfiltered
  `raceMeetings` call).

### Observed meeting shape

```json
{"id":"MTG_20261025_0001","venueCode":"ST","date":"2026-10-25","status":"CLOSED",
 "totalNumberOfRace":11,"currentNumberOfRace":11,"dateOfWeek":"Sunday","meetingType":"...",
 "races":[{"no":1,"postTime":"2026-10-25T12:40:00+08:00","status":"RESULT","wageringFieldSize":11},
          ... 11 races ...]}
```

Race `status` values seen: `RESULT`. Meeting `status` values seen: `CLOSED`.
Pool `poolInvs[].status` values seen: `PAYOUT`.

Also present on 2026-10-25: a simulcast meeting `20261025S2` (`venueCode: "S2"`, 1 race, `CLOSED`).

## Notes

- The SPA loads the same bundle for `/racing/` and `/en/football/…`; the racing routes are inside
  `main.<hash>.js`.
- Racing uses **polling** (`RacingConfig.autoRefreshInterval = 30` s) in addition to the push —
  the push is the faster path.
- `validVenue` includes `S1`–`S9` (simulcast/overseas meetings), so the topic tree is not limited
  to local racing.
