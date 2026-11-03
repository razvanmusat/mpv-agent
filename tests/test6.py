import sys, os, json, shutil
sys.path.insert(0, ".."); import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache6"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/vps")
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv6.sock", mpv_args=[], ssh_target="x@y", remote_program="program.json", remote_clips_dir=".")
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
a = agent.Agent()
def fake(remote, local):                      # "VPS" = folderul vps/
    src = d + "/vps/" + remote.lstrip("./")
    if not os.path.exists(src): raise RuntimeError("link_stat failed: No such file: " + remote)
    shutil.copy(src, local)
a.rsync = fake
prog = {"open":"00:00","close":"23:59","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},{"file":"b.jpg","days":[1,2,3,4,5,6,7],"order":2}]}
st = lambda: a.status()["last_sync"]

a.sync(); ok(st()["ok"] is False and "program.json" in st()["message"], "fara program.json pe VPS -> ok:false cu motiv: %s" % st()["message"][:50])
open(d+"/vps/program.json","w").write("{ stricat"); a.sync()
ok(st()["ok"] is False and "invalid" in st()["message"], "JSON stricat -> respins: %s" % st()["message"][:60])
ok(not os.path.exists(d+"/program.json"), "programul vechi/niciunul ramane neatins")
json.dump(prog, open(d+"/vps/program.json","w")); open(d+"/vps/a.mp4","w").write("x"); a.sync()
ok(st()["ok"] is False and st()["failed"]==["b.jpg"], "lipseste b.jpg pe VPS -> ok:false, failed=['b.jpg']")
ok(os.path.exists(d+"/program.json") and os.path.exists(d+"/clips/a.mp4"), "programul valid e aplicat, a.mp4 tras")
open(d+"/vps/b.jpg","w").write("x"); a.sync()
ok(st()["ok"] is True and st()["message"]=="ok" and st()["files"]==2 and st()["failed"]==[], "totul tras -> ok:true, files=2")
ok("time" in st() and a.status()["syncing"] is False, "time prezent, syncing=false")
a.player.stop()
print("TOATE OK")
