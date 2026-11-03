import sys, os, json
sys.path.insert(0, ".."); import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache8"; os.makedirs(d + "/clips", exist_ok=True)
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv8.sock", mpv_args=[])
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
for n in ("a.mp4", "fundal.jpg"): open(d+"/clips/"+n, "wb").write(b"x")
json.dump({"open":"00:00","close":"23:59","stopImage":"fundal.jpg","default":[{"file":"a.mp4","days":[1,2,3,4,5,6,7],"order":1}]}, open(d+"/program.json","w"))
a = agent.Agent()
# mpv nu ruleaza (niciun tick inca)
before = (a.manual, list(a.playlist), a.player.running())
r = a.command("stop")
ok(r == (False, "nu ruleaza nimic"), "stop fara mpv -> (False, 'nu ruleaza nimic'): %s" % (r,))
ok((a.manual, list(a.playlist), a.player.running()) == before and a.manual is None, "stare manuala neschimbata, fara poza de oprire, mpv tot oprit")
# mpv ruleaza: comportament neschimbat
a.tick(); ok(a.player.running(), "tick porneste mpv")
r = a.command("stop"); ok(r == (True, "ok") and a.manual == "stop" and os.path.basename(a.playlist[0][0]) == "fundal.jpg", "stop cu mpv pornit -> ok, manual=stop, poza de oprire")
r = a.command("stop"); ok(r == (True, "ok") and a.manual == "stop", "stop repetat, cu poza afisata (mpv ruleaza) -> ramane ok ca inainte")
a.command("play"); a.player.stop(); a.manual = None; a.playlist = []
r = a.command("stop"); ok(r == (False, "nu ruleaza nimic") and a.manual is None, "stop dupa ce mpv a fost oprit -> 409, manual neschimbat")
print("TOATE OK")
