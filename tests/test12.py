import sys, os, json, shutil, http.client, threading
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache12"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv12.sock", mpv_args=[], port_agent=18771)
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("a.mp4", "p1.mp4", "p2.jpg", "q1.mp4", "fundal.jpg"): open(d + "/clips/" + n, "wb").write(b"x")
D = lambda f, o: {"file": f, "days": [1,2,3,4,5,6,7], "order": o}
X = {"date":"2026-12-05","start":"14:00","durationMinutes":60,"files":[{"file":"p2.jpg","order":2,"imageSeconds":30},{"file":"p1.mp4","order":1}]}
Q = {"date":"2026-12-05","start":"16:00","durationMinutes":30,"files":[{"file":"q1.mp4","order":1}]}
def write(parties):
    json.dump({"open":"09:00","close":"20:00","stopImage":"fundal.jpg","default":[D("a.mp4",1)],"parties":parties}, open(d+"/program.json","w"))
write([X, Q]); XID = "2026-12-05 14:00"; QID = "2026-12-05 16:00"
a = agent.Agent(); names = lambda: [os.path.basename(p) for p, _ in a.playlist]
log = lambda: [json.loads(l) for l in open(T + "/run/fake-mpv.log")]
loads = lambda: sum(1 for c in log() if c[0] == "loadfile")
def last_pause():
    v = None
    for c in log():
        if c[0] == "set_property" and c[1] == "pause": v = c[2]
    return v
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
def ticks(t, n=2):
    at(t)
    for _ in range(n): a.tick()
XF = ["p1.mp4", "p2.jpg"]

print("--- A. pornita INAINTE de ora ei: ca un clip implicit, ignora doar ora ei de inceput si de sfarsit")
ticks("2026-12-05 13:50"); ok(names() == ["a.mp4"], "13:50 ruleaza clipul implicit")
r = a.command("party", XID); ok(r == (True, "ok") and names() == XF and a.manual == "party", "party -> porneste fisierele petrecerii in ordine: %s" % names())
n = loads(); ticks("2026-12-05 14:00"); ok(a.manual == "party" and names() == XF and loads() == n, "14:00 (propria ei ora de inceput): continua, fara sa reia playlistul")
ticks("2026-12-05 15:00"); ok(a.manual == "party" and names() == XF, "15:00 (propriul ei sfarsit): continua")
ticks("2026-12-05 15:59", 3); ok(a.manual == "party" and names() == XF, "15:59 inca ruleaza")
ticks("2026-12-05 16:00"); ok(a.key.startswith("party:2026-12-05 16:00") and names() == ["q1.mp4"] and a.manual is None and a.party_session is None, "16:00 incepe AUTOMAT petrecerea urmatoare, asa cum e programata: %s" % names())
ticks("2026-12-05 16:30"); ok(a.key == "default" and names() == ["a.mp4"] and a.manual is None, "16:30 dupa petrecerea programata -> clipul implicit (cea pornita manual nu revine)")

print("--- B. prelungire: petrecerea ruleaza programat, apesi 'Pornește acum' inainte sa se termine")
ticks("2026-12-05 14:30"); ok(a.key.startswith("party:2026-12-05 14:00") and names() == XF and a.manual is None, "14:30 ruleaza programat")
a.command("party", XID); ticks("2026-12-05 14:55")
ticks("2026-12-05 15:00"); ok(a.manual == "party" and names() == XF, "15:00 (sfarsitul programat) -> continua")
ticks("2026-12-05 19:59", 3); ok(a.manual == "party" and names() == XF, "19:59 inca ruleaza, ca un clip implicit")
ticks("2026-12-05 20:00"); ok(not a.player.running() and a.manual is None and a.party_session is None, "20:00 se inchide programul -> playerul se opreste, ca la un clip implicit")

print("--- C. pornita dupa ora de sfarsit")
ticks("2026-12-05 15:40"); ok(a.key == "default" and names() == ["a.mp4"], "15:40 clip implicit")
a.command("party", XID); ticks("2026-12-05 15:50", 3); ok(a.manual == "party" and names() == XF, "pornita dupa sfarsit: ruleaza")
ticks("2026-12-05 16:00"); ok(names() == ["q1.mp4"] and a.manual is None, "16:00 incepe automat urmatoarea petrecere programata")

print("--- D. 'Pornește acum' pe petrecerea URMATOARE: acelasi comportament")
ticks("2026-12-05 15:30"); a.command("party", XID); ok(names() == XF, "ruleaza X manual")
r = a.command("party", QID); ok(r[0] and names() == ["q1.mp4"] and a.party_session == QID and a.manual == "party", "pornesti urmatoarea (Q) acum -> o inlocuieste pe X: %s" % names())
n = loads(); ticks("2026-12-05 16:00"); ok(a.manual == "party" and names() == ["q1.mp4"] and a.party_session == QID and loads() == n, "16:00 (ora ei programata): continua fara sa reia")
ticks("2026-12-05 16:30"); ok(a.manual == "party" and names() == ["q1.mp4"], "16:30 (propriul ei sfarsit): continua")
ticks("2026-12-05 19:59", 2); ok(a.manual == "party" and names() == ["q1.mp4"], "19:59 inca ruleaza")
ticks("2026-12-05 20:00"); ok(not a.player.running(), "20:00 inchiderea programului o opreste")

