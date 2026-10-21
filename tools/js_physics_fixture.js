/* Runs the browser simulator's physics for a scripted 3 days (no person behaviour, fixed actions) and prints each room's
   true values every 6 hours, to compare with the Python port. usage: TZ=Asia/Seoul node tools/js_physics_fixture.js <smarthome-sim.html> */
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8"), script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const S = new Function(script.slice(0, script.indexOf("/* ===== Storage")) + ";return { Simulator, SPEC };")();
const s = new S.Simulator(S.SPEC); s.variant = "3room-A"; s.whereRefusal = () => null;
const T0 = new Date(2026, 0, 15).getTime(); s.jumpTo(T0); s.phone.moveRoom("room1");
const out = [], ACT = require(process.argv[3] || "./physics_script.json");
let ai = 0;
for (let m = 1; m <= 3 * 1440; m++) {
  const t = T0 + m * 60000;
  while (ai < ACT.length && ACT[ai][0] <= m) { const a = ACT[ai++]; s.clock.setTo(T0 + a[0] * 60000 - 60000 + 1000);
    if (a[1] === "run") s.run(a[2], a[3], a[4], a[5] || [], "mobile_app"); else if (a[1] === "set") s.setValue(a[2], a[3], a[4], a[5]); else if (a[1] === "move") s.phone.moveRoom(a[2]); }
  s.clock.setTo(t); s.tick();
  if (m % 360 === 0) out.push([m, JSON.parse(JSON.stringify(s.house.env.rooms))]);
}
console.log(JSON.stringify(out));
