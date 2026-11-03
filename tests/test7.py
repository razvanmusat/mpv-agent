import sys, os, json, shutil, time, threading, http.client
sys.path.insert(0, ".."); import agent
T = os.getcwd(); d = T + "/cache7"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/vps")
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv7.sock", mpv_args=[], ssh_target="x@y", remote_program="program.json", remote_clips_dir=".")
a = agent.Agent(); a.tick = lambda: None
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 18770), agent.make_handler(a)); threading.Thread(target=srv.serve_forever, daemon=True).start()
def req(m, p):
    c = http.client.HTTPConnection("127.0.0.1", 18770, timeout=5); c.request(m, p); r = c.getresponse(); b = json.loads(r.read()); return r.status, b
def fake(remote, local):
    src = d + "/vps/" + remote.lstrip("./")
    if not os.path.exists(src): raise agent.RuntimeError if False else RuntimeError("link_stat failed: " + remote)
    shutil.copy(src, local)
a.rsync = fake
prog = {"open":"00:00","close":"23:59","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},{"file":"b.jpg","days":[1,2,3,4,5,6,7],"order":2}]}
show = lambda t: print("%-34s %s" % (t, json.dumps({k: req("GET","/status")[1][k] for k in ("syncing","last_sync")})))
def keys(): s = req("GET","/status")[1]; return s
print("== campurile /status (complet), inainte de primul sync:"); print(json.dumps(keys(), indent=1))
print("\n== 2. last_sync dupa fiecare caz")
json.dump(prog, open(d+"/vps/program.json","w")); open(d+"/vps/a.mp4","w").write("x"); open(d+"/vps/b.jpg","w").write("x")
a.sync(); show("a) reusit")
open(d+"/vps/program.json","w").write("{ stricat"); a.sync(); show("b) program invalid")
json.dump(prog, open(d+"/vps/program.json","w")); os.unlink(d+"/vps/b.jpg"); a.sync(); show("c) un fisier netras")
open(d+"/vps/b.jpg","w").write("x")
def boom(): raise RuntimeError("tick a esuat")
a.tick = boom; a.sync(); show("d) exceptie in self.tick()")
a.tick = lambda: None
os.makedirs(d + "/clips/subdir"); a.sync(); show("e) alta exceptie (director in clips/)")
os.rmdir(d + "/clips/subdir")
a.rsync = lambda r, l: (_ for _ in ()).throw(RuntimeError("fara retea")); a.sync(); show("e2) rsync program esueaza")
print("\n== 3/4. syncing si last_sync.time in timp (sync_once simulat de 1.2 s, doua POST /sync consecutive)")
runs = []
def slow():
    runs.append(time.time()); time.sleep(1.2); return {"ok": True, "message": "ok", "failed": [], "files": 2}
a.sync_once = slow; a.last_sync = {"ok": True, "message": "ok", "failed": [], "files": 2, "time": "VECHI"}
t0 = time.time(); r1 = req("POST","/sync"); s_after1 = keys(); r2 = req("POST","/sync"); s_after2 = keys()
print("POST1 ->", r1, "| imediat dupa: syncing=%s time=%s" % (s_after1["syncing"], s_after1["last_sync"]["time"]))
print("POST2 ->", r2, "| imediat dupa: syncing=%s time=%s" % (s_after2["syncing"], s_after2["last_sync"]["time"]))
last = None
while time.time() - t0 < 4.2:
    s = keys(); cur = (s["syncing"], s["last_sync"]["time"])
    if cur != last: print("  t=%.2fs syncing=%-5s last_sync.time=%s" % (time.time()-t0, cur[0], cur[1])); last = cur
    time.sleep(0.03)
print("rulari sync_once:", len(runs), "(start la t=%s)" % [round(x - t0, 2) for x in runs])
print("\n== 3. syncing imediat dupa 202, 30 incercari")
a.sync_once = lambda: (time.sleep(0.3), {"ok": True, "message": "ok", "failed": [], "files": 0})[1]
fals = 0
for _ in range(30):
    req("POST","/sync"); fals += 0 if keys()["syncing"] else 1; time.sleep(0.45)
print("syncing=false imediat dupa 202 in %d din 30 de incercari" % fals)
