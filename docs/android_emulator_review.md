# Decision: the phone log is not made with the Android Emulator

Date: 2026-10-28. Status: decided, review closed.

## Question

Could the Android Emulator replace our phone simulator (`smarthome_sim/phone.py`), so that the phone log
(APP_USAGE, screen, notifications, calendar, ...) comes from a real Android system and stays consistent by itself
(for example: an app is always opened before it is used)?

## Decision

No. The dataset is a controlled benchmark (hidden patterns with known ground truth, 100 personas x 1 year).
The emulator would give consistency for part of the phone log, but costs speed, reproducibility and the link to the
home, health and activity logs. Instead, the phone simulator gets the Android rules it is missing
(one foreground app, screen on/off, an app is opened before it is used).

Marks: [doc] checked in official documentation on 2026-10-28; [063] counted in our 063 run (Python, seed 63,
365 days); [expected] our knowledge or expectation, not tested.

## What our phone log contains [063]

| Log type | Lines in one year | Made by |
|---|---|---|
| SMARTTHINGS (copies of home lines) | 302,191 | home simulator |
| APP_USAGE | 27,080 | phone simulator |
| DATA_USAGE | 11,203 | phone simulator |
| HEALTH (steps, heart rate, sleep, exercise) | 9,144 | phone simulator |
| ACTIVITY (walking, still, in vehicle) | 6,304 | phone simulator |
| CONNECTIVITY (Wi-Fi, Bluetooth) | 1,648 | phone simulator |
| DEVICE_STATE (screen, charging) | 1,458 | phone simulator |
| MEDIA | 436 | phone simulator |

31,796 phone lines (SMARTTHINGS excluded) were made directly by rules or checks. The log has 44 event formats
(`pipeline/event-formats-v3.json`).

## Reasons

1. **The steps before an operation do not go away.** The emulator would refuse an inconsistent log, but it does
   not open apps by itself. The agent would have to launch SmartThings and tap through its screens. The agent
   becomes more detailed than now, not less. [expected]
2. **More than half of the log would still be made by us.** [063 counts above]
   - SMARTTHINGS: the SmartThings app shows devices of the real SmartThings cloud; our simulated home is not
     there. [expected]
   - HEALTH (steps, heart rate, sleep): there is no watch; the values would still be written by us. [expected]
   - ACTIVITY: the console has no command for activity recognition. Sensor values can be set, but producing
     motion that Android recognises as walking or driving is a separate problem. [doc] [expected]
   - Wi-Fi names per place (home, campus): the emulator has one virtual Wi-Fi network. [expected]
   - Bluetooth: netsim handles BLE and Bluetooth Classic radio; how to emulate a car or earbuds connection is not
     documented. [doc]
   - Clipboard: since Android 10 only the default keyboard app or the app in focus can read the clipboard, so a
     log collector app cannot record CLIPBOARD lines. [doc]
   - Outgoing calls and SMS: the console only simulates incoming calls (`gsm call`) and incoming SMS
     (`sms send`). [doc]
   So the result would be a mix of emulator and our simulators, with a new problem: keeping their clocks in step.
3. **Time.** The emulator runs in real time. The console has no command to set the clock [doc]. Setting it with
   `date` on a rooted image may work, but how usage statistics behave across clock jumps was not checked.
   Our simulator runs one persona-year in about 4 minutes [063]; with an adb command per operation, an
   emulator year would take hours even with clock jumps. [expected]
4. **Reproducibility.** Now the same profile and seed give the same log (tested in `tests/test_port.py`).
   Background work, notifications and network in the emulator would make runs differ. [expected]
   A controlled benchmark needs runs that can be repeated exactly.
5. **Machines.** The emulator on Linux needs KVM; hosted runners have to enable it separately (Tenki docs) [doc].
   This work environment has no `/dev/kvm` (2 CPUs, 7 GB memory).
6. **Real apps need accounts.** KakaoTalk, Instagram and others need a login per persona. [expected]

## What the emulator would have given

- APP_USAGE, screen and notification lines that are consistent because Android writes them. [expected]
- Location (`geo fix`), battery and charger (`power`), incoming calls and SMS (`gsm call`, `sms send`). [doc]
- A strong answer to reviewers on realism: "the phone lines come from real Android APIs".

## Sources

- Send emulator console commands: https://developer.android.com/studio/run/emulator-console
- Advanced emulator networking features (netsim, Bluetooth): https://developer.android.com/studio/run/emulator-networking-advanced
- Android 10 privacy changes (clipboard): https://developer.android.com/about/versions/10/privacy/changes
- Android Emulator on Linux runners, KVM: https://tenki.cloud/docs/runners/android-emulator
