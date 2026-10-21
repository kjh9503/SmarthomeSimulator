#!/usr/bin/env node
/* Agent runner: drives one simulated person through the smart-home + phone simulator for N days,
   following an agent profile (profiles/<personaId>.json), and writes the home log and the phone log.

   usage: node tools/js/run_agent.js --profile profiles/063.json [--sim browser/smarthome-sim.html]
                            [--out out/063] [--days 365] [--seed 63] [--trace] [--home-log]

   Outputs (in --out):
     home_log.jsonl    only with --home-log: the home lines alone (they are in the phone log as SMARTTHINGS copies)
     phone_log.jsonl   every phone event (event-formats v3), including the SMARTTHINGS copies of home lines
     summary.json      counts per behaviour and per check, for checking the run (not training data)
     trace.jsonl       only with --trace: one line per behaviour decision with its step results
*/
process.env.TZ = "Asia/Seoul"; /* must be set before the first Date is made */
const fs = require("fs"), path = require("path");

/* ---------------- arguments ---------------- */
const argv = process.argv.slice(2), opt = {};
for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) { const k = argv[i].slice(2); opt[k] = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true; }
if (!opt.profile) { console.error("usage: node run_agent.js --profile <profile.json> [--sim <smarthome-sim.html>] [--out <dir>] [--days N] [--seed N] [--trace]"); process.exit(2); }
const HERE = __dirname;
const profile = JSON.parse(fs.readFileSync(opt.profile, "utf8"));
const simPath = opt.sim || path.join(HERE, "..", "..", "browser", "smarthome-sim.html");
const outDir = opt.out || path.join(HERE, "out", profile.personaId);
const DAYS = +(opt.days || profile.simulation.days), SEED = +(opt.seed ?? profile.simulation.seed);
const OFF = JSON.parse(fs.readFileSync(opt.offRules || path.join(HERE, "off_rules.json"), "utf8"));
let VOCAB = null; try { VOCAB = JSON.parse(fs.readFileSync(path.join(HERE, "..", "..", "pipeline", "vocabulary.json"), "utf8")); } catch (e) { /* optional */ }
fs.mkdirSync(outDir, { recursive: true });

/* ---------------- random numbers: one stream for the simulator, one for the person ---------------- */
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
Math.random = mulberry32(SEED * 7919 + 1);        /* the simulator's own noise (sensor jitter, steps, heart rate) */
const rnd = mulberry32(SEED * 104729 + 7);         /* the person's choices */
const uni = (a, b) => a + (b - a) * rnd();
const chance = p => rnd() < p;
function num(x) { return x && typeof x === "object" && "min" in x ? uni(x.min, x.max) : +x; }
function pickWeighted(opts, w) { if (!w) return opts[Math.floor(rnd() * opts.length)]; const s = w.reduce((a, b) => a + b, 0); let r = rnd() * s; for (let i = 0; i < opts.length; i++) { r -= w[i]; if (r <= 0) return opts[i]; } return opts[opts.length - 1]; }
function resolve(v) { /* {"choice":[..],"weights":[..]} -> one option, recursively */
  if (Array.isArray(v)) return v.map(resolve);
  if (v && typeof v === "object") {
    if (Array.isArray(v.choice) && Object.keys(v).every(k => k === "choice" || k === "weights")) return resolve(pickWeighted(v.choice, v.weights));
    const o = {}; for (const [k, x] of Object.entries(v)) o[k] = resolve(x); return o;
  }
  return v;
}

