## Home (one person, one house)
- 2room: rooms room1, room2, living_room, kitchen, dining_room, bathroom, laundry, closet, entryway, balcony
- 3room: rooms room1, room2, room3, living_room, kitchen, dining_room, bathroom, laundry, closet, hallway, entryway, balcony
- 4room: rooms room1, room2, room3, room4, living_room, kitchen, dining_room, bathroom, laundry, closet, hallway, entryway, balcony
- room1..room4 can play any role (bedroom, study room, nursery, kids' room, home office); balcony is outdoors.

## Home devices (device type: rooms | capability.attribute values | commands)
- temperature_sensor: balcony, bathroom, closet, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | temperatureMeasurement.temperature=number C
- humidity_sensor: balcony, bathroom, closet, dining_room, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | relativeHumidityMeasurement.humidity=integer % 0-100
- light_sensor: bathroom, closet, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | illuminanceMeasurement.illuminance=number lux
- occupancy_sensor: balcony, bathroom, closet, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | presenceSensor.presence=present|not present
- air_quality_sensor: balcony, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | fineDustSensor.fineDustLevel=number µg/m³; carbonDioxideMeasurement.carbonDioxide=number ppm
- noise_sensor: balcony, bathroom, closet, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | soundPressureLevel.soundPressureLevel=number dB
- door_contact: balcony, entryway | contactSensor.contact=open|closed
- window_contact: living_room, room1, room2, room3, room4 | contactSensor.contact=open|closed
- water_leak_sensor: bathroom, kitchen, laundry | waterSensor.water=dry|wet
- smoke_alarm: kitchen | smokeDetector.smoke=clear|detected
- doorbell: entryway | button.button=pushed
- wifi_router: living_room | connectedDevices.connectedDevices=integer
- light: balcony, bathroom, closet, dining_room, entryway, hallway, kitchen, laundry, living_room, room1, room2, room3, room4 | switch.switch=on|off; cmd on(), off()
- lamp: living_room, room1, room2, room3, room4 | switch.switch=on|off; cmd on(), off(); switchLevel.level=integer 0-100; cmd setLevel(level); colorTemperature.colorTemperature=integer K 2700-6500; cmd setColorTemperature(K)
- heating_cooling_unit: dining_room, hallway, kitchen, living_room, room1, room2, room3, room4 | thermostatMode.thermostatMode=off|cool|heat; cmd setThermostatMode(mode); thermostatCoolingSetpoint.coolingSetpoint=number C; cmd setCoolingSetpoint(C); thermostatHeatingSetpoint.heatingSetpoint=number C; cmd setHeatingSetpoint(C)
- humidifier: room1, room2, room3, room4 | switch.switch=on|off; cmd on(), off(); humiditySetpoint.humiditySetpoint=integer % 0-100; cmd setHumiditySetpoint(%)
- air_purifier: living_room | fanSpeedPercent.percent=integer 0-100; cmd setPercent(percent)
- curtain: living_room | windowShade.windowShade=open|closed|opening|closing|partially_open|unknown; cmd open(), close(), pause()
- tv: living_room | switch.switch=on|off; cmd on(), off(); mediaPlayback.playbackStatus=playing|paused|stopped; cmd play(), pause(), stop()
- speaker: living_room, room1, room2 | connection.connection=connected|disconnected; mediaPlayback.playbackStatus=playing|paused|stopped; cmd play(), stop(); audioVolume.volume=integer 0-100; cmd setVolume(volume)
- robot_vacuum: living_room | robotCleanerOperatingState.operatingState=docked|running|seekingCharger|charging|paused|stopped; cmd start(), pause(), goHome(); battery.battery=integer % 0-100
- dishwasher: kitchen | cycleState.cycleState=idle|running|finished; cmd start(), startHeatedDry(); remainingTime.remainingTime=integer min; contactSensor.contact=open|closed
- oven: kitchen | mode.mode=off|bake|convection; cmd setMode(mode); temperatureSetpoint.temperatureSetpoint=number C; cmd setTemperatureSetpoint(C); temperatureMeasurement.temperature=number C; contactSensor.contact=open|closed; preheat.preheat=idle|preheating|ready
- stove: kitchen | switch.switch=on|off; cmd on(), off()
- washer: laundry | cycleState.cycleState=idle|running|finished; cmd start(mode); mode.mode=normal|quick|bedding; remainingTime.remainingTime=integer min | washer modes: normal, quick, bedding
- dryer: laundry | cycleState.cycleState=idle|running|finished; cmd start(mode, minutes); mode.mode=normal|delicate|timeDry; remainingTime.remainingTime=integer min; errorCode.errorCode=string
- lock: entryway | lock.lock=locked|unlocked; cmd lock(), unlock()

## Home device alerts the phone receives (SmartThings app notifications)
- doorbell (doorbell), smoke (smoke_alarm), water_leak (water_leak_sensor), cycle_finished (any device with cycleState), cleaning_finished (robot_vacuum), preheat_done (oven), device_error (any device with errorCode)

## Places outside home
- Home: home
- Work and study: office, coworking, campus, library
- Transport: station, subway_station, bus_stop, airport, gas_station, parking_lot
- Food and drink: cafe, restaurant, bakery, bar
- Shopping: market, grocery_store, convenience_store, mall, department_store, electronics_store
- Leisure and sport: gym, swimming_pool, park, river_park, hiking_trail, cinema, museum, stadium, place_of_worship
- Health and services: hospital, clinic, dentist, pharmacy, bank, post_office, hair_salon, government_office
- People and stays: friend_home, parents_home, hotel
- Away = any place other than home. Trips between places take time; travel modes: walk, bicycle, scooter, motorcycle, car, car_passenger, taxi, bus, subway, train, airport_rail

## The person's phone
- Things the phone receives: messenger/app notifications (any app, any text), calls ringing or missed, incoming SMS, calendar reminders at an event's start, SmartThings alerts above, weather-app notifications (rain expected / rain started / clear), hourly health (steps, distance, kcal, heart rate).
- Calendar events: title, start, end, location (any text). Values a pattern depends on (guest count, meeting format, pickup place, document type...) can live in an event title or in a notification's text.
- Phone states: screen on/off, charging, battery %, activity (IN_VEHICLE, ON_BICYCLE, STILL, WALKING, RUNNING), asleep, music playing/paused (phone), Bluetooth (Galaxy Buds, Car Audio), Wi-Fi network, app in the foreground.
- Health: measures WEIGHT, BODY_FAT, BLOOD_PRESSURE, BLOOD_GLUCOSE, BODY_TEMPERATURE, OXYGEN_SATURATION, RESPIRATORY_RATE, RESTING_HEART_RATE, VO2_MAX, HYDRATION; exercises Running, Walking, Cycling (with durationMinutes); SLEEP record with durationMinutes on waking.
- Person's phone actions: open/close any app, the app then shows a notification describing the result (navigation started, item added to a checklist, timer started, setting changed); play/pause/stop phone music; add/change/delete calendar events; calls, SMS, photos, screenshots, clipboard; connect/disconnect Bluetooth; plug in/unplug; sleep/wake; start/end exercise; record health measures; control any home device from the SmartThings app.
- Apps already installed: KakaoTalk (com.kakao.talk), Chrome (com.android.chrome), YouTube (com.google.android.youtube), Spotify (com.spotify.music), Instagram (com.instagram.android), Naver Map (com.nhn.android.nmap), SmartThings (com.samsung.android.oneconnect). Other realistic Android apps may be named (give package and label).

## Outdoors
- Weather: clear, cloudy, rain, snow; outdoor temperature (C), humidity (%), pm25 (µg/m³), windSpeed (m/s), precipitation (mm/h), daylight (lux). Seoul climate.
