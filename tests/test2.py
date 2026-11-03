import sys, os, json
sys.path.insert(0, "..")
import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
agent.cfg.update(cache_dir=T+"/cache", mpv_socket=T+"/run/mpv.sock", mpv_args=[])
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
prog = {"open":"00:00","close":"23:59","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1},{"file":"b.jpg","days":[1,2,3,4,5,6,7],"order":2,"imageSeconds":7}],"parties":[]}
json.dump(prog, open(T+"/cache/program.json","w"))
a = agent.Agent(); a.tick()
ok(a.player.running() and [os.path.basename(p) for p,_ in a.playlist]==["a.mp4","b.jpg"], "porneste cu cele 2 fisiere")
prog["default"] = prog["default"][:1]; json.dump(prog, open(T+"/cache/program.json","w")); a.tick()
ok([os.path.basename(p) for p,_ in a.playlist]==["a.mp4"], "program schimbat -> playlist reincarcat")
os.rename(T+"/cache/clips/a.mp4", T+"/cache/clips/a.bak"); a.tick()
ok(not a.player.running(), "clip lipsa -> nimic de rulat, mpv oprit")
os.rename(T+"/cache/clips/a.bak", T+"/cache/clips/a.mp4"); a.tick()
ok(a.player.running(), "clip revenit -> porneste din nou")
prog["close"]="00:01"; json.dump(prog, open(T+"/cache/program.json","w")); a.tick()
ok(not a.player.running(), "in afara orelor -> mpv oprit")
a.sync(); print("sync fara config: ok (a doar a avertizat)")
