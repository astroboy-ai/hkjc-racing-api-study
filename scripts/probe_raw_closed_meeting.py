
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
DT, VE = "20261025", "st"
pools = ["win","pla","qin","qpl","fct","tri","ff","tce","qtt","iwn","cwa","cwb","cwc","dbl","tbl","dt","tt","6up"]
WANT = []
for no in ["01","02","10","11","+"]:
    for p in pools[:4]:
        WANT.append(f"hk/d/prdt/wager/evt/02/upd/racing/{DT}/{VE}/{no}/{p}/odds/full")
    WANT.append(f"hk/d/evnt/racing/evt/02/upd/racing/{DT}/{VE}/{no}")
WANT.append(f"hk/d/evnt/racing/evt/02/upd/racing/{DT}/{VE}")
WANT.append(f"hk/d/prdt/wager/evt/02/upd/racing/{DT}/{VE}/+/inv")
WANT.append(f"hk/d/prdt/wager/evt/02/upd/racing/{DT}/{VE}/00/jkc/+/odds")
WANT.append(f"hk/d/prdt/wager/evt/02/upd/racing/{DT}/{VE}/00/jkc/+/detail")
print("topics:", len(WANT))
pid=1
ws.send_binary(pk(0x82, struct.pack("!H",pid)+b"\x00"+u8(RECOV)+bytes([0]))); pid+=1; time.sleep(0.2)
for t in WANT:
    ws.send_binary(pk(0x82, struct.pack("!H",pid)+b"\x00"+u8(t)+bytes([0]))); pid+=1
    if pid % 25 == 0: time.sleep(0.3)
time.sleep(1.5)
for secs in [120, 3600, 43200, 604800]:
    trace="probe_"+CID+"_"+str(secs)+"_"+str(int(time.time()*1000))
    pl=json.dumps({"systemCode":"JCBW2_4E","senderId":CID,"topics":WANT,"latestMessageInSeconds":secs})
    pr=up("Trace-Id",trace)
    ws.send_binary(pk(0x30, u8(REQ)+b"\x00"+el(len(pr))+pr+pl.encode()))
    print("PUB recovery latestMessageInSeconds =", secs, flush=True)
    time.sleep(2)

msgs=[]; buf=b""; end=time.time()+75
ws.settimeout(5)
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
        if t==9: continue
        if t!=3: continue
        tl=struct.unpack("!H",body[0:2])[0]; topic=body[2:2+tl].decode("utf-8","replace"); p=2+tl
        pl2,i2=rl(body,p); raw=body[i2+pl2:]
        try: dec=gzip.decompress(raw).decode("utf-8")
        except Exception: dec=raw.decode("utf-8","replace")
        msgs.append({"topic":topic,"decoded":dec})
        print("PUB", topic, "|", dec[:300].replace("\n"," "), flush=True)
print("=== TOTAL:", len(msgs), flush=True)
json.dump(msgs, open(f"{O}/racing_push_closed_meeting.json","w"), ensure_ascii=False)
ws.close()
