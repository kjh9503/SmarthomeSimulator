const fs = require("fs");
const houseTypes = {};
for (const [ht, t] of Object.entries(HOUSE_TYPES)) {
  const s = new Simulator(SPEC); s.variant = `${ht}-A`; const h = s.house;
  houseTypes[ht] = { rooms: h.rooms.map(r => r.id), devices: Object.keys(h.devices).sort(), variants: Object.keys(ROOM_PROFILES).filter(v => ROOM_PROFILES[v].houseType === ht) };
}
const deviceTypes = {};
for (const d of SPEC) deviceTypes[d.device] = { label: DEVICE_LABEL[d.device], rooms: d.rooms, capabilities: d.capabilities.map(c => ({
  capability: c.capability, attributes: c.attributes.map(a => ({ name: a.name, type: a.type, ...(a.values ? { values: a.values } : {}), ...(a.unit ? { unit: a.unit } : {}), ...(a.min != null ? { min: a.min } : {}), ...(a.max != null ? { max: a.max } : {}) })),
  commands: c.commands.map(m => ({ name: m.name, args: m.args })) })),
  ...(d.device === "washer" ? { modes: Object.keys(CYCLE_MINUTES.washer) } : {}) };
const vocab = {
  _about: "Names the structured patterns may use. Generated from the simulator (smarthome-sim.html). Do not invent names outside this file except where a field says 'free text'.",
  houseTypes, deviceTypes,
  roomLabels: ROOM_LABEL,
  places: Object.fromEntries(Object.entries(PLACES).filter(([, p]) => p.lat != null).map(([k, p]) => [k, { label: p.label, category: p.category, wifi: p.wifi }])),
  travelModes: Object.fromEntries(Object.entries(TRAVEL_MODES).map(([k, m]) => [k, { rideActivity: m.activity, drives: !!m.drives, bluetooth: m.bt || null }])),
  activities: Object.keys(ACTIVITIES),
  exercises: Object.keys(EXERCISES),
  healthMeasures: Object.keys(MEASURES),
  healthRecords: { HOURLY: ["steps", "meters", "kilocalories", "averageBpm", "minBpm", "maxBpm"], SLEEP: ["durationMinutes", "startTime", "endTime"], EXERCISE: ["title", "durationMinutes", "startTime", "endTime"] },
  apps: Object.fromEntries(Object.entries(APPS).map(([k, a]) => [k, a.about ? `${a.label} (${a.about})` : a.label])),
  bluetoothDevices: Object.keys(BT_DEVICES),
  weather: { states: ["clear", "cloudy", "rain", "snow"], outdoorVariables: { temperature: "C", humidity: "%", pm25: "µg/m³", windSpeed: "m/s", precipitation: "mm/h", daylight: "lux" } },
  smartThingsAlerts: ST_ALERTS.map(a => ({ category: a.category, device: a.device || `any device with ${a.attr}`, attribute: a.attr, severity: a.severity })),
  phoneEventTypes: ["NOTIFICATION", "APP_USAGE", "HEALTH", "SMARTTHINGS", "DEVICE_STATE", "CONNECTIVITY", "MEDIA", "APP_LIFECYCLE", "DATA_USAGE", "ACTIVITY", "TELEPHONY", "CALENDAR", "CLIPBOARD", "MEDIA_CAPTURE"],
  calendarActions: ["ADD", "UPDATE", "DELETE", "REMINDER"],
};
fs.writeFileSync(process.argv[2], JSON.stringify(vocab, null, 2) + "\n");
console.log("rooms", JSON.stringify(Object.fromEntries(Object.entries(houseTypes).map(([k, v]) => [k, v.rooms.length + " rooms / " + v.devices.length + " devices"]))), "| places", Object.keys(vocab.places).length, "| apps", Object.keys(vocab.apps).length, "| device types", Object.keys(deviceTypes).length);
