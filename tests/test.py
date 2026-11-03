import sys, os, json, time, urllib.request, threading
sys.path.insert(0, "..")
import agent
from datetime import datetime
T = os.getcwd()
os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
agent.cfg.update(cache_dir=T+"/cache", mpv_socket=T+"/run/mpv.sock", mpv_args=[], port_agent=18765)
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))

# --- reguli de redare (pur logica)
raw = {"open":"09:00","close":"20:00",
 "default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},{"file":"b.jpg","days":[1,2,3],"order":2,"imageSeconds":10}],
 "parties":[{"date":"2026-12-05","start":"15:00","durationMinutes":150,"files":[{"file":"p2.jpg","order":2,"imageSeconds":8},{"file":"p1.mp4","order":1}]}]}
p = agent.parse_program(raw)
D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")
k, it = agent.compute_target(p, D("2026-12-02 10:00"))  # miercuri 3 -> a+b
ok(k=="default" and [i["file"] for i in it]==["a.mp4","b.jpg"], "luni-miercuri: a,b")
k, it = agent.compute_target(p, D("2026-12-03 10:00"))  # joi (4) -> doar a
ok([i["file"] for i in it]==["a.mp4"], "joi: doar a.mp4 (b are zilele 1-3)")
k, it = agent.compute_target(p, D("2026-12-05 16:00"))
ok(k.startswith("party") and [i["file"] for i in it]==["p1.mp4","p2.jpg"], "petrecere activa, ordonata")
k, it = agent.compute_target(p, D("2026-12-05 17:30"))  # 15:00+150min = 17:30 exact -> terminat
ok(k=="default", "la ora de final petrecerea s-a terminat")
k, it = agent.compute_target(p, D("2026-12-05 20:00"))
ok(k=="none", "la close nu ruleaza nimic")
k, it = agent.compute_target(p, D("2026-12-05 08:59"))
ok(k=="none", "inainte de open nu ruleaza nimic")
for bad in [{"file":"../etc/passwd","days":[1],"order":1}, {"file":"x.mp4","days":[9],"order":1}]:
    try: agent.parse_program({**raw, "default":[bad]}); ok(False, "ar fi trebuit respins "+str(bad))
    except ValueError: ok(True, "respins: "+str(bad))

# --- agent + HTTP, cu mpv fals
now = datetime.now()
prog = {"open":"00:00","close":"23:59","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},
        {"file":"b.jpg","days":[1,2,3,4,5,6,7],"order":2,"imageSeconds":7}],"parties":[]}
json.dump(prog, open(T+"/cache/program.json","w"))
for n in ("a.mp4","b.jpg"): open(T+"/cache/clips/"+n,"wb").write(b"x")
a = agent.Agent()
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 18765), agent.make_handler(a)); threading.Thread(target=srv.serve_forever, daemon=True).start()
def call(method, path, body=None):
    r = urllib.request.Request("http://127.0.0.1:18765"+path, method=method, data=json.dumps(body).encode() if body else None)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
a.tick(); time.sleep(0.3)
st = call("GET","/status")[1]
ok(st["mpv_running"] and st["target"]=="default" and st["playing"]=="a.mp4", "tick porneste mpv cu playlist default: %s" % st["playing"])
log = open(T+"/run/fake-mpv.log").read()
ok('"image-display-duration=7"' in log, "imageSeconds trimis ca optiune per fisier la loadfile")
ok(call("POST","/command",{"command":"pause"})[0]==200 and call("GET","/status")[1]["paused"] is True, "pause")
a.tick(); ok(call("GET","/status")[1]["paused"] is True, "pauza ramane la tick")
ok(call("POST","/command",{"command":"play"})[0]==200 and call("GET","/status")[1]["paused"] is False, "play dupa pauza")
ok(call("POST","/command",{"command":"stop"})[0]==200 and not call("GET","/status")[1]["mpv_running"], "stop opreste mpv")
a.tick(); ok(not call("GET","/status")[1]["mpv_running"], "stop ramane la tick (aceeasi tinta)")
ok(call("POST","/command",{"command":"play"})[0]==200 and call("GET","/status")[1]["mpv_running"], "play dupa stop reporneste")
ok(call("POST","/command",{"command":"next"})[0]==200, "next")
ok(call("POST","/command",{"command":"hack"})[0]==400, "comanda necunoscuta respinsa")
ok(call("POST","/command",{"foo":1})[0]==400, "corp invalid respins")
ok(call("GET","/nimic")[0]==404, "404")
# schimbare de tinta anuleaza comanda manuala
call("POST","/command",{"command":"stop"})
prog["default"] = [{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1}]; json.dump(prog, open(T+"/cache/program.json","w"))
a.tick(); ok(not call("GET","/status")[1]["mpv_running"], "acelasi key 'default' -> stop se pastreaza chiar daca s-a schimbat continutul")
# in afara orelor: nimic, apoi play manual = default de azi
prog["open"]="00:00"; prog["close"]="00:01"; json.dump(prog, open(T+"/cache/program.json","w"))
a.tick(); ok(a.key=="none" and not a.player.running(), "in afara orelor: nimic ruleaza (tinta s-a schimbat, manualul anulat)")
ok(call("POST","/command",{"command":"play"})[0]==200 and a.player.running(), "play manual in afara orelor porneste default")
a.tick(); ok(a.player.running(), "play manual ramane la tick")
a.player.stop()
print(call("GET","/status")[1])
print("TOATE OK")
