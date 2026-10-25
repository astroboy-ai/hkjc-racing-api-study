#!/usr/bin/env python3
"""HKJC RACING odds push client (Solace MQTT v5 over WebSocket, no login).

Probed 2026-10-25. See docs/odds_push.md and docs/topic_map.md.

    pip install websocket-client
    python racing_push_client.py --date 20261028 --venue hv --seconds 120 --out push.json

The recovery request needs CONCRETE topics, so build them from the real card. Use
`--auto` (default) to fetch the meeting via GraphQL and build the topics for you, or
pass `--topics` explicitly.

NOTE: the broker keeps no cache for a closed meeting - run this during a live meeting.
"""
import argparse, gzip, json, os, random, re, struct, subprocess, sys, time, urllib.parse

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

HOST, PORT = "ueb.hkjc.com", 52443
WS_URL = f"wss://{HOST}:{PORT}/"
ORIGIN = "https://bet.hkjc.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1")
GQL = "https://info.cld.hkjc.com/graphql/base-get/"

# The server is byte-exact: `encodeURIComponent` leaves ( ) ! ' * - . _ ~ alone and
# the JSON must be compact (no spaces after ":" / ","). json.dumps defaults add them.
_ENC_SAFE = "!'()*-._~"


def enc(s):
    return urllib.parse.quote(s, safe=_ENC_SAFE)


def enc_json(v):
    return enc(json.dumps(v, separators=(",", ":")))




REQ_TOPIC = "hk/d/prdt/wager/req/02/recovery/client"
RSP_PREFIX = "hk/d/prdt/wager/rpy/02/recovery/client/"

# pools to request, by suffix after {no}/
ODDS_SUFFIX = ["win/odds/full", "pla/odds/full", "qin/odds/full", "qpl/odds/full",
               "fct/odds/full", "tri/odds/full", "f_f/odds/full", "tce/odds/top_n",
               "qtt/odds/top_n", "iwn/odds/full", "cwa/odds/full", "cwb/odds/full",
               "cwc/odds/full", "dbl/odds/full", "tbl/odds/full", "d_t/inv", "t_t/inv",
               "6up/inv", "qtt/inv", "dbl/inv", "tbl/inv"]
EVT_SUFFIX = [""] + ["win", "pla", "qin", "qpl", "fct", "tri", "f_f", "tce", "qtt",
                     "iwn", "cwa", "cwb", "cwc", "dbl", "tbl", "dt", "tt", "6up"]



def _get(url):
    """curl, not urllib: the server rejects urllib's default header set."""
    r = subprocess.run(["curl", "-s", "--compressed", "--max-time", "25",
                        "-H", f"User-Agent: {UA}", "-H", "Accept-Language: en",
                        "-H", f"Referer: {ORIGIN}/", "-H", f"Origin: {ORIGIN}", url],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout


def no_login_secret():
    """Read PUSH_NO_LOGIN_SECRET from the public site config (never hard-code it)."""
    m = re.search(r"PUSH_NO_LOGIN_SECRET\s*:\s*'([^']+)'", _get(ORIGIN + "/Config/GlobalConfig.js"))
    if not m:
        raise RuntimeError("PUSH_NO_LOGIN_SECRET not found in GlobalConfig.js")
    return m.group(1)


# --- GraphQL: the race card ------------------------------------------------
def race_meetings(date="", venue=""):
    q = open(__file__.replace("scripts/racing_push_client.py",
                              "queries/raceMeetings.graphql")).read() \
        if False else _bundled_query()
    url = (GQL + "?query=" + enc(q) + "&operationName=raceMeetings"
           + "&variables=" + enc_json({"date": date, "venueCode": venue}))
    return json.loads(_get(url))["data"]["raceMeetings"]


def _bundled_query():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "queries", "raceMeetings.graphql")
    if os.path.exists(p):
        return open(p).read().strip()
    return _extract_from_bundle()


def _extract_from_bundle():
    shell = _get(ORIGIN + "/racing/")
    m = re.search(r"/static/js/(main\.[A-Za-z0-9._-]+\.js)", shell)
    if not m:
        raise RuntimeError("main bundle not found")
    js = _get(f"{ORIGIN}/static/js/{m.group(1)}")

    def lit(marker, limit=30000):
        i = js.find(marker)
        if i < 0:
            raise RuntimeError(f"{marker!r} not found in bundle")
        j = i
        while True:
            k = js.find("'", j)
            if k < 0:
                raise RuntimeError(f"unterminated literal for {marker!r}")
            if js[k - 1] != "\\":
                break
            j = k + 1
        return re.sub(r"\s+", " ", js[i:min(k, i + limit)].encode().decode("unicode_escape")).strip()

    # fragments MUST come first - the server is byte-exact about document order
    return " ".join([lit("fragment raceFragment", 2000),
                     lit("fragment racingBlockFragment", 4000),
                     lit("query raceMeetings")])