/* ---------------- load the simulator (the page's script up to the storage / UI part) ---------------- */
const html = fs.readFileSync(simPath, "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const core = script.slice(0, script.indexOf("/* ===== Storage"));
const SIM = new Function(core + "\n;return { Simulator, SPEC, PLACES, outdoorAt, APPS, ROOM_PROFILES, ST_ALERTS };")();
const { Simulator, SPEC, PLACES, outdoorAt, APPS, ST_ALERTS } = SIM;

/* ---------------- set up the world ---------------- */
const sim = new Simulator(SPEC);
sim.variant = profile.variant;
const phone = sim.phone, S = phone.s;
const [y0, m0, d0] = profile.simulation.startDate.split("-").map(Number);
const T0 = new Date(y0, m0 - 1, d0).getTime(), MIN = 60000, DAY = 86400000;
const TEND = new Date(y0, m0 - 1, d0 + DAYS).getTime();
sim.jumpTo(T0);
const roles = profile.roomRoles || {};
const realRoom = r => roles[r] || r;
const devId = ref => { const i = ref.lastIndexOf("."); return `${realRoom(ref.slice(0, i))}.${ref.slice(i + 1)}`; };
const st = profile.start || { place: "home" };
if (st.place !== "home") phone.teleport(st.place);
else if (st.room) phone.moveRoom(realRoom(st.room));
if (st.battery != null) S.battery = st.battery;
if (st.asleep) { S.asleep = true; S.sleepStart = T0; S.screenOn = false; }
/* apps the profile uses that are not installed: present from the start (no install event) */
for (const pkg of new Set(JSON.stringify(profile).match(/"(?:com|us|net|org|kr|jp)\.[a-z0-9_.]+"/gi) || [])) {
  const p = pkg.slice(1, -1); if (S.installed.includes(p)) continue;
  const ex = VOCAB && VOCAB.extraApps && VOCAB.extraApps[p];
  if (ex || (VOCAB && VOCAB.apps && VOCAB.apps[p])) { S.installed.push(p); APPS[p] ||= { label: (ex && (ex.label || ex)) || p, uid: 10200 + S.installed.length, mbPerMin: 1 }; }
}

/* ---------------- output: write finished lines, keep memory small ---------------- */
const homeOut = opt["home-log"] ? fs.openSync(path.join(outDir, "home_log.jsonl"), "w") : null; /* the home lines also reach the phone log as SMARTTHINGS copies */
const phoneOut = fs.openSync(path.join(outDir, "phone_log.jsonl"), "w");
const traceOut = opt.trace ? fs.openSync(path.join(outDir, "trace.jsonl"), "w") : null;
let nHome = 0, nPhone = 0;
function writeOut(cutoff) { /* lines older than cutoff are final (a day's sensor lines are written when the day closes) */
  const E = sim.log.entries; let i = 0; while (i < E.length && Date.parse(E[i].time) < cutoff) i++;
  if (i) { if (homeOut) fs.writeSync(homeOut, E.slice(0, i).map(e => JSON.stringify(e)).join("\n") + "\n"); nHome += i; E.splice(0, i); }
  const P = phone.events; let j = 0; while (j < P.length && P[j].timestamp < cutoff) j++;
  if (j) { fs.writeSync(phoneOut, P.slice(0, j).map(e => JSON.stringify(e)).join("\n") + "\n"); nPhone += j; P.splice(0, j); }
}
const trace = o => { if (traceOut) fs.writeSync(traceOut, JSON.stringify(o) + "\n"); };
const iso = t => { const d = new Date(t), p = n => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}+09:00`; };

/* ---------------- what happens: hooks on the logs, and the person's own movement ---------------- */
const happenings = [];            /* new home lines, phone events, person and weather changes, for event triggers */
const recentPhone = [];           /* phone events of the last 24 h, for phone_event / health conditions */
const recentWeather = [];         /* [t, weather] per minute, last 24 h */
const actionHistory = [];         /* [t, do, args] the person's own actions, last 7 days */
const addLog = sim.log.add.bind(sim.log);
sim.log.add = e => { addLog(e); if (Date.parse(e.time) >= clockMs() - 2 * MIN) happenings.push({ src: "home", e }); };
const emit = phone.emit.bind(phone);
phone.emit = (...a) => { const e = emit(...a); recentPhone.push(e); happenings.push({ src: "phone", e }); return e; };
/* SMARTTHINGS copies of home lines go straight into the phone's list (not through emit): show them to the triggers too */
const copyHome = phone.copyHome.bind(phone);
phone.copyHome = entries => {
  copyHome(entries);
  for (const e of entries) {
    if (Date.parse(e.time) < clockMs() - 2 * MIN) continue; /* a day's sensor lines written when the day closes */
    const c = phone.toSmartThings(e); recentPhone.push(c); happenings.push({ src: "phone", e: c });
    for (const a of ST_ALERTS) if ((!a.device || a.device === e.device) && a.attr === e.attribute && a.when(e.value, e.previousValue)) {
      const al = phone.toAlert(e, a); recentPhone.push(al); happenings.push({ src: "phone", e: al });
    }
  }
};
let prevPerson = snapPerson();
function snapPerson() { return { place: S.place, trip: S.trip ? { from: S.trip.from, to: S.trip.to } : null, room: S.room, asleep: S.asleep }; }
function personChanges() {
  const a = prevPerson, b = snapPerson(); prevPerson = b;
  if (!a.trip && b.trip) happenings.push({ src: "person", what: "depart", place: b.trip.from });
  if (a.trip && !b.trip) happenings.push({ src: "person", what: "arrive", place: b.place });
  if (b.room && b.room !== a.room) happenings.push({ src: "person", what: "enter_room", room: b.room, place: "home" });
  if (a.asleep && !b.asleep) happenings.push({ src: "person", what: "wake", place: b.place });
  if (!a.asleep && b.asleep) happenings.push({ src: "person", what: "fall_asleep", place: b.place });
}

/* ---------------- time inside the minute: actions get increasing seconds ---------------- */
let minuteMs = T0, secInMinute = 0;
const clockMs = () => sim.clock.now().getTime();
function advanceSeconds() { secInMinute = Math.min(59, secInMinute + 3 + Math.floor(rnd() * 13)); sim.clock.setTo(minuteMs + secInMinute * 1000); }

/* ---------------- helpers on dates ---------------- */
const hhmm = s => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
const dayStart = t => { const d = new Date(t); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
const dayKey = t => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const minuteOfDay = t => { const d = new Date(t); return d.getHours() * 60 + d.getMinutes(); };
const DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
function dayOk(days, t) { if (!days || days === "all") return true; const w = DOW[new Date(t).getDay()]; if (days === "weekdays") return !["sat", "sun"].includes(w); if (days === "weekends") return ["sat", "sun"].includes(w); return days.includes(w); }
const monthOk = (months, t) => !months || months.includes(new Date(t).getMonth() + 1);
/* the day a time window belongs to (a window past midnight belongs to the day it starts), or null when t is outside it */
function windowDay(win, t) {
  const f = hhmm(win.from), to = hhmm(win.to), m = minuteOfDay(t), d0 = dayStart(t);
  if (f <= to) return m >= f && m <= to ? d0 : null;
  if (m >= f) return d0; if (m <= to) return dayStart(d0 - 12 * 3600000); return null;
}
function inTime(win, t) { return windowDay(win, t) != null; }

/* ---------------- conditions ---------------- */
function cmp(a, op, b) {
  switch (op) {
    case "==": return a === b || (a != null && b != null && String(a) === String(b));
    case "!=": return !(a === b || (a != null && b != null && String(a) === String(b)));
    case "<": return a < b; case "<=": return a <= b; case ">": return a > b; case ">=": return a >= b;
    case "in": return Array.isArray(b) && b.includes(a);
    case "not_in": return Array.isArray(b) && !b.includes(a);
    case "contains": return Array.isArray(a) ? a.includes(b) : String(a ?? "").includes(String(b));
  }
  return false;
}
function deviceValue(ref, cap, attr) {
  const id = devId(ref), d = sim.house.device(id); if (!d) return undefined;
  /* brightness is seen with the eyes: the room's actual light level; every other value is what the device / app shows */
  if (d.type === "light_sensor" && attr === "illuminance") return sim.house.env.rooms[d.roomId].illuminance;
  return d.get(cap, attr);
}
function phoneField(f) {
  switch (f) {
    case "screenOn": return S.screenOn; case "charging": return S.charging; case "battery": return Math.round(S.battery);
    case "activity": return S.activity; case "asleep": return S.asleep; case "media.state": return S.media ? S.media.state : "STOPPED";
    case "bluetooth": return S.bt.slice(); case "wifi": return S.wifi; case "foregroundApp": return S.foreground;
  }
}
function calendarCond(c, t) {
  const evs = Object.values(S.calendar).filter(e => String(e.title).toLowerCase().includes(c.titleContains.toLowerCase()));
  const ds = dayStart(t), de = ds + DAY;
  switch (c.relation) {
    case "starts_within": return evs.some(e => e.begin > t && e.begin <= t + (c.minutes || 0) * MIN);
    case "ongoing": return evs.some(e => e.begin <= t && t < e.end);
    case "today": return evs.some(e => e.begin >= ds && e.begin < de);
    case "none_today": return !evs.some(e => e.begin >= ds && e.begin < de);
    case "starts_before": return evs.some(e => e.begin >= ds && e.begin < de && minuteOfDay(e.begin) <= hhmm(c.time));
  }
  return false;
}
function matchPhoneEvent(e, c) {
  if (c.type && e.type !== c.type) return false;
  if (c.eventSource && e.source !== c.eventSource) return false;
  if (c.action && (e.payload || {}).action !== c.action) return false;
  if (c.category && ((e.payload || {}).category ?? ((e.payload || {}).notification || {}).category) !== c.category) return false; /* SMARTTHINGS alerts keep it in payload.notification */
  if (c.textContains && !String(e.text || "").toLowerCase().includes(c.textContains.toLowerCase())) return false;
  if (c.titleContains && !String(e.title || "").toLowerCase().includes(c.titleContains.toLowerCase())) return false;
  if (c.field && !cmp((e.payload || {})[c.field], c.op, c.value)) return false;
  return true;
}
function subset(a, b) { /* every key of a equals b's */
  if (a && typeof a === "object" && !Array.isArray(a)) return b && typeof b === "object" && Object.entries(a).every(([k, v]) => subset(v, b[k]));
  return JSON.stringify(a) === JSON.stringify(b);
}
function cond(c, t) {
  switch (c.kind) {
    case "time": return inTime(c.window, t);
    case "day": return dayOk(c.days, t);
    case "month": return monthOk(c.months, t);
    case "place": { const ps = Array.isArray(c.place) ? c.place : [c.place];
      if (c.op === "is_not") return !ps.includes(S.place) || !!S.trip;
      return ps.includes(S.place) && !S.trip; }
    case "room": return S.place === "home" && S.room === realRoom(c.room);
    case "device": return cmp(deviceValue(c.device, c.capability, c.attribute), c.op, c.value);
    case "weather": {
      if (c.withinMinutes) return recentWeather.some(([wt, w]) => wt >= t - c.withinMinutes * MIN && cmp(w, c.op, c.value));
      return cmp(outdoorAt(new Date(t)).weather, c.op, c.value); }
    case "outdoor": return cmp(outdoorAt(new Date(t))[c.variable], c.op, c.value);
    case "calendar": return calendarCond(c, t);
    case "phone_event": { const hit = recentPhone.some(e => e.timestamp >= t - c.withinMinutes * MIN && matchPhoneEvent(e, c)); return c.negate ? !hit : hit; }
    case "phone_state": return cmp(phoneField(c.field), c.op, c.value);
    case "health": {
      const evs = recentPhone.filter(e => e.type === "HEALTH" && e.source === c.record && (!c.withinMinutes || e.timestamp >= t - c.withinMinutes * MIN));
      const e = evs[evs.length - 1]; return !!e && cmp(e.payload[c.field], c.op, c.value); }
    case "recent_action": {
      const hit = actionHistory.some(([at, d, a]) => at >= t - c.withinMinutes * MIN && d === c.action.do && subset(c.action.args || {}, a));
      return c.negate ? !hit : hit; }
  }
  throw new Error("unknown condition kind " + c.kind);
}
const allConds = (cs, t) => (cs || []).every(c => cond(c, t));

/* ---------------- statistics ---------------- */
const stats = {};
const statFor = id => stats[id] ||= { triggered: 0, conditionsTrue: 0, followed: 0, notFollowed: 0, steps: { done: 0, no_change: 0, skipped: 0, refused: 0 }, refusals: {} };
const checkStats = { bedtime: { checked: 0, turnedOff: 0, leftOn: 0 }, leaving: { checked: 0, turnedOff: 0, leftOn: 0 }, morning: { checked: 0, turnedOff: 0, leftOn: 0 } };

/* ---------------- the person's actions ---------------- */
function refused(reason) { return { result: "refused", reason: reason || sim.lastRefusal || "refused" }; }
function goTo(roomId) { /* walk to a room at home before using something there by hand */
  if (S.place !== "home" || S.trip || S.asleep || S.room === roomId) return;
  phone.moveRoom(roomId); personChanges();
}
function handRoom(d) { return d.id === "balcony.door_contact" && S.room === "living_room" ? "living_room" : d.roomId; }
function exec(a, ctx) { /* one step; returns {result, reason?, block?} */
  const args = a.args || {};
  advanceSeconds();
  const t = clockMs();
  const done = n => n > 0 ? { result: "done" } : sim.lastRefusal ? refused() : { result: "no_change" };
  const awake = () => S.asleep ? refused("asleep") : this_driving() ? refused("driving") : null;
  let out;
  switch (a.do) {
    case "home.command": {
      const id = devId(args.device), d = sim.house.device(id); if (!d) { out = refused("no such device " + id); break; }
      if (args.channel === "mobile_app") out = done(phone.controlHome(id, args.capability, args.command, args.args || []));
      else { goTo(d.roomId); out = done(sim.run(id, args.capability, args.command, args.args || [], "physical")); }
      break; }
    case "home.record": {
      const id = devId(args.device), d = sim.house.device(id); if (!d) { out = refused("no such device " + id); break; }
      if (!(d.id === "balcony.door_contact" && S.room === "living_room")) goTo(d.roomId);
      out = done(sim.setValue(id, args.capability, args.attribute, args.value)); break; }
    case "person.travel": {
      if (S.trip) { out = refused("already travelling"); break; }
      if (S.asleep) { out = refused("asleep"); break; }
      if (S.place === "home") offCheck("leaving", t);
      advanceSeconds();
      const n = phone.travel(args.to, args.mode);
      if (n > 0 || S.trip) { out = { result: "done", block: { travelTo: args.to } }; }
      else out = args.to === S.place ? { result: "no_change" } : refused(); break; }
    case "person.moveRoom": out = done(phone.moveRoom(realRoom(args.room))); break;
    case "phone.screen": out = done(phone.screen(args.on === true || args.on === "true")); break;
    case "phone.openApp": out = done(phone.openApp(args.package)); break;
    case "phone.closeApp": out = done(phone.closeApp()); break;
    case "phone.install": out = done(phone.install(args.package, args.label)); break;
    case "phone.uninstall": out = done(phone.uninstall(args.package)); break;
    case "phone.power": out = done(phone.power(args.connected === true || args.connected === "true")); break;
    case "phone.btConnect": out = done(phone.btConnect(args.name)); break;
    case "phone.btDisconnect": out = done(phone.btDisconnect(args.name)); break;
    case "phone.media": out = done(phone.media(args.state, args.title, args.artist, args.album)); break;
    case "phone.call": out = done(phone.call(args.state)); break;
    case "phone.sms": out = done(phone.sms(args.direction || "OUTGOING")); break;
    case "phone.calendarAdd": {
      if ((out = awake())) break;
      let b = args.begin; if (typeof b === "string" && /^\d\d:\d\d$/.test(b)) b = dayStart(t) + hhmm(b) * MIN; else b = +b || t;
      out = done(phone.calendarAdd(args.title, b, b + num(args.durationMinutes || 60) * MIN, args.location || "")); break; }
    case "phone.calendarUpdate": {
      const evs = Object.values(S.calendar).filter(e => String(e.title).toLowerCase().includes(String(args.titleContains).toLowerCase()));
      if (!evs.length) { out = { result: "no_change" }; break; }
      const sh = num(args.shiftMinutes || 0) * MIN; let n = 0; for (const e of evs) n += phone.calendarUpdate(e.eventId, { begin: e.begin + sh, end: e.end + sh }); out = done(n); break; }
    case "phone.calendarDelete": {
      const evs = Object.values(S.calendar).filter(e => String(e.title).toLowerCase().includes(String(args.titleContains).toLowerCase()));
      let n = 0; for (const e of evs) n += phone.calendarDelete(e.eventId); out = evs.length ? done(n) : { result: "no_change" }; break; }
    case "phone.sleep": out = done(phone.sleep()); break;
    case "phone.wake": out = done(phone.wake()); break;
    case "phone.setActivity": out = done(phone.setActivity(args.activity)); break;
    case "phone.exerciseStart": out = done(phone.exerciseStart(args.kind)); break;
    case "phone.exerciseEnd": out = done(phone.exerciseEnd()); break;
    case "phone.measure": out = done(phone.measure(args.source, args.value)); break;
    case "phone.photo": out = done(phone.photo()); break;
    case "phone.screenshot": out = done(phone.screenshot(args.ocrText || "")); break;
    case "phone.copyClipboard": out = done(phone.copyClipboard(args.label || "Memo")); break;
    case "phone.appNotice": { if ((out = awake())) break; out = done(phone.notify(args.package, args.title || "", args.text || "", "status")); break; }
    case "wait": out = { result: "done", block: { until: t + Math.round(num(args.minutes)) * MIN } }; break;
    default: out = refused("unknown action " + a.do);
  }
  if (out.result === "done" || out.result === "no_change") { actionHistory.push([t, a.do, args]); }
  personChanges();
  return out;
}
function this_driving() { return phone.driving; }

/* ---------------- reverts (undo later) ---------------- */
const scheduled = []; /* {at, kind:"revert"|"eventCheck"|"morning", ...} */
function schedule(item) { scheduled.push(item); }
function deviceRevert(a) { /* the device's own timer: the command's effect, logged as the device's report */
  const args = a.args || {}, id = devId(args.device), d = sim.house.device(id); if (!d) return 0;
  const t = clockMs(); let n = 0;
  for (const [c, at, v] of d.effects(args.capability, args.command, args.args || [])) {
    const ch = d.set(c, at, v); if (!ch.changed) continue;
    const e = sim.build(d, ch, "device", null, [], new Date(t), "timer"); sim.log.add(e); phone.copyHome([e]); sim.noteAction(d, new Date(t)); n++;
  }
  return n;
}

/* ---------------- cooking: once the stove is on, the person turns it off after a cooking time ---------------- */
const COOK_DEFAULT = profile.cookingMinutes || { dist: "lognormal", median: 15, sigma: 0.6 };
const gaussR = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
function cookMinutes(c) {
  c = c || COOK_DEFAULT; let m;
  if (c.dist === "lognormal") m = c.median * Math.exp(c.sigma * gaussR());
  else if (c.dist === "shifted_exp") m = (c.min || 0) - c.mean * Math.log(1 - rnd());
  else m = -c.mean * Math.log(1 - rnd());
  return Math.max(1, Math.round(m));
}
const cookTimes = [];
function startCooking(a, from) {
  const mins = cookMinutes(a.cookingMinutes); cookTimes.push(mins);
  schedule({ kind: "revert", at: clockMs() + mins * MIN, byDevice: false, keep: true, owner: from,
    action: { do: "home.command", args: { device: "kitchen.stove", capability: "switch", command: "off", args: [], channel: "physical" } } });
}

/* ---------------- checks before sleep, before leaving, after waking ---------------- */
let leftOvernight = [];
function ruleState(rule, d, t) {
  if (rule.deviceType !== d.type) return false;
  if (rule.rooms && !rule.rooms.includes(d.roomId)) return false;
  if (rule.months && !monthOk(rule.months, t)) return false;
  return cmp(d.get(rule.isOn.capability, rule.isOn.attribute), rule.isOn.op, rule.isOn.value);
}
function onDevices(t, only) {
  const out = [];
  for (const d of Object.values(sim.house.devices)) {
    if (only && !only.includes(d.id)) continue;
    const rule = OFF.rules.find(r => ruleState(r, d, t)); if (rule) out.push([d, rule]);
  }
  for (let i = out.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [out[i], out[j]] = [out[j], out[i]]; } /* random order */
  return out;
}
function offCheck(moment, t, only) {
  if (S.place !== "home" || S.trip || S.asleep) return [];
  const back = S.room, left = [], cs = checkStats[moment];
  for (const [d, rule] of onDevices(t, only)) {
    cs.checked++;
    if (!chance(rule.p[moment])) { left.push(d.id); cs.leftOn++; continue; }
    const o = rule.off;
    const a = o.do === "home.record" ? { do: "home.record", args: { device: d.id, capability: o.capability, attribute: o.attribute, value: o.value } }
                                     : { do: "home.command", args: { device: d.id, capability: o.capability, command: o.command, args: o.args, channel: o.channel } };
    const r = exec(a, null); if (r.result === "done") cs.turnedOff++; else { left.push(d.id); cs.leftOn++; }
    trace({ t: iso(clockMs()), check: moment, device: d.id, result: r.result, reason: r.reason });
  }
  if (moment !== "morning") { /* the check takes over what the person meant to switch off later */
    for (let i = scheduled.length - 1; i >= 0; i--) if (scheduled[i].kind === "revert" && !scheduled[i].byDevice && !scheduled[i].keep) scheduled.splice(i, 1);
  }
  if (back && S.room !== back) { phone.moveRoom(back); personChanges(); }
  return left;
}

/* ---------------- behaviours ---------------- */
const behaviours = profile.behaviours.map(b => ({ ...b, _st: {}, _firings: 0 }));
const tasks = [];
function shiftActions(b, t) { /* preference_shift: old actions before the change, new after, mixed during transitionDays */
  const sh = b.shift || (b.pattern && b.pattern.shift); if (!sh || !sh.before) return b.actions;
  let p;
  if (sh.at && sh.at.monthDay) {
    const [mm, dd] = sh.at.monthDay.split("-").map(Number), at = new Date(new Date(t).getFullYear(), mm - 1, dd).getTime();
    const days = (t - at) / DAY, tr = sh.transitionDays || 0; p = days < 0 ? 0 : tr ? Math.min(1, days / tr) : 1;
  } else if (sh.at && sh.at.afterFirings != null) {
    const k = b._firings - sh.at.afterFirings, tr = sh.transitionDays || 0; p = k < 0 ? 0 : tr ? Math.min(1, k / tr) : 1;
  } else p = 1;
  return chance(p) ? b.actions : sh.before;
}
function fire(b, t, how) { /* the trigger fired: check conditions, then decide with the behaviour's probability */
  const s = statFor(b.id); s.triggered++;
  const day = how.day ?? dayStart(t), dk = dayKey(day);
  b._st.count ||= {}; const cnt = b._st.count[dk] || 0;
  if (cnt >= (b.maxPerDay || 1)) { s.triggered--; s.overMaxPerDay = (s.overMaxPerDay || 0) + 1; return "max"; }
  if (!allConds(b.conditions, t)) return "conditions_false";
  s.conditionsTrue++;
  if (!chance(b.probability)) { s.notFollowed++; trace({ t: iso(t), behaviour: b.id, outcome: "not_followed", via: how.via }); return "not_followed"; }
  s.followed++; b._st.count[dk] = cnt + 1; b._firings++;
  const actions = resolve(shiftActions(b, t));
  const task = { b, actions, i: 0, until: 0, travelTo: null, steps: [], start: t, via: how.via };
  if (actions.some(a => a.do === "phone.sleep")) offCheck("bedtime", t);
  tasks.push(task); runTask(task);
  return "followed";
}
function runTask(task) {
  const s = statFor(task.b.id);
  while (task.i < task.actions.length) {
    if (task.until && clockMs() < task.until) return;
    if (task.travelTo) { if (S.trip) return; task.travelTo = null; }
    task.until = 0;
    const a = task.actions[task.i++];
    if (a.probability != null && !chance(a.probability)) { s.steps.skipped++; task.steps.push([a.do, "skipped"]); continue; }
    if (a.when && !allConds(a.when, clockMs())) { s.steps.skipped++; task.steps.push([a.do, "skipped_when"]); continue; }
    const r = exec(a, task);
    s.steps[r.result]++; if (r.reason) s.refusals[r.reason.slice(0, 80)] = (s.refusals[r.reason.slice(0, 80)] || 0) + 1;
    task.steps.push(r.reason ? [a.do, r.result, r.reason.slice(0, 80)] : [a.do, r.result]);
    if (r.result === "done" && a.do === "home.command" && devId(a.args.device) === "kitchen.stove" && a.args.command === "on") startCooking(a, task.b.id);
    if (a.revert && (r.result === "done" || r.result === "no_change")) {
      schedule({ kind: "revert", at: clockMs() + Math.round(num(a.revert.afterMinutes)) * MIN, byDevice: !!a.revert.byDevice, action: resolve(a.revert.action), owner: task.b.id });
    }
    if (a.do === "person.travel" && r.result === "refused") { task.i = task.actions.length; break; } /* no trip: the rest makes no sense */
    if (r.block && r.block.until) { task.until = r.block.until; return; }
    if (r.block && r.block.travelTo) { task.travelTo = r.block.travelTo; return; }
  }
  task.finished = true;
  trace({ t: iso(task.start), behaviour: task.b.id, outcome: "followed", via: task.via, steps: task.steps });
}

/* event triggers */
function eventMatches(ev, h) {
  if (ev.source !== h.src) return false;
  if (h.src === "home") {
    const e = h.e;
    if (e.device !== ev.deviceType || e.capability !== ev.capability || e.attribute !== ev.attribute) return false;
    if (ev.room && e.roomId !== realRoom(ev.room)) return false;
    if (!cmp(e.value, "==", ev.value)) return false;
    if (ev.previousValue !== undefined && !cmp(e.previousValue, "==", ev.previousValue)) return false;
    return true;
  }
  if (h.src === "phone") return matchPhoneEvent(h.e, ev);
  if (h.src === "person") return h.what === ev.what && (!ev.place || ev.place === h.place) && (!ev.room || realRoom(ev.room) === h.room);
  if (h.src === "weather") return h.to === ev.to && (!ev.from || ev.from === h.from);
  return false;
}
function processHappenings() {
  for (let guard = 0; happenings.length && guard < 50; guard++) {
    const batch = happenings.splice(0);
    for (const h of batch) {
      if (h.src === "person" && h.what === "wake" && S.place === "home" && leftOvernight.length)
        schedule({ kind: "morning", at: clockMs() + Math.round(uni(0, OFF.morningWithinMinutes)) * MIN, devices: leftOvernight.splice(0) });
      if (h.src === "person" && h.what === "fall_asleep") leftOvernight = onDevices(clockMs()).map(([d]) => d.id);
      for (const b of behaviours) {
        const tr = b.trigger; if (tr.kind !== "event" || !eventMatches(tr.event, h)) continue;
        if (tr.delayMinutes != null) schedule({ kind: "eventCheck", at: clockMs() + Math.round(num(tr.delayMinutes)) * MIN, b });
        else fire(b, clockMs(), { via: "event" });
      }
    }
  }
}

/* The person does one thing at a time: a behaviour that moves the person or uses things by hand waits while another one is
   in the middle of such steps. A behaviour sitting in a long wait (15 min or more left) does not count: it can be interrupted. */
const BODY = new Set(["person.travel", "person.moveRoom", "home.record"]);
const isBody = a => BODY.has(a.do) || (a.do === "home.command" && (a.args || {}).channel !== "mobile_app");
const hasBody = actions => actions.some(isBody);
function busy(t) {
  return tasks.some(k => !k.finished && (k.travelTo || (k.actions.slice(k.i).some(isBody) && !(k.until && k.until - t >= 15 * MIN))));
}
const DEFER_MAX_MIN = 180; /* a daily behaviour waits at most this long after its minute */

/* time triggers, once per minute */
function timeTriggers(t) {
  const list = [];
  for (const b of behaviours) {
    const tr = b.trigger; if (tr.kind === "event") continue;
    const deferred = tr.kind === "daily" && b._st.daily && b._st.daily.at === t && b._st.daily.deferred;
    const day = deferred ? b._st.daily.day : windowDay(tr.window, t); if (day == null) { if (tr.kind === "time_window") b._st.tw = null; continue; }
    if (!dayOk(tr.days, day) || !monthOk(tr.months, day)) continue;
    const dk = dayKey(day);
    if (tr.kind === "time_window") {
      /* checked every minute; the first minute the conditions hold decides; after a follow, the next false -> true change can fire again */
      const w = b._st.tw && b._st.tw.dk === dk ? b._st.tw : (b._st.tw = { dk, decided: false, last: false });
      if (w.stop) continue;
      const now = allConds(b.conditions, t);
      if (now && !w.last) list.push([b, { day, via: "time_window", w }]);
      w.last = now;
    } else if (tr.kind === "daily") {
      b._st.daily ||= {};
      if (b._st.daily.dk !== dk) { const f = hhmm(tr.window.from), to = hhmm(tr.window.to), len = (to - f + 1440) % 1440 + 1; b._st.daily = { dk, day, at: day + (f + Math.floor(rnd() * len)) * MIN }; }
      if (b._st.daily.at === t) list.push([b, { day, via: "daily", daily: b._st.daily }]);
    } else if (tr.kind === "rate") {
      if (chance(tr.perHour / 60)) list.push([b, { day, via: "rate" }]);
    }
  }
  list.sort((x, y) => (y[0].priority || 0) - (x[0].priority || 0));
  for (const [b, how] of list) {
    if (hasBody(b.actions) && busy(t)) { /* the person is in the middle of something */
      if (how.daily) { if (t - (how.daily.first ??= t) < DEFER_MAX_MIN * MIN) { how.daily.at = t + MIN; how.daily.deferred = true; } }
      else if (how.w) how.w.last = false; /* time_window: try again next minute */
      statFor(b.id).deferred = (statFor(b.id).deferred || 0) + 1;
      continue;
    }
    const r = fire(b, t, how);
    if (how.w && (r === "not_followed" || r === "max")) how.w.stop = true; /* time_window: not followed -> no more tries that day */
  }
}

/* scheduled items due */
function runScheduled(t) {
  scheduled.sort((a, b) => a.at - b.at);
  while (scheduled.length && scheduled[0].at <= t) {
    const it = scheduled.shift();
    if (it.kind === "revert") {
      if (it.byDevice) { sim.clock.setTo(it.at); deviceRevert(it.action); }
      else { const r = exec(it.action, null); const s = statFor(it.owner); s.steps[r.result]++; if (r.reason) s.refusals["revert: " + r.reason.slice(0, 70)] = (s.refusals["revert: " + r.reason.slice(0, 70)] || 0) + 1; }
    } else if (it.kind === "eventCheck") fire(it.b, t, { via: "event" });
    else if (it.kind === "morning") offCheck("morning", t, it.devices);
    personChanges(); processHappenings();
  }
}

/* ---------------- main loop: one simulated minute at a time ---------------- */
const t0 = Date.now(); let lastWeather = outdoorAt(new Date(T0)).weather;
for (let t = T0 + MIN; t <= TEND; t += MIN) {
  minuteMs = t; secInMinute = 0;
  sim.clock.setTo(t); sim.tick();                       /* the world moves one minute: physics, appliances, sensors, phone, trips */
  personChanges();
  const w = outdoorAt(new Date(t)).weather;
  recentWeather.push([t, w]); if (w !== lastWeather) { happenings.push({ src: "weather", from: lastWeather, to: w }); lastWeather = w; }
  processHappenings();
  runScheduled(t);
  timeTriggers(t); processHappenings();
  for (const task of tasks) if (!task.finished) { runTask(task); processHappenings(); }
  for (let i = tasks.length - 1; i >= 0; i--) if (tasks[i].finished) tasks.splice(i, 1);
  sim.clock.setTo(t);                                   /* back to the whole minute before the next step */
  if (t % (6 * 3600000) === 0) {                         /* housekeeping */
    while (recentPhone.length && recentPhone[0].timestamp < t - DAY) recentPhone.shift();
    while (recentWeather.length && recentWeather[0][0] < t - DAY) recentWeather.shift();
    while (actionHistory.length && actionHistory[0][0] < t - 7 * DAY) actionHistory.shift();
  }
  if ((t - T0) % DAY === 0) {
    writeOut(t - 2 * DAY);
    const d = (t - T0) / DAY;
    if (d % 30 === 0 || d === DAYS) console.log(`day ${d}/${DAYS} (${dayKey(t - MIN)}) home ${nHome} phone ${nPhone} lines written, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  }
}
sim.flush(); writeOut(Infinity);
if (homeOut) fs.closeSync(homeOut); fs.closeSync(phoneOut); if (traceOut) fs.closeSync(traceOut);
const summary = { personaId: profile.personaId, houseId: sim.houseId, houseType: sim.type, variant: profile.variant, startDate: profile.simulation.startDate, days: DAYS, seed: SEED,
  homeLines: nHome, phoneEvents: nPhone, behaviours: stats, checks: checkStats,
  cooking: (() => { const c = cookTimes.slice().sort((a, b) => a - b), q = f => c.length ? c[Math.min(c.length - 1, Math.floor(f * c.length))] : null;
    return { times: c.length, minutesMedian: q(0.5), minutesP10: q(0.1), minutesP90: q(0.9), minutesMax: c.length ? c[c.length - 1] : null }; })(), seconds: Math.round((Date.now() - t0) / 1000) };
fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
console.log(`done: ${nPhone} phone events (${nHome} of them copies of home lines) -> ${outDir}`);
