import sys, os, json, shutil, time, threading, http.client
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache13"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips"); os.makedirs(d + "/vps")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv13.sock", mpv_args=[], port_agent=18772, ssh_target="x@y", remote_program="program.json", remote_clips_dir=".")
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("a.mp4", "fundal.jpg", "q1.mp4", "q2.mp4", "q3.jpg", "p1.mp4"): open(d + "/clips/" + n, "wb").write(b"x")
D = lambda f, o: {"file": f, "days": [1,2,3,4,5,6,7], "order": o}
P = {"date":"2026-12-05","start":"16:00","durationMinutes":30,"files":[{"file":"p1.mp4","order":1}]}
def write(parties=None):
    json.dump({"open":"09:00","close":"20:00","stopImage":"fundal.jpg","default":[D("a.mp4",1)],"parties":parties if parties is not None else [P]}, open(d+"/program.json","w"))
write(); PID = "2026-12-05 16:00"
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
def wait(cond, secs=5):
    end = time.time() + secs
    while time.time() < end and not cond(): time.sleep(0.05)
    return cond()
Q = lambda *fs: [{"file": f} for f in fs]

print("--- rulare rapida cu fisiere deja pe player")
ticks("2026-12-05 10:00"); ok(names() == ["a.mp4"], "10:00 ruleaza clipul implicit")
r = a.command("quick", agent.parse_quick_files([{"file": "q2.mp4"}, {"file": "q1.mp4"}, {"file": "q3.jpg", "imageSeconds": 45}]))
ok(r == (True, "ok") and names() == ["q2.mp4", "q1.mp4", "q3.jpg"] and a.manual == "party" and a.party_session == "adhoc", "quick -> porneste in ordinea data (nu cea din program): %s" % names())
loadlog = [c for c in log() if c[0] == "loadfile"][-3:]
ok(loadlog[2][-1] == "image-display-duration=45", "imageSeconds trimis la mpv: %s" % loadlog[2][-1])
ticks("2026-12-05 11:00", 3); ok(a.manual == "party" and names() == ["q2.mp4", "q1.mp4", "q3.jpg"], "ruleaza mai departe peste ore")
a.command("pause"); ticks("2026-12-05 12:00"); ok(a.manual == "pause" and last_pause() is True and names() == ["q2.mp4", "q1.mp4", "q3.jpg"], "pauza in rularea rapida ramane")
a.command("play"); ticks("2026-12-05 12:10"); ok(a.manual == "party" and last_pause() is False, "play din pauza -> continua")
n = loads(); ok(a.command("play")[0] and loads() == n, "play cat ruleaza: nu schimba nimic")
print("--- se comporta ca un clip implicit")
ticks("2026-12-05 16:00"); ok(a.key == PID.join(["party:", ""]) and names() == ["p1.mp4"] and a.manual is None and a.party_session is None, "16:00 incepe automat petrecerea programata si o inlocuieste: %s" % names())
a.command("quick", agent.parse_quick_files(Q("q1.mp4"))); ticks("2026-12-05 16:40")
ok(a.key == "default" and a.manual == "party" and names() == ["q1.mp4"], "dupa petrecerea programata, rularea rapida pornita in timpul ei continua (tinta devine implicit)")
ticks("2026-12-05 19:59", 2); ok(names() == ["q1.mp4"], "19:59 inca ruleaza")
ticks("2026-12-05 20:00"); ok(not a.player.running() and a.manual is None and a.party_session is None, "20:00 inchiderea programului o opreste")
a.command("quick", agent.parse_quick_files(Q("q1.mp4"))); ticks("2026-12-05 21:00"); ok(names() == ["q1.mp4"] and a.manual == "party", "in afara programului: porneste si ramane")
ticks("2026-12-06 09:00"); ok(a.manual is None and names() == ["a.mp4"], "la deschiderea programului preia programul")
a.command("quick", agent.parse_quick_files(Q("q2.mp4"))); a.command("stop"); ticks("2026-12-06 09:10")
ok(names() == ["fundal.jpg"] and a.manual == "stop" and a.party_session is None, "stop -> poza de fundal, sesiunea se termina")
print("--- inlocuire intre rularea rapida si petrecerile din program")
ticks("2026-12-05 10:00"); a.command("quick", agent.parse_quick_files(Q("q1.mp4")))
r = a.command("party", PID); ok(r[0] and names() == ["p1.mp4"] and a.party_session == PID, "party in locul rularii rapide")
r = a.command("quick", agent.parse_quick_files(Q("q2.mp4"))); ok(r[0] and names() == ["q2.mp4"] and a.party_session == "adhoc", "quick in locul unei petreceri pornite")

