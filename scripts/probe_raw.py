
import json, time, random, struct, gzip
import websocket
O = "/opt/data/profiles/r2-d2/cache/scratch/h36"
SECRET = open(f"{O}/.nologin_secret").read().strip()
CID = "jcbw2_4e_" + "".join(random.choice("0123456789abcdef") for _ in range(6)) + "_" + str(int(time.time()*1000))
def el(n):
    o=b""
    while True:
        d=n%128; n//=128
        if n>0: d|=0x80
        o+=bytes([d])
        if n==0: break
    return o
def u8(s):
    b=s.encode(); return struct.pack("!H",len(b))+b
def pk(t,b): return bytes([t])+el(len(b))+b
def rl(buf,i):
    m=1; v=0
    while True:
        d=buf[i]; i+=1; v+=(d&127)*m
        if not (d&128): break
        m*=128
    return v,i
def up(k,v):
    kb=k.encode(); vb=v.encode()
    return b"\x26"+struct.pack("!H",len(kb))+kb+struct.pack("!H",len(vb))+vb

ws = websocket.create_connection("wss://ueb.hkjc.com:52443/", timeout=20,
    header=["Origin: https://bet.hkjc.com",
            "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"],
    subprotocols=["mqtt"], sslopt={"cert_reqs":0})
ws.send_binary(pk(0x10, u8("MQTT")+bytes([5])+bytes([0xC2])+struct.pack("!H",60)+b"\x00"+u8(CID)+u8("jcbw2")+u8(SECRET)))
ws.settimeout(10); r=ws.recv(); print("CONNACK:", (r if isinstance(r,bytes) else r.encode()).hex(), flush=True)

RECOV="hk/d/prdt/wager/rpy/02/recovery/client/"+CID
REQ="hk/d/prdt/wager/req/02/recovery/client"
WANT=[
 "hk/d/prdt/wager/evt/02/upd/racing/#",
 "hk/d/prdt/wager/evt/01/upd/racing/#",
 "hk/d/evnt/racing/evt/01/upd/racing/#",
 "hk/d/evnt/racing/evt/02/upd/racing/#",
]
pid=1
for t in [RECOV]+WANT:
    ws.send_binary(pk(0x82, struct.pack("!H",pid)+b"\x00"+u8(t)+bytes([0])))
    print("SUB", t, flush=True); pid+=1; time.sleep(0.25)
trace="probe_"+CID+"_"+str(int(time.time()*1000))
pl=json.dumps({"systemCode":"JCBW2_4E","senderId":CID,"topics":WANT,"latestMessageInSeconds":120})
pr=up("Trace-Id",trace)
ws.send_binary(pk(0x30, u8(REQ)+b"\x00"+el(len(pr))+pr+pl.encode()))
print("PUB recovery", flush=True)

msgs=[]; buf=b""; end=time.time()+100
ws.settimeout(6)
while time.time()<end:
    try: d=ws.recv()
    except Exception: continue
    if isinstance(d,str): d=d.encode()
    buf+=d
    while True:
        if not buf: break
        t=buf[0]>>4
        n,i=rl(buf,1)
        if len(buf)<i+n: break
        body=buf[i:i+n]; buf=buf[i+n:]
        if t==9: print("SUBACK", body.hex(), flush=True); continue
        if t!=3: print("PKT", t, body.hex()[:100], flush=True); continue
        tl=struct.unpack("!H",body[0:2])[0]; topic=body[2:2+tl].decode("utf-8","replace"); p=2+tl
        pl2,i2=rl(body,p); raw=body[i2+pl2:]
        try: dec=gzip.decompress(raw).decode("utf-8")
        except Exception: dec=raw.decode("utf-8","replace")
        msgs.append({"topic":topic,"decoded":dec})
        print("PUB", topic, flush=True); print("   ", dec[:400].replace("\n"," "), flush=True)
json.dump(msgs, open(f"{O}/racing_push_samples.json","w"), ensure_ascii=False)
print("=== TOTAL:", len(msgs), flush=True)
tc={}
for m in msgs: tc[m["topic"]]=tc.get(m["topic"],0)+1
print("TOPICS:", json.dumps(tc, indent=1)[:2000], flush=True)
ws.close()
