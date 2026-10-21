/* writes outdoorAt() for a set of times, from the browser simulator's script, to compare with the Python port.
   usage: TZ=Asia/Seoul node tools/js_outdoor_fixture.js <smarthome-sim.html> [count] [stepMinutes] > fixture.json */
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8"), script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const S = new Function(script.slice(0, script.indexOf("/* ===== Storage")) + ";return { outdoorAt };")();
const out = [];
const T0 = new Date(2026, 0, 1).getTime();
const N = +(process.argv[3] || 600), STEP = +(process.argv[4] || 877.3);
for (let i = 0; i < N; i++) { const t = T0 + Math.floor(i * STEP) * 60000; out.push([t, S.outdoorAt(new Date(t))]); }
console.log(JSON.stringify(out));