print("--- fisiere care nu sunt pe player: se descarca la cerere")
gate = threading.Event(); fetched = []
for n in os.listdir(d + "/clips"): shutil.copy(d + "/clips/" + n, d + "/vps/" + n)   # "VPS": toate fisierele din program
shutil.copy(d + "/clips/q1.mp4", d + "/vps/nou1.mp4"); shutil.copy(d + "/clips/q1.mp4", d + "/vps/nou2.mp4")
shutil.copy(d + "/program.json", d + "/vps/program.json")
def fake(remote, local):
    name = os.path.basename(remote)
    if name == "boom.mp4": raise RuntimeError("rsync: nu exista")
    if name.startswith("nou"): gate.wait(5)
    fetched.append(name)
    shutil.copy(d + "/vps/" + name, local)
a.rsync = fake
ticks("2026-12-05 10:00"); a.command("stop"); a.command("play"); ticks("2026-12-05 10:05"); ok(names() == ["a.mp4"], "ruleaza clipul implicit")
r = a.command("quick", agent.parse_quick_files(Q("nou1.mp4", "nou2.mp4")))
ok(r[0] and "se descarca 2 fisiere" in r[1] and a.adhoc_loading and a.party_session == "adhoc", "fisiere lipsa: porneste descarcarea in fundal: %s" % (r,))
ticks("2026-12-05 10:06", 3); ok(a.manual == "party" and names() == ["a.mp4"] and a.player.running(), "cat se descarca, continua ce rula (sesiunea nu se termina)")
st = a.status(); ok(st["party_loading"] is True and st["party"] == "adhoc", "/status: party_loading=true")
gate.set(); ok(wait(lambda: not a.adhoc_loading), "descarcarea s-a terminat")
ticks("2026-12-05 10:07"); ok(names() == ["nou1.mp4", "nou2.mp4"] and a.adhoc_error is None, "dupa descarcare porneste rularea rapida: %s" % names())
print("--- fisierele rularii rapide nu se sterg la sync")
a.sync(); wait(lambda: not a.sync_busy)
ok(os.path.exists(d + "/clips/nou1.mp4") and os.path.exists(d + "/clips/nou2.mp4"), "sync in timpul sesiunii: fisierele ei raman, desi nu sunt in program")
a.command("stop"); ticks("2026-12-05 10:10"); a.sync(); wait(lambda: not a.sync_busy)
ok(not os.path.exists(d + "/clips/nou1.mp4"), "dupa Stop, la urmatorul sync se curata")
print("--- descarcare esuata")
a.command("play"); ticks("2026-12-05 10:15")
r = a.command("quick", agent.parse_quick_files(Q("boom.mp4"))); wait(lambda: not a.adhoc_loading)
ok(a.adhoc_error and "boom.mp4" in a.adhoc_error, "esec la descarcare: eroare in status: %s" % a.adhoc_error)
ticks("2026-12-05 10:16"); ok(a.manual is None and a.party_session is None and names() == ["a.mp4"], "sesiunea se termina, revine la program")

print("--- validare (HTTP)")
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 18772), agent.make_handler(a)); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(body):
    c = http.client.HTTPConnection("127.0.0.1", 18772, timeout=5); raw = json.dumps(body).encode()
    c.request("POST", "/command", body=raw, headers={"Content-Length": str(len(raw))}); r = c.getresponse(); return r.status, json.loads(r.read())
ticks("2026-12-05 10:30")
ok(post({"command": "quick", "files": [{"file": "q1.mp4"}]})[0] == 200, "valid -> 200")
for label, body in [("fara files", {"command": "quick"}), ("files nu e lista", {"command": "quick", "files": "q1.mp4"}), ("lista goala", {"command": "quick", "files": []}),
                    ("peste 50", {"command": "quick", "files": [{"file": "f%d.mp4" % i} for i in range(51)]}),
                    ("nume cu /", {"command": "quick", "files": [{"file": "a/b.mp4"}]}), ("nume cu ..", {"command": "quick", "files": [{"file": "../x.mp4"}]}),
                    ("nume ascuns", {"command": "quick", "files": [{"file": ".ascuns"}]}), ("fara nume", {"command": "quick", "files": [{}]}),
                    ("element non-dict", {"command": "quick", "files": ["q1.mp4"]}), ("imageSeconds 0", {"command": "quick", "files": [{"file": "q3.jpg", "imageSeconds": 0}]}),
                    ("imageSeconds text", {"command": "quick", "files": [{"file": "q3.jpg", "imageSeconds": "x"}]})]:
    ok(post(body)[0] == 400, "respins (400): " + label)
big = {"command": "quick", "files": [{"file": "fisier_cu_nume_lung_%d_%s.mp4" % (i, "x" * 40), "imageSeconds": 10} for i in range(50)]}
ok(len(json.dumps(big)) > 4096 and post(big)[0] == 200, "50 de fisiere (corp > 4 KB) -> 200")
print("\n%d verificari picate" % len(bad)); [print("  -", m) for m in bad]
a.player.stop()