print("--- E. pornita cand programul e inchis")
ticks("2026-12-05 21:00"); ok(not a.player.running(), "21:00 nimic nu ruleaza")
r = a.command("party", XID); ok(r[0] and names() == XF, "porneste in afara programului")
ticks("2026-12-05 23:30", 3); ok(a.player.running() and names() == XF and a.manual == "party", "ramane pornita peste noapte (comenzi doar manuale)")
ticks("2026-12-06 09:00"); ok(a.manual is None and names() == ["a.mp4"], "9:00 se deschide programul -> preia programul (clipul implicit)")

print("--- F. pauza / play / next in sesiune")
a.command("party", XID); ticks("2026-12-06 12:00"); a.command("pause"); ticks("2026-12-06 12:10")
ok(a.manual == "pause" and last_pause() is True and names() == XF, "pauza in petrecerea manuala ramane")
ticks("2026-12-06 14:00"); ticks("2026-12-06 15:00"); ok(a.manual == "pause" and last_pause() is True, "pauza ramane si peste propriile ore de inceput/sfarsit")
a.command("play"); ticks("2026-12-06 15:05"); ok(a.manual == "party" and last_pause() is False, "play din pauza -> continua")
a.command("pause"); a.command("next"); ticks("2026-12-06 15:10"); ok(a.manual == "party" and last_pause() is False and names() == XF, "next din pauza -> porneste, ramane in sesiune")
a.command("pause"); ticks("2026-12-06 15:20")
write([X, dict(Q, date="2026-12-06")]); ticks("2026-12-06 15:30")
ticks("2026-12-06 16:00"); ok(names() == ["q1.mp4"] and a.manual is None and last_pause() is False, "pe pauza, 16:00 incepe automat urmatoarea petrecere, nepauzata")
write([X, Q])

print("--- Stop")
a.command("party", XID); ticks("2026-12-06 17:00"); a.command("stop"); ticks("2026-12-06 17:10")
ok(names() == ["fundal.jpg"] and a.manual == "stop" and a.party_session is None, "stop -> poza de fundal, sesiunea s-a incheiat")
a.command("play"); ticks("2026-12-06 17:20"); ok(names() == ["a.mp4"], "play dupa stop -> clipul implicit")

print("--- program modificat cat ruleaza")
ticks("2026-12-05 11:00"); a.command("party", XID)
P2 = dict(X, files=[{"file":"p2.jpg","order":1,"imageSeconds":30}]); write([P2, Q]); ticks("2026-12-05 11:10")
ok(names() == ["p2.jpg"] and a.manual == "party", "petrecerea modificata in program (sync) -> urmeaza noul continut")
write([Q]); ticks("2026-12-05 11:20")
ok(a.manual == "party" and names() == ["p2.jpg"], "petrecerea stearsa din program -> continua cu ultima versiune cunoscuta")
os.rename(d+"/clips/p2.jpg", d+"/clips/p2.bak"); ticks("2026-12-05 11:30")
ok(a.manual is None and a.party_session is None, "fisierele ei nu mai exista pe player -> sesiunea se termina")
os.rename(d+"/clips/p2.bak", d+"/clips/p2.jpg"); write([X, Q])

print("--- erori")
ticks("2026-12-05 10:00")
r = a.command("party", "2026-12-05 09:00"); ok(r == (False, "petrecerea nu e in programul de pe player (salveaza programul)"), "petrecere necunoscuta -> 409")
r = a.command("party", None); ok(r[0] is False, "fara id -> 409")
os.rename(d+"/clips/p1.mp4", d+"/clips/p1.bak"); os.rename(d+"/clips/p2.jpg", d+"/clips/p2.bak")
r = a.command("party", XID); ok(r == (False, "fisierele petrecerii nu sunt pe player"), "fisiere lipsa pe Pi -> 409")
os.rename(d+"/clips/p1.bak", d+"/clips/p1.mp4"); os.rename(d+"/clips/p2.bak", d+"/clips/p2.jpg")

print("--- HTTP")
from http.server import ThreadingHTTPServer
ticks("2026-12-05 11:00")
srv = ThreadingHTTPServer(("127.0.0.1", 18771), agent.make_handler(a)); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(body):
    c = http.client.HTTPConnection("127.0.0.1", 18771, timeout=5); raw = json.dumps(body).encode()
    c.request("POST", "/command", body=raw, headers={"Content-Length": str(len(raw))}); r = c.getresponse(); return r.status, json.loads(r.read())
ok(post({"command": "party", "party": XID})[0] == 200 and a.manual == "party", "POST party valid -> 200")
ok(post({"command": "party", "party": "2000-01-01 00:00"})[0] == 409, "POST party necunoscut -> 409")
ok(post({"command": "party"})[0] == 400 and post({"command": "party", "party": 5})[0] == 400, "POST party fara argument / non-string -> 400")
c = http.client.HTTPConnection("127.0.0.1", 18771, timeout=5); c.request("GET", "/status"); st = json.loads(c.getresponse().read())
ok(st["manual"] == "party" and st["party"] == XID, "/status: manual=party, party=%s" % st["party"])
print("\n%d verificari picate" % len(bad)); [print("  -", m) for m in bad]
a.player.stop()
