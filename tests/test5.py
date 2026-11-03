import sys, os, json, time, threading, http.client, subprocess
sys.path.insert(0, ".."); import agent
from datetime import datetime
T = os.getcwd(); real_path = os.environ["PATH"]
os.environ["PATH"] = T + "/bin:" + real_path
agent.cfg.update(cache_dir=T+"/cache", mpv_socket=T+"/run/mpv.sock", mpv_args=[], port_agent=18766)
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
logf = T + "/run/fake-mpv.log"
for f in (logf,):
    open(f, "w").close()
for n in ("a.mp4", "p.jpg", "q.PNG"): open(T+"/cache/clips/"+n, "wb").write(b"x")

# program de noapte
p = agent.parse_program({"open":"22:00","close":"06:00","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1}]})
D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")
ok(agent.compute_target(p, D("2026-12-02 23:30"))[0]=="default", "noapte: 23:30 ruleaza")
ok(agent.compute_target(p, D("2026-12-03 03:00"))[0]=="default", "noapte: 03:00 ruleaza")
ok(agent.compute_target(p, D("2026-12-03 12:00"))[0]=="none", "noapte: 12:00 nu ruleaza")
ok(agent.compute_target(agent.parse_program({"open":"09:00","close":"20:00","default":[]}), D("2026-12-03 12:00"))[0]=="default", "zi: 12:00 ruleaza")

# poze fara imageSeconds -> 10 s; PNG cu extensie mare recunoscut; video fara durata
prog = {"open":"00:00","close":"23:59","default":[
  {"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},
  {"file":"p.jpg","days":[1,2,3,4,5,6,7],"order":2},
  {"file":"q.PNG","days":[1,2,3,4,5,6,7],"order":3,"imageSeconds":4}],"parties":[]}
json.dump(prog, open(T+"/cache/program.json","w"))
a = agent.Agent(); a.tick()
log = open(logf).read().splitlines()
loads = [json.loads(l) for l in log if '"loadfile"' in l]
ok(len(loads)==3 and len(loads[0])==3, "video: loadfile fara optiune de durata")
ok(loads[1][-1]=="image-display-duration=10", "jpg fara imageSeconds -> 10s: %s" % loads[1][-1])
ok(loads[2][-1]=="image-display-duration=4", "png cu imageSeconds=4 -> 4s")

# play cand ruleaza deja exact asta: nu reincarca
n0 = len([l for l in open(logf) if '"loadfile"' in l])
ok(a.command("play")[0], "play raspunde ok")
n1 = len([l for l in open(logf) if '"loadfile"' in l])
ok(n0 == n1, "play pe ce ruleaza deja nu reia playlistul (loadfile: %d -> %d)" % (n0, n1))

# HTTP robust
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 18766), agent.make_handler(a)); threading.Thread(target=srv.serve_forever, daemon=True).start()
def raw(body, clen=None, path="/command"):
    c = http.client.HTTPConnection("127.0.0.1", 18766, timeout=4)
    c.putrequest("POST", path); c.putheader("Content-Length", str(len(body) if clen is None else clen)); c.endheaders(); c.send(body)
    r = c.getresponse(); return r.status
ok(raw(b'{"command":["pause"]}')==400, "comanda ca lista -> 400 (nu exceptie)")
ok(raw(b'{"command":{"x":1}}')==400, "comanda ca obiect -> 400")
ok(raw(b'', clen=-1)==400, "Content-Length negativ -> 400, nu se blocheaza")
ok(raw(b'not json')==400, "corp non-json -> 400")
ok(raw(b'{"command":"pause"}')==200, "pause valid -> 200")
ok(a.status()["paused"] is True, "status raspunde fara sa blocheze")
a.command("play")

# rsync: timeout -> RuntimeError (nu opreste tot sync-ul)
orig = subprocess.run
def boom(*a_, **k): raise subprocess.TimeoutExpired("rsync", 1)
subprocess.run = boom
try: a.rsync("x", "y"); ok(False, "ar fi trebuit sa ridice")
except RuntimeError as e: ok("15 minute" in str(e), "rsync timeout -> RuntimeError")
subprocess.run = orig

# mpv nu porneste: se reincearca la fiecare tick, fara sa blocheze
a.player.stop(); a.playlist = []
os.environ["PATH"] = T + "/binfail:" + real_path
open(T+"/binfail/attempts.log","w").close()
agent.cfg["mpv_socket"] = T + "/run/inexistent/mpv.sock"
b = agent.Agent(); b.tick(); b.tick(); b.tick()
att = len(open(T+"/binfail/attempts.log").read().split())
ok(att >= 3 and b.playlist is None, "mpv defect: reincearca la fiecare tick (%d incercari), nu considera aplicat" % att)
print("TOATE OK")
