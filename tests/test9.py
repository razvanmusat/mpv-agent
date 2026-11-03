import sys, os, json, shutil
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache9"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv9.sock", mpv_args=[])
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("a.mp4", "b.jpg", "p1.mp4", "p2.mp4", "fundal.jpg"): open(d + "/clips/" + n, "wb").write(b"x")
D = lambda f, o, **k: {"file": f, "days": [1,2,3,4,5,6,7], "order": o, **k}
json.dump({"open":"09:00","close":"20:00","stopImage":"fundal.jpg",
  "default":[D("a.mp4",1), D("b.jpg",2,imageSeconds=5)],
  "parties":[{"date":"2026-12-05","start":"15:00","durationMinutes":60,"files":[{"file":"p1.mp4","order":1}]},
             {"date":"2026-12-05","start":"16:00","durationMinutes":30,"files":[{"file":"p2.mp4","order":1}]}]}, open(d+"/program.json","w"))
a = agent.Agent()
names = lambda: [os.path.basename(p) for p, _ in a.playlist]
def paused():
    last = None
    for l in open(T + "/run/fake-mpv.log"):
        c = json.loads(l)
        if c[0] == "set_property" and c[1] == "pause": last = c[2]
    return last
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
def ticks(t, n=3):
    at(t)
    for _ in range(n): a.tick()

print("--- in timpul programului")
ticks("2026-12-05 10:00"); ok(names() == ["a.mp4","b.jpg"] and a.player.running(), "10:00 ruleaza clipurile implicite")
a.command("stop"); ticks("2026-12-05 10:30"); ok(names() == ["fundal.jpg"] and a.manual == "stop", "stop -> poza de oprire; ramane asa dupa mai multe verificari (nu porneste singur)")
a.command("play"); ticks("2026-12-05 11:00"); ok(names() == ["a.mp4","b.jpg"] and a.manual is None, "play -> porneste clipurile implicite")
a.command("pause"); ticks("2026-12-05 11:30"); ok(a.manual == "pause" and paused() is True and names() == ["a.mp4","b.jpg"], "pause -> ramane in pauza, nu reporneste singur")
ticks("2026-12-05 15:00"); ok(a.key.startswith("party") and names() == ["p1.mp4"] and a.manual is None and paused() is False, "incepe petrecerea cat clipul era pe pauza -> porneste clipul de petrecere (nepauzat)")
a.command("stop"); ticks("2026-12-05 15:30"); ok(names() == ["fundal.jpg"] and a.manual == "stop", "stop in timpul petrecerii -> ramane oprit pana la play")
ticks("2026-12-05 16:00"); ok(names() == ["p2.mp4"] and a.manual is None, "se termina petrecerea 1 (clipul era stopat) -> porneste automat urmatorul clip de petrecere")
a.command("pause"); ticks("2026-12-05 16:15"); ok(a.manual == "pause", "pauza in timpul petrecerii 2")
ticks("2026-12-05 16:30"); ok(a.key == "default" and names() == ["a.mp4","b.jpg"] and a.manual is None and paused() is False, "se termina petrecerea (clipul era pe pauza) -> porneste automat clipul implicit, nepauzat")
a.command("stop"); ticks("2026-12-05 19:59", 2); ok(names() == ["fundal.jpg"], "19:59 stop activ")
ticks("2026-12-05 20:00"); ok(not a.player.running() and a.manual is None and a.key == "none", "20:00 sfarsitul programului -> playerul se inchide (si comanda manuala se anuleaza)")
print("--- dupa program: doar manual")
ticks("2026-12-05 20:30"); ok(not a.player.running(), "20:30 nu porneste nimic singur")
r = a.command("stop"); ok(r[0] is False and not a.player.running(), "stop cand nu ruleaza nimic -> 409, nu face nimic")
r = a.command("pause"); ok(r[0] is False, "pause cand nu ruleaza nimic -> 409")
a.command("play"); ticks("2026-12-05 21:00"); ok(a.player.running() and names() == ["a.mp4","b.jpg"], "play manual dupa program -> porneste clipurile implicite si ruleaza")
a.command("pause"); ticks("2026-12-05 22:00"); ok(a.player.running() and paused() is True and a.manual == "pause", "pause manual dupa program -> playerul ramane pornit, pe pauza")
ticks("2026-12-05 22:30"); ok(a.player.running() and paused() is True, "pauza dupa program ramane pe pauza si dupa alte verificari")
a.command("play"); ticks("2026-12-05 23:00"); ok(a.player.running() and paused() is False and a.manual == "play" and names() == ["a.mp4","b.jpg"], "play din pauza dupa program -> ruleaza mai departe, nu se opreste singur")
a.command("stop"); ticks("2026-12-06 00:30"); ok(names() == ["fundal.jpg"] and a.manual == "stop", "stop manual dupa program -> poza de oprire; programarea nu intervine (nici dupa miezul noptii)")
a.command("play"); ticks("2026-12-06 08:59"); ok(a.player.running() and names() == ["a.mp4","b.jpg"] and a.manual == "play", "play manual inainte de deschidere ramane pornit")
ticks("2026-12-06 09:00"); ok(a.key == "default" and a.manual is None and names() == ["a.mp4","b.jpg"], "09:00 deschidere -> programul preia (clipurile implicite)")
print("\n%d verificari picate" % len(bad)); [print("  -", m) for m in bad]
a.player.stop()
