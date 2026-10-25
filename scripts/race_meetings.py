#!/usr/bin/env python3
"""Fetch the HKJC racing card / meeting list (GraphQL raceMeetings).

    python race_meetings.py --date 2026-10-25 --venue ST
    python race_meetings.py --active          # meetings currently presented

Needs `operationName=raceMeetings` and the exact shipped query; see docs/endpoint_catalog.md.
"""
import argparse, json, os, re, subprocess, sys, urllib.parse

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






def _get(url):
    """curl, not urllib: the server rejects urllib's default header set."""
    r = subprocess.run(["curl", "-s", "--compressed", "--max-time", "25",
                        "-H", f"User-Agent: {UA}", "-H", "Accept-Language: en",
                        "-H", f"Referer: {ORIGIN}/", "-H", f"Origin: {ORIGIN}", url],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout


def _extract_from_bundle():
    shell = _get(ORIGIN + "/racing/")
    m = re.search(r"/static/js/(main\.[A-Za-z0-9._-]+\.js)", shell)
    if not m:
        sys.exit("main bundle not found in the SPA shell")
    js = _get(f"{ORIGIN}/static/js/{m.group(1)}")

    def lit(marker, limit=30000):
        i = js.find(marker)
        if i < 0:
            sys.exit(f"{marker!r} not found - the site may have redeployed")
        # the literal's opening quote is the nearest unescaped ' before the marker
        o = i
        while o > 0:
            o -= 1
            if js[o] == "'" and js[o - 1] != "\\":
                break
        j = i
        while True:
            k = js.find("'", j)
            if k < 0:
                sys.exit(f"unterminated literal for {marker!r}")
            if js[k - 1] != "\\":
                break
            j = k + 1
        return re.sub(r"\s+", " ", js[o + 1:min(k, o + 1 + limit)].encode().decode("unicode_escape")).strip()

    # fragments MUST come first - the server is byte-exact about document order
    return " ".join([lit("fragment raceFragment", 2000),
                     lit("fragment racingBlockFragment", 4000),
                     lit("query raceMeetings")])


def bundled_query():
    """Use the captured document if present, else extract it from the SPA bundle."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "queries", "raceMeetings.graphql")
    if os.path.exists(p):
        return open(p).read().strip()
    return _extract_from_bundle()



def race_meetings(date="", venue=""):
    url = (GQL + "?query=" + enc(bundled_query())
           + "&operationName=raceMeetings"
           + "&variables=" + enc_json({"date": date, "venueCode": venue}))
    return json.loads(_get(url))["data"]["raceMeetings"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD")
    ap.add_argument("--venue", default="", help="HV | ST | CH | S1..S9")
    ap.add_argument("--active", action="store_true", help="meetings currently presented")
    ap.add_argument("--out")
    a = ap.parse_args()

    ms = race_meetings("" if a.active else a.date, a.venue.upper())
    for m in ms:
        print(f"{m['id']}  venue={m['venueCode']}  date={m['date']}  status={m['status']}  "
              f"races={m.get('totalNumberOfRace')}  current={m.get('currentNumberOfRace')}")
        for r in (m.get("races") or []):
            print(f"   race {r['no']:>2}  post={r.get('postTime')}  status={r.get('status')}  "
                  f"field={r.get('wageringFieldSize')}")
        pools = m.get("poolInvs") or []
        if pools:
            st = {}
            for p in pools:
                st[p.get("status")] = st.get(p.get("status"), 0) + 1
            print("   poolInvs:", st)
    if not ms:
        print("(no meetings returned)")
    if a.out:
        json.dump(ms, open(a.out, "w"), ensure_ascii=False, indent=1)
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
