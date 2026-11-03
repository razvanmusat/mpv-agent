import sys, os, json, shutil
sys.path.insert(0, ".."); import agent
from datetime import datetime as RealDT
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache14"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips"); os.makedirs(d + "/vps")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv14.sock", mpv_args=[], port_agent=18773, ssh_target="x@y", remote_program="program.json", remote_clips_dir="")
class FDT(RealDT):
    val = None
    @classmethod
    def now(cls, tz=None): return cls.val
agent.datetime = FDT
at = lambda s: setattr(FDT, "val", RealDT.strptime(s, "%Y-%m-%d %H:%M"))
for n in ("f1.jpg", "f2.png", "f3.jpg", "a.mp4"): open(d + "/clips/" + n, "wb").write(b"x")
def write(**extra):
    p = {"open":"09:00","close":"20:00","default":[],"parties":[]}; p.update(extra)
    json.dump(p, open(d+"/program.json","w"))
a = agent.Agent(); names = lambda: [os.path.basename(p) for p, _ in a.playlist]; secs = lambda: [s for _, s in a.playlist]
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
at("2026-12-07 10:00")
write(stopImages=[{"file":"f1.jpg","imageSeconds":5},{"file":"f2.png"},{"file":"f3.jpg","imageSeconds":30}])
a.tick()
ok(names() == ["f1.jpg","f2.png","f3.jpg"] and secs() == [5, agent.DEFAULT_IMAGE_SECONDS, 30], "mai multe poze de fundal: ordinea si secundele: %s %s" % (names(), secs()))
a.command("stop")
ok(names() == ["f1.jpg","f2.png","f3.jpg"], "dupa Stop se arata aceeasi lista de poze: %s" % names())
write(stopImages=[{"file":"f2.png","imageSeconds":7}])
a.tick()
ok(names() == ["f2.png"] and secs() == ["inf"], "o singura poza ramane permanent: %s %s" % (names(), secs()))
write(stopImage="f1.jpg")
a.tick()
ok(names() == ["f1.jpg"], "forma veche stopImage merge in continuare: %s" % names())
write(stopImages=[{"file":"f1.jpg","imageSeconds":-1}])
try:
    agent.parse_program(json.load(open(d+"/program.json"))); ok(False, "imageSeconds negativ trebuie respins")
except ValueError: ok(True, "imageSeconds negativ respins")
ok(agent.referenced_files(agent.parse_program({"open":"09:00","close":"20:00","stopImages":[{"file":"f1.jpg"},{"file":"f3.jpg"}]})) >= {"f1.jpg","f3.jpg"}, "pozele de fundal sunt trase la sync")
a.player.close() if hasattr(a.player, "close") else None
print("GATA" if not bad else "ESUATE: %s" % bad); sys.exit(1 if bad else 0)
