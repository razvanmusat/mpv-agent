import sys, os, json
sys.path.insert(0, ".."); import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
agent.cfg.update(cache_dir=T+"/cache", mpv_socket=T+"/run/mpv.sock", mpv_args=[])
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
open(T+"/cache/clips/fundal.jpg","wb").write(b"x"); open(T+"/cache/clips/a.mp4","wb").write(b"x")
prog = {"open":"00:00","close":"23:59","stopImage":"fundal.jpg","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1}],"parties":[]}
json.dump(prog, open(T+"/cache/program.json","w"))
a = agent.Agent(); a.tick()
ok(os.path.basename(a.playlist[0][0])=="a.mp4", "ruleaza clipul")
print(a.command("stop")); base = lambda: [os.path.basename(p) for p,_ in a.playlist]
ok(base()==["fundal.jpg"] and a.player.running() and a.playlist[0][1]=="inf", "stop -> poza de fundal, durata inf, mpv ramane pornit")
a.tick(); ok(base()==["fundal.jpg"], "ramane poza la tick")
ok(a.command("pause")[0] is False and a.command("next")[0] is False, "pause/next respinse cat timp e oprit")
ok(a.command("play")[0] and base()==["a.mp4"], "play revine la clip")
open(T+"/run/fake-mpv.log"); log=open(T+"/run/fake-mpv.log").read(); ok('"image-display-duration=inf"' in log, "optiunea image-display-duration=inf trimisa")
del prog["stopImage"]; json.dump(prog, open(T+"/cache/program.json","w")); a.tick(); a.command("stop")
ok(not a.player.running(), "fara stopImage: stop opreste mpv ca inainte")
a.player.stop()
