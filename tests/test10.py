import sys, os, json, shutil
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache10"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv10.sock", mpv_args=[])
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("a.mp4", "fundal.jpg"): open(d + "/clips/" + n, "wb").write(b"x")     # p1.mp4 NU exista local
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
def prog(days, stop="fundal.jpg"):
    p = {"open":"09:00","close":"20:00","default":[{"file":"a.mp4","days":days,"order":1}],
         "parties":[{"date":"2026-12-05","start":"15:00","durationMinutes":60,"files":[{"file":"p1.mp4","order":1}]}]}
    if stop: p["stopImage"] = stop
    json.dump(p, open(d + "/program.json", "w"))
a = agent.Agent(); names = lambda: [os.path.basename(p) for p, _ in a.playlist]
def ticks(t, n=3):
    at(t)
    for _ in range(n): a.tick()
# 2026-12-05 = sambata (6). Clipul implicit e doar luni (1) -> azi nu are clipuri implicite
prog([1])
ticks("2026-12-05 10:00"); ok(a.player.running() and names() == ["fundal.jpg"], "in program, azi fara clip implicit -> poza de oprire")
ticks("2026-12-05 12:00"); ok(names() == ["fundal.jpg"], "ramane poza pe tot parcursul")
r = a.command("play"); ok(r == (False, "nu exista clipuri de rulat") and names() == ["fundal.jpg"], "play fara clipuri de rulat -> 409, poza ramane")
ticks("2026-12-05 15:00"); ok(a.key.startswith("party") and names() == ["fundal.jpg"], "petrecere cu fisierele lipsa local, in program -> poza de oprire (nu ecran gol)")
open(d + "/clips/p1.mp4", "wb").write(b"x"); ticks("2026-12-05 15:10")
ok(names() == ["p1.mp4"], "cand apare clipul de petrecere (sync) -> il inlocuieste pe poza")
ticks("2026-12-05 16:00"); ok(a.key == "default" and names() == ["fundal.jpg"], "se termina petrecerea, fara clip implicit azi -> poza de oprire")
prog([6]); ticks("2026-12-05 16:05"); ok(names() == ["a.mp4"], "apare clip implicit pentru azi -> inlocuieste poza")
prog([1]); ticks("2026-12-05 16:10"); ok(names() == ["fundal.jpg"], "clipul implicit dispare din program -> revine poza")
ticks("2026-12-05 20:00"); ok(not a.player.running() and a.key == "none", "20:00 sfarsitul programului -> playerul se inchide (poza dispare si ea)")
ticks("2026-12-05 21:00"); ok(not a.player.running(), "dupa program nu apare poza singura")
ticks("2026-12-06 09:00"); ok(a.player.running() and names() == ["fundal.jpg"], "09:00 deschidere, fara clip implicit duminica -> poza de oprire")
prog([1], stop=None); ticks("2026-12-06 09:05"); ok(not a.player.running(), "fara stopImage in program -> nimic nu ruleaza (ca inainte)")
prog([1]); ticks("2026-12-06 09:10"); a.command("pause"); ticks("2026-12-06 09:20")
ok(a.player.running() and a.manual == "pause", "pause pe poza de rezerva -> ramane pornit, pe pauza")
a.command("play"); ticks("2026-12-06 09:30"); ok(a.player.running() and names() == ["fundal.jpg"] and a.manual is None, "play din pauza pe poza -> continua")
print("\n%d verificari picate" % len(bad)); [print("  -", m) for m in bad]
a.player.stop()