def build_topics(dt, ve, races, with_events=True):
    """dt='20261028', ve='hv', races=[1,2,...]"""
    t = []
    for no in list(races) + ["+"]:
        n = no if no == "+" else (no if int(no) >= 10 else "0" + str(int(no)))
        for s in ODDS_SUFFIX:
            t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/{n}/{s}")
        if with_events:
            for s in EVT_SUFFIX:
                base = f"hk/d/evnt/racing/evt/02/upd/racing/{dt}/{ve}/{n}"
                t.append(base + ("/" + s if s else ""))
    t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/00/jkc/+/odds")
    t.append(f"hk/d/prdt/wager/evt/02/upd/racing/{dt}/{ve}/00/jkc/+/detail")
    t.append(f"hk/d/evnt/racing/evt/02/upd/racing/{dt}/{ve}")     # ALL_MEE
    return t


# --- minimal MQTT v5 ------------------------------------------------------
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


def connect(cid, secret):
    ws = websocket.create_connection(WS_URL, timeout=20,
                                     header=[f"Origin: {ORIGIN}", f"User-Agent: {UA}"],
                                     subprotocols=["mqtt"], sslopt={"cert_reqs": 0})
    ws.send_binary(_pkt(0x10, _u8("MQTT") + bytes([5]) + bytes([0xC2]) + struct.pack("!H", 60)
                        + b"\x00" + _u8(cid) + _u8("jcbw2") + _u8(secret)))
    ws.settimeout(10)
    a = ws.recv(); a = a if isinstance(a, bytes) else a.encode()
    if len(a) < 3 or a[0] != 0x20 or a[2] != 0x00:
        raise RuntimeError(f"CONNACK rejected: {a.hex()}")
    return ws


def subscribe(ws, topics, pid0=1):
    for n, t in enumerate(topics):
        ws.send_binary(_pkt(0x82, struct.pack("!H", pid0 + n) + b"\x00" + _u8(t) + bytes([0])))
        if (pid0 + n) % 40 == 0:
            time.sleep(0.4)
    time.sleep(1.0)


def recovery(ws, cid, topics, seconds=120):
    trace = f"probe_{cid}_{int(time.time()*1000)}"
    payload = json.dumps({"systemCode": "JCBW2_4E", "senderId": cid,
                          "topics": topics, "latestMessageInSeconds": seconds})
    pr = _up("Trace-Id", trace)
    ws.send_binary(_pkt(0x30, _u8(REQ_TOPIC) + b"\x00" + _len(len(pr)) + pr + payload.encode()))


def stream(ws, deadline):
    buf = b""
    ws.settimeout(5)
    while time.time() < deadline:
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
            yield topic, raw.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (topic form)")
    ap.add_argument("--venue", help="lowercase venue code, e.g. hv")
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--out", default="push.json")
    ap.add_argument("--topics", nargs="*", default=None, help="explicit topic list")
    ap.add_argument("--secret", default=None)
    a = ap.parse_args()

    secret = a.secret or no_login_secret()
    cid = "jcbw2_4e_" + "".join(random.choice("0123456789abcdef") for _ in range(6)) \
          + "_" + str(int(time.time() * 1000))

    if a.topics:
        topics = a.topics
    else:
        if not a.date or not a.venue:
            sys.exit("need --date/--venue, or --topics")
        iso = f"{a.date[:4]}-{a.date[4:6]}-{a.date[6:]}"
        ms = race_meetings(iso, a.venue.upper())
        races = [r["no"] for r in (ms[0]["races"] if ms else [])]
        print(f"meeting {a.venue.upper()} {iso}: {len(races)} races", flush=True)
        topics = build_topics(a.date, a.venue, races)

    print(f"connecting wss://{HOST}:{PORT}/ as {cid}; {len(topics)} topics", flush=True)
    ws = connect(cid, secret)
    subscribe(ws, [RSP_PREFIX + cid] + topics)
    recovery(ws, cid, topics)
    out = []
    for topic, txt in stream(ws, time.time() + a.seconds):
        out.append({"topic": topic, "raw": txt})
        print(topic, "|", txt[:220], flush=True)
    ws.close()
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"\n{len(out)} messages -> {a.out}")


if __name__ == "__main__":
    main()
