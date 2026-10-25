#!/usr/bin/env python3
"""HKJC RACING live odds-push capture — self-contained (cron: no live meeting check).

Runs during a live meeting: finds the open meeting, builds concrete topics, connects to the
Solace broker and streams the odds deltas for --seconds. Prints a one-paragraph summary and
writes <out> for the agent to pick up.

    python racing_live_capture.py --seconds 180 --out ~/profiles/r2-d2/cron/output/racing_live.json
"""
import argparse, gzip, json, os, random, re, struct, subprocess, sys, time

ORIGIN = "https://bet.hkjc.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1")
GQL = "https://info.cld.hkjc.com/graphql/base-get/"
ENC_SAFE = "!'()*-._~"

HOST, PORT = "ueb.hkjc.com", 52443
DATE, VENUE = "", ""
REQ_TOPIC = "hk/d/prdt/wager/req/02/recovery/client"
RSP_PREFIX = "hk/d/prdt/wager/rpy/02/recovery/client/"

ODDS_SUFFIX = ["win/odds/full", "pla/odds/full", "qin/odds/full", "qpl/odds/full",
               "fct/odds/full", "tri/odds/full", "f_f/odds/full", "tce/odds/top_n",
               "qtt/odds/top_n", "iwn/odds/full", "cwa/odds/full", "cwb/odds/full",
               "cwc/odds/full", "dbl/odds/full", "tbl/odds/full", "d_t/inv", "t_t/inv",
               "6up/inv", "qtt/inv", "dbl/inv", "tbl/inv"]
EVT_SUFFIX = ["", "win", "pla", "qin", "qpl", "fct", "tri", "f_f", "tce", "qtt",
              "iwn", "cwa", "cwb", "cwc", "dbl", "tbl", "dt", "tt", "6up"]


def _get(url):
    r = subprocess.run(["curl", "-s", "--compressed", "--max-time", "25",
                        "-H", f"User-Agent: {UA}", "-H", "Accept-Language: en",
                        "-H", f"Referer: {ORIGIN}/", "-H", f"Origin: {ORIGIN}", url],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"curl rc={r.returncode}: {r.stderr[:160]}")
    return r.stdout


def enc(s):
    import urllib.parse
    return urllib.parse.quote(s, safe=ENC_SAFE)


def enc_json(v):
    return enc(json.dumps(v, separators=(",", ":")))


def _lit(js, marker, limit=30000):
    i = js.find(marker)
    if i < 0:
        raise RuntimeError(f"{marker!r} not in bundle - site redeployed")
    o = i
    while o > 0:
        o -= 1
        if js[o] == "'" and js[o - 1] != "\\":
            break
    j = i
    while True:
        k = js.find("'", j)
        if k < 0:
            raise RuntimeError(f"unterminated literal {marker!r}")
        if js[k - 1] != "\\":
            break
        j = k + 1
    return re.sub(r"\s+", " ", js[o + 1:min(k, o + 1 + limit)].encode().decode("unicode_escape")).strip()


def race_meetings(date="", venue=""):
    # the query document is byte-exact and shipped verbatim in the repo; the SPA bundle's own
    # copy is formatted differently and the server rejects it.
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "repos",
                     "hkjc-racing-api-study", "queries", "raceMeetings.graphql")
    q = open(os.path.abspath(p)).read().strip()
    url = (GQL + "?query=" + enc(q) + "&operationName=raceMeetings"
           + "&variables=" + enc_json({"date": date, "venueCode": venue}))
    return json.loads(_get(url))["data"]["raceMeetings"]


def no_login_secret():
    m = re.search(r"PUSH_NO_LOGIN_SECRET\s*:\s*'([^']+)'", _get(ORIGIN + "/Config/GlobalConfig.js"))
    if not m:
        raise RuntimeError("PUSH_NO_LOGIN_SECRET not found")
    return m.group(1)


def build_topics(dt, ve, races):
    t = []
    for no in list(races) + ["+"]:
        n = no if no == "+" else (no if int(no) >= 10 else "0" + str(int(no)))
        for s in ODDS_SUFFIX:
            t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/{n}/{s}")
        for s in EVT_SUFFIX:
            base = f"hk/d/evnt/racing/evt/02/upd/racing/{dt}/{ve}/{n}"
            t.append(base + ("/" + s if s else ""))
    t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/00/jkc/+/odds")
    t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/00/jkc/+/detail")
    t.append(f"hk/d/evnt/racing/evt/02/upd/racing/{dt}/{ve}")   # ALL_MEE
    return t


def _len(n):
    o = b""
    while True:
        d = n % 128; n //= 128
        if n: d |= 0x80
        o += bytes([d])
        if not n: return o


def _u8(s):
    b = s.encode(); return struct.pack("!H", len(b)) + b


def _pkt(t, b):
    return bytes([t]) + _len(len(b)) + b


def _up(k, v):
    kb, vb = k.encode(), v.encode()
    return b"\x26" + struct.pack("!H", len(kb)) + kb + struct.pack("!H", len(vb)) + vb


def _rd(buf, i):
    m, v = 1, 0
    while True:
        d = buf[i]; i += 1; v += (d & 127) * m
        if not d & 128: return v, i
        m *= 128


