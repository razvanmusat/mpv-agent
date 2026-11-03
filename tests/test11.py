import sys, os, json, shutil
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache11"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv11.sock", mpv_args=[])
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("a.mp4", "b.mp4", "fundal.jpg"): open(d + "/clips/" + n, "wb").write(b"x")
json.dump({"open":"09:00","close":"20:00","stopImage":"fundal.jpg",
  "default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},{"file":"b.mp4","days":[1,2,3,4,5,6,7],"order":2}]}, open(d+"/program.json","w"))
a = agent.Agent()
def log():
    return [json.loads(l) for l in open(T + "/run/fake-mpv.log")]
def last_pause():
    v = None
    for c in log():
        if c[0] == "set_property" and c[1] == "pause": v = c[2]
    return v
def n_next(): return sum(1 for c in log() if c[0] == "playlist-next")
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
at("2026-12-05 10:00"); a.tick(); a.tick()
a.command("pause"); ok(last_pause() is True and a.manual == "pause", "pauza activa")
n0 = n_next(); r = a.command("next")
ok(r == (True, "ok") and n_next() == n0 + 1, "next din pauza -> trimis playlist-next, raspuns ok")
ok(last_pause() is False and a.manual is None, "next din pauza -> iese din pauza (nu ramane pe pauza), manual=None in program")
at("2026-12-05 10:05"); a.tick(); a.tick(); ok(last_pause() is False and a.manual is None, "ramane pornit dupa tick-uri")
# next normal (nu din pauza) nu atinge pauza si starea
n1 = n_next(); a.command("next"); ok(n_next() == n1 + 1 and a.manual is None and last_pause() is False, "next fara pauza -> comportament neschimbat")
# next cand e stop -> 409 ca inainte
a.command("stop"); r = a.command("next"); ok(r == (False, "playerul e oprit, da play") and a.manual == "stop", "next cand e stop -> 409, neschimbat")
a.command("play")
# dupa program: next din pauza ramane sesiune manuala (nu opreste playerul)
at("2026-12-05 21:00"); a.tick(); ok(not a.player.running(), "dupa program: nimic nu ruleaza")
a.command("play"); a.tick(); a.command("pause"); a.tick(); ok(a.manual == "pause" and last_pause() is True, "dupa program: play + pause")
a.command("next"); a.tick(); a.tick()
ok(a.player.running() and last_pause() is False and a.manual == "play", "dupa program: next din pauza -> ruleaza mai departe, manual=play, playerul nu se opreste")
print("\n%d verificari picate" % len(bad)); [print("  -", m) for m in bad]
a.player.stop()