VENUES = ["HV", "ST", "CH", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]


def discover_meeting(days=12):
    """The server rejects empty variables (BAD_REQUEST), so find a real meeting: walk forward
    from today through the venue list until one returns data."""
    import datetime
    t0 = datetime.date.today()
    for i in range(days):
        d = (t0 + datetime.timedelta(days=i)).isoformat()
        for v in VENUES:
            try:
                ms = race_meetings(d, v)
            except Exception:
                continue
            if ms:
                return d, v, ms
    return None, None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", help="YYYY-MM-DD of a real meeting (else auto-discovered)")
    ap.add_argument("--venue", help="HV | ST | CH | S1..S9 (else auto-discovered)")
    a = ap.parse_args()
    global DATE, VENUE
    if a.date and a.venue:
        DATE, VENUE = a.date, a.venue.upper()
    else:
        DATE, VENUE, _ = discover_meeting()
        if not DATE:
            print("RACING PUSH CAPTURE: no meeting found in the next 12 days.")
            json.dump([], open(a.out, "w"))
            return
        print(f"RACING PUSH CAPTURE: discovered {VENUE} {DATE}")

    import websocket
    # raceMeetings("") returns nothing usable - variables must be a real meeting
    ms = race_meetings(DATE, VENUE)
    live = [m for m in ms if m.get("status") not in ("CLOSED", "RESULT", "PAYOUT")]
    if not live:
        desc = ", ".join(f"{m['venueCode']}:{m['status']}" for m in ms) or "none"
        print(f"RACING PUSH CAPTURE: no live meeting right now (activeMeetings: {desc}). "
              f"Nothing to capture.")
        json.dump([], open(a.out, "w"))
        return

    m = live[0]
    ve = m["venueCode"].lower()
    dt = m["date"].replace("-", "")
    races = [r["no"] for r in (m.get("races") or [])]
    print(f"RACING PUSH CAPTURE: {m['venueCode']} {m['date']} {m['status']}, {len(races)} races")

    secret = no_login_secret()
    cid = ("jcbw2_4e_" + "".join(random.choice("0123456789abcdef") for _ in range(6))
           + "_" + str(int(time.time() * 1000)))
    topics = build_topics(dt, ve, races)

    ws = websocket.create_connection(f"wss://{HOST}:{PORT}/", timeout=20,
                                     header=[f"Origin: {ORIGIN}", f"User-Agent: {UA}"],
                                     subprotocols=["mqtt"], sslopt={"cert_reqs": 0})
    ws.send_binary(_pkt(0x10, _u8("MQTT") + bytes([5]) + bytes([0xC2]) + struct.pack("!H", 60)
                        + b"\x00" + _u8(cid) + _u8("jcbw2") + _u8(secret)))
    ws.settimeout(10)
    ack = ws.recv(); ack = ack if isinstance(ack, bytes) else ack.encode()
    if len(ack) < 3 or ack[0] != 0x20 or ack[2] != 0x00:
        print(f"RACING PUSH CAPTURE: CONNACK rejected {ack.hex()}")
        return

    ws.send_binary(_pkt(0x82, struct.pack("!H", 1) + b"\x00" + _u8(RSP_PREFIX + cid) + bytes([0])))
    for n, t in enumerate(topics):
        ws.send_binary(_pkt(0x82, struct.pack("!H", 2 + n) + b"\x00" + _u8(t) + bytes([0])))
        if (2 + n) % 100 == 0:
            time.sleep(0.5)
    time.sleep(1.0)

    pr = _up("Trace-Id", f"live_{cid}_{int(time.time()*1000)}")
    payload = json.dumps({"systemCode": "JCBW2_4E", "senderId": cid,
                          "topics": topics, "latestMessageInSeconds": 120})
    ws.send_binary(_pkt(0x30, _u8(REQ_TOPIC) + b"\x00" + _len(len(pr)) + pr + payload.encode()))

    out, buf = [], b""
    ws.settimeout(5)
    end = time.time() + a.seconds
    while time.time() < end:
        try:
            d = ws.recv()
        except Exception:
            continue
        if isinstance(d, str):
            d = d.encode()
        buf += d
        while buf:
            t = buf[0] >> 4
            n, i = _rd(buf, 1)
            if len(buf) < i + n:
                break
            body, buf = buf[i:i + n], buf[i + n:]
            if t != 3:
                continue
            tl = struct.unpack("!H", body[0:2])[0]
            topic = body[2:2 + tl].decode("utf-8", "replace")
            p = 2 + tl
            pl, i2 = _rd(body, p)
            raw = body[i2 + pl:]
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
            out.append({"topic": topic, "raw": raw.decode("utf-8", "replace")})
    ws.close()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    pools, states = {}, {}
    for e in out:
        seg = e["topic"].split("/")
        pools["/".join(seg[-2:])] = pools.get("/".join(seg[-2:]), 0) + 1
    print(f"RACING PUSH CAPTURE: {len(out)} messages in {a.seconds}s across {len(pools)} topic "
          f"suffixes -> {a.out}")
    print("  top suffixes: " + ", ".join(f"{k}={v}" for k, v in sorted(pools.items(),
          key=lambda x: -x[1])[:8]))


if __name__ == "__main__":
    main()
