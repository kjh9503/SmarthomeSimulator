# 에이전트 시뮬레이터: 설계 결정과 참고 문헌 (한국어판)

기준: 2026-10-29, repo 커밋 a1d0c42. 영어판은 `docs/agent_design_notes.md`.
표시: **[문헌]** 아래 참고 문헌에서 가져온 값 · **[가정]** 근거 없이 정한 값 · **[측정]** 우리 실행에서 잰 값
(따로 적지 않으면 프로필 063, Python, seed 63, 2026년 365일).

## 1. 목적과 전제

- 이 데이터셋은 **정답을 아는 통제된 벤치마크**다. 프로필 하나가 한 사람이고, 집과 휴대폰의 1년을 만든다. 숨긴 패턴의 정답을 알고 있다. "현실적인 생활 데이터"라고 주장하지 않는다.
- 시험할 방법론: 휴대폰 원시 로그를 받아 사람의 패턴을 **if-then 규칙**으로 찾아낸다.
- 설계에 주는 조건:
  - 패턴과 일상이 형식에서 구별되면 안 된다 (패턴만 만드는 로그 줄 금지, 8절).
  - 현실성은 패턴 찾기의 난이도를 바꾸는 곳에서 중요하다. 숫자는 최근 자료에서 가져온다.
  - 같은 프로필 + 같은 seed = 같은 로그 (`tests/test_port.py`로 확인).

## 2. 프로필 = 규칙 목록

- 규칙(`behaviours` 항목 하나): trigger → 조건(모두 참) → 확률 → actions. `kind`는 `pattern`(숨긴 패턴, 정답) 또는 `routine`(일상).
- trigger 종류:
  - `time_window`: 매분 확인, 조건이 참으로 바뀌는 순간 실행
  - `daily`: 시간대 안의 무작위 한 분
  - `rate`: 시간당 횟수
  - `event`: 집 기기 보고, 휴대폰 이벤트, 사람의 도착·출발·기상·취침, 날씨
- 단계별 옵션: `when`(그 단계의 조건), `probability`, `revert`(`afterMinutes`, `byDevice` = 기기 타이머), `{"choice": [...], "weights": [...]}`와 `{min, max}`(매번 뽑음), `cookingMinutes`.
- 규칙의 확률은 숫자 하나다. 계절·시각에 따른 차이는 규칙을 나누거나(`months`, `days`, 시간대) 조건(날씨, 바깥 값, 센서)으로 만든다. 예: 저녁 환기는 4–10월 0.35, 11–3월 0.12. 063에서 월별로 확률이 다른 것은 창문·발코니 문뿐이다.

## 3. 엔진 (`smarthome_sim/agent.py`)

- 매분 순서:
  1. `sim.tick()`으로 세상이 1분 진행
  2. 새로 생긴 일에 대한 event 규칙
  3. 예약된 일 (되돌리기, 지연 확인, 아침 확인)
  4. 시간 trigger
  5. 진행 중인 작업
- 엔진은 시뮬레이터 변수에 값을 직접 넣지 않는다. action마다 시뮬레이터 함수를 부른다: `home.command` → `sim.run`, `home.record` → `sim.set_value`, `person.moveRoom` → `phone.move_room`, 앱 조작 → `phone.control_home`. 거절(자는 중, 집에 없음, 그 방에 없음, 운전 중)은 시뮬레이터가 한다.
- 손 조작 전에 사람을 그 기기의 방으로 옮긴다(`go_to`). 로그에 재실 변화가 남는다.
- 몸을 쓰는 작업은 한 번에 하나다. 15분 이상 기다리는 작업은 끼어들기를 허용한다. daily 규칙은 최대 180분까지 미룬다.
- 1분 안의 조작은 하나에 3–15초씩 시각이 흐른다. 앱 이어 쓰기는 초 단위로 진행하며, 그 분에 이미 일어난 일보다 이른 시각으로는 기록하지 않는다.

## 4. 끄기 확인 (`smarthome_sim/off_rules.json`) [가정, 합의함]

잠들기 전, 외출 전, 아침(일어난 뒤 60분 안)에 켜져 있는 기기를 각각의 확률로 끈다.

| 기기 | 자기 전 | 외출 전 | 아침 |
|---|---|---|---|
| 조명 | 0.95 | 0.98 | 0.9 |
| 스탠드 | 0.9 | 0.97 | 0.85 |
| TV, 스피커 | 0.95 | 0.99 | 0.9 |
| 공기청정기, 난방, 가습기 | 0.8 | 0.9 | 0.8 |
| 냉방 | 0.8 | 0.92 | 0.8 |
| 창문·발코니 문, 11–3월 | 0.98 | 0.99 | 0.95 |
| 창문·발코니 문, 4–10월 | 0.85 | 0.95 | 0.5 |

가스레인지·오븐: 요리 시간을 뽑아 끄기를 예약한다(063: 로그정규 중앙값 15분, sigma 0.6. 아침은 중앙값 6분, sigma 0.5). 기기 자동 꺼짐은 가스레인지 240분, 오븐 720분이고, 마지막 안전장치로 둔다. [가정]

## 5. 가전 (프롬프트 `pipeline/prompt_agent_profile.md`)

집 9종 모두에 모든 기기 종류가 있다. 쓰는지는 규칙이 정한다.

| 묶음 | 기기 | 규칙 | 근거 |
|---|---|---|---|
| A 누구나 씀 (조건이 맞으면) | 냉방, 난방, 세탁기, 조명, 잠금·현관 | 반드시 씀 | 에어컨 보유 98% [문헌 Gallup 2025], 드럼 66% + 통돌이 35% [문헌 Gallup 2023] |
| B 누구나 있음, 빈도는 사람마다 | TV, 가스레인지, 커튼, 창문, 스탠드 | 페르소나에 따라 | TV 99% [문헌 Gallup 2023] |
| C 일부만 가짐 | 공기청정기 66%, 가습기 39%, 건조기 35%, 식기세척기 24%, 오븐 21%, AI 스피커 18%, 로봇청소기 15% | 가진 경우만 | [문헌 Gallup 2023, 2025] |
| D 사람이 조작 안 함 | 센서, 공유기, 초인종, 화재경보기 | 없음 | |

- 기준 온도 [가정]: 냉방은 26–28°C(기본 27), 난방은 18–20°C(기본 19).
- 063 시험 [측정]:
  - 28/18°C 기준: 냉방 1년 8일
  - 27/19°C 기준: 냉방 26일(7–8월만), 난방 107일, 세탁 45일
- 남은 문제:
  - 시뮬레이터의 여름 실내 온도가 낮을 수 있다(냉방 없이 8월 거실 최고 28.8°C).
  - 에어컨을 켜고 자는 경우가 자기 전 끄기 확인과 충돌한다.

## 6. 같은 기기의 반복 조작

- 엔진에 최소 간격은 없다. [측정]
  - 짧은 켜기→끄기의 대부분은 한 규칙 안에서 생긴다(현관 조명, 요리).
  - 다른 경로끼리 부딪친 경우: 아침 창문 열기 직후 외출 전 확인이 닫음, 0.1분 안에 3번. 난방을 켜고 60분 안에 외출 전 확인이 끔, 15번.
- 합의한 구분:
  - (가) 두 번째 조작이 너무 빠름 → 간격에 따른 확률. 패턴과 일상에 똑같이 적용하고, 패턴이 정한 지속 시간 안에서는 적용하지 않는다.
  - (나) 곧 나가거나 잘 사람에게 첫 조작이 어울리지 않음 → 간격 확률로는 풀리지 않는다.
- 둘 다 아직 미해결.

## 7. 조작 전에 반드시 거치는 단계

합의한 두 기준:
1. 그 단계가 로그에 줄을 남길 때만 만든다.
2. 방법이 하나뿐이면 엔진이 자동으로 넣는다(확률 없음). 여럿이면 프로필이 확률로 고른다.

| 조작 | 앞 단계 (로그 줄) | 방법 | 결정 |
|---|---|---|---|
| 앱으로 집 기기 조작 | SmartThings가 앞에 뜸 | 하나 | 자동 (아직 안 만듦) |
| 일정 추가·변경·삭제 | 캘린더가 앞에 뜸 | 하나 (다른 앱에서 추가는 고려 안 함) | 자동 (안 만듦) |
| 전화 걸기, 문자 보내기, 사진 | 전화 / 메시지 / 카메라가 앞에 뜸 | 하나 | 자동 (안 만듦) |
| 건강 수치 입력, 운동, 음악 재생·멈춤 | 앱이 앞에 뜸, 또는 없음 (연동 기기, 워치, 이어폰, 알림창) | 여럿 | 확률 (안 만듦) |
| 스크린샷, 복사 | 어떤 앱이 앞에 있음 | | 그때 앞에 있던 앱, 없으면 설치된 앱 중 무작위 |
| 앱 설치·삭제 | | | 제외 (어떤 패턴에도 없음) |
| 집 안 손 조작 | 그 방에 있음 (재실) | 하나 | 됨 (`go_to`) |
| 외출·귀가 | 현관문, 잠금 | 하나 | 됨 |

이 기준을 정하기 전의 발견 [측정]: 063에서 일상 규칙(25번)과 외출 전 확인(3번)이 앱으로 공기청정기를 조작할 때는 SmartThings 앱 줄이 없었다. 패턴은 앱을 열었다. 실제 휴대폰에서는 나올 수 없는 로그이고, 패턴만 만드는 단서이기도 하다.

## 8. 벤치마크의 타당성

- 예상되는 리뷰 지적 [가정, 예측]:
  - 순환성: 생성기가 넣은 것을 다시 찾을 뿐이다
  - 지름길로 쓸 수 있는 생성기 흔적
  - 실제 자료 없이 손으로 정한 확률
  - 규칙끼리 독립
  - 1년 동안 변화 없음
  - LLM이 쓴 프로필의 다양성 부족
  - 실제 로그로 옮겨지는지 모름
- 관련 연구 AgentSense(AAAI)는 생성 데이터로 학습하고 실제 활동 인식 데이터셋 5개로 시험해서 쓸모를 보였다 [문헌].
- 지금까지 확인한 것 [측정, `tools/pattern_only_lines.py`]:
  - 063에서 패턴만 만드는 로그 줄 종류: 앱으로 공기청정기 60%, 기기 타이머로 0%, SmartThings 앱 열림.
  - 패턴의 조작은 26번 모두 마지막 조건이 참이 된 바로 그 분에 일어났다. 21:00 시간 창 시작 19번, PM2.5 넘음 3번, 창문 닫음 1번, 귀가 3번. 원인은 `time_window`가 조건이 바뀌는 순간에 실행되기 때문이다.
- 문제로 합의했지만 아직 못 고친 것: 즉시 반응하는 시각, 패턴만 쓰는 값, 앱 조작 전 앱 열기.

## 9. Android 에뮬레이터 (결정: 쓰지 않음)

자세한 내용은 `docs/android_emulator_review.md`. 요약:
- 앱 열기 같은 앞 단계를 에이전트가 직접 해야 해서 복잡도가 줄지 않고 옮겨질 뿐이다.
- 로그의 절반 이상(집 복사, 건강, 활동, 장소별 와이파이)은 어차피 우리가 만들어야 한다.
- 콘솔에 시계를 바꾸는 명령이 없고, 실시간으로 돈다.
- 재현성이 없다.
- KVM이 필요하다.
- 실제 앱마다 계정이 필요하다.

## 10. 앱

- 기본 앱 (모든 사람, 16개):
  - KakaoTalk, Chrome, YouTube, Spotify(음악, 팟캐스트), Instagram, Google Maps, SmartThings(기기, 세탁), Calendar, Phone, Messages, Camera, Samsung Health, Samsung Notes, Clock, Reminder(할 일), Weather
  - 근거: 한국 갤럭시 선탑재 앱(Z Fold7 목록) [문헌 Samsung], 한국 월 사용자 상위 앱 [문헌 WiseApp 2024]
- 쓰는 사람만 가진 앱: Coupang, Coupang Eats, NAVER(뉴스), Millie(전자책), Kakao T
- 원문 패턴에 나오는 앱 종류 (사용자가 정리): 출퇴근, 전자책, 세탁, 음악, 노트, 팟캐스트, 뉴스, 쇼핑, 할 일, 영상
- 음악은 Spotify로 했다. 한국 점유율은 YouTube Music 42%, Spotify 14%다 [문헌 WiseApp 2025-04].
- 앱마다 번호(uid)와 데이터 사용량을 고정했다. 새로 정한 데이터 사용량은 추정치다 [가정]. 쿠팡 본 앱 패키지 이름은 쿠팡이츠 패키지에서 추정했다.

## 11. 휴대폰 사용과 화면 모델

**엔진**
- `phone.useApps`:
  - `first`에서 첫 앱을 고르고, `continue` 확률로 `next`의 다른 앱으로 넘어간다.
  - 앱마다 로그정규분포 시간(초) 동안 쓴다. 3,600초에서 자른다.
  - `check.share` 확률로 사용 한 번이 앱 하나, 몇 초짜리 확인이 된다.
- 화면:
  - 휴대폰 사용이 시작되면 켜진다 (앱, 앱 조작, 일정, 거는 전화·보내는 문자, 사진 등).
  - 사용이 끝나면 `manualScreenOff` 확률로 1–3초 안에 직접 끄고, 아니면 `screenTimeoutSeconds` 뒤 꺼진다.
  - 꺼질 때 앞에 있던 앱은 뒤로 간다.
- 잠깐 보기:
  - 앱 없이 화면만 켰다가, 로그정규 시간(중앙값 56초, 평균 88초 [문헌 Hintze 2014]) 뒤 끈다.
  - 전날 쉬던 시간으로 확률을 잡아서 `glancesPerDay`가 실제 하루 횟수가 되게 했다.
- 날마다 차이: 매일 휴대폰 사용 규칙의 빈도에 배율을 곱한다. 로그정규, 평균 1, sigma `dailySigma`.

**사람마다 (`pipeline/sample_phone_person.py`)**

LLM은 `phoneUseLevel`(light / medium / heavy = 하위·가운데·상위 3분의 1)과 상대적인 규칙만 쓴다. 스크립트가 숫자를 뽑고 규칙에 배율을 곱한다.

| 값 | 분포 | 근거 |
|---|---|---|
| 시간당 잠금 해제 | 로그정규, 중앙값 1.71, 사분위 1.10–2.49 (sigma 0.606). 하루 = ×24 | [문헌 Winbush 2025] |
| 시간당 앱 시간 | 로그정규, 중앙값 15.16분, 사분위 10.8–20.6 (sigma 0.479) | [문헌 Winbush 2025] |
| 확인 비율 | 0.25–0.55 균등. 확인 시간 로그정규 중앙값 10초, sigma 0.8 | [가정]. 40초 미만 사용 41% [문헌 arXiv 2609.24477] |
| 한 번에 쓰는 앱 수 | `continue` 0.32 → 68 / 22 / 7% | [문헌 Böhmer 2011: 68.2 / 19.5 / 6.6%] |
| 첫 앱 | 절반쯤 메신저 | [문헌 Böhmer 2011: 통신 앱 49.6%] |
| 직접 끄는 확률 | beta(4.5, 0.5), 평균 0.9 | [가정]. 사람마다 크게 다름 [문헌 Hintze 2014] |
| 잠깐 보기 횟수 | 로그정규, 중앙값 22, sigma 0.90 | [문헌 Hintze 2014: 중앙값 22, 평균 33] |
| 자동 꺼짐 시간 | 15초 10%, 30초 50%, 60초 20%, 120초 10%, 300초 7%, 600초 3% | [가정]. 기본값 30초 [문헌 Samsung] |
| 날마다 sigma | 0.15–0.55 균등 | [문헌 Appiah 2026: 같은 사람 안의 변동계수 16–60%, 대체로 25% 이상] |
| 앱 시간 배율 | 3,600초 자르기를 넣은 평균으로 이분법 탐색 | 커밋 a1d0c42 |

한국 자료로 확인 [문헌]: 하루 앱 사용 5.2시간 (data.ai, 2022년 1분기). 사용자 1인당 KakaoTalk 하루 약 52회·22분, YouTube 하루 약 80분 (와이즈앱 2025, 총량을 월 사용자로 나눈 것은 우리 계산).

**결과** [측정, 커밋 a1d0c42 뒤. 괄호는 목표]

| 수준 | 하루 사용 | 하루 앱 시간(분) | 40초 미만 사용 | 날마다 변동계수 | KakaoTalk 하루 열기 |
|---|---|---|---|---|---|
| light | 16.3 (17) | 146 (155) | 47.7% | 0.30 | 10.7 |
| medium | 33.9 (35) | 298 (311) | 46.6% | 0.22 | 22.8 |
| heavy (063) | 57.6 (60) | 453 (468) | 46.8% | 0.19 | 38.7 |

- 알려진 차이:
  - 앱 하나만 쓴 사용 약 83% (Böhmer 68.2%). 그대로 두기로 합의했다.
  - 5초 미만 약 9% (Böhmer 49.8%, 2011년, 단위가 다름).
  - 앱 시간이 목표의 94–97%.
- 로그 크기 [측정, 배경 로그 하루 500줄 고정]:
  - 화면 모델 전 1년 359,464줄
  - 063 heavy 437,281줄 (+22%, 휴대폰 사용 줄 약 8만)
  - light 361,495줄, medium 394,979줄
  - 파일 151.8 MB → 185.2 MB (heavy)

## 12. 환경(시뮬레이터) 쪽 확인

- Python 포팅 = JS 시뮬레이터: 바깥 값 1e-12, 물리 1e-15 안에서 같음 (`tests/test_port.py`).
- 2026년 날씨와 평년값 [측정]: 월별 최고·최저 기온 0.9°C 안, PM 1.2 µg/m³ 안, 비 온 날 86일(평년 79.3), 강수 1,509 mm(평년 1,418).
- 냉난방 물리 [측정]:
  - 8월 거실 냉방(설정 24°C): 30.2 → 24.0°C, 20분
  - 1월 난방(설정 22°C): 15.0 → 22.0°C, 30분
- 휴대폰 로그만 저장한다(집 로그 따로 없음). SMARTTHINGS 복사본은 다른 필드로 알 수 있는 필드를 빼고 저장하며, `expand()`가 바이트 단위로 똑같이 되살린다.

## 13. 남은 과제

`docs/open_tasks.md` 참고:
- 페르소나에서 캘린더 일정 만들기
- 들어오는 휴대폰 이벤트 (메시지, 전화)
- 조작 전 앱 열기
- 음악·건강·운동의 방법 선택
- JS 실행기에 휴대폰 모델 없음
- 패턴만의 단서와 즉시 반응 시각
- 간격에 따른 끄기 확률
- 페르소나 → 기본 일상 목록

## 참고 문헌

| 줄임 | 문헌 | 쓴 곳 | 읽은 범위 |
|---|---|---|---|
| Winbush 2025 | Winbush A., McDuff D., Hernandez J., Barakat A., Jiang A., Heneghan C., Nelson B. W., Allen N. B. Smartphone use in a large US adult population: Temporal associations between objective measures of usage and mental well-being. PNAS 122(43) e2427311122, 2025. https://doi.org/10.1073/pnas.2427311122 | 사람별 잠금 해제, 앱 시간 (미국 성인 10,099명, Android) | PDF 전체 (사용자 제공) |
| Appiah 2026 | Appiah K. N., Adu N., Singh D. K. Using Fixed-Effects Panel Models to Assess Within-Person Variation in Smartphone Unlocks from Continuous Sensing. Journal of Technology in Behavioral Science, 2026. https://doi.org/10.1007/s41347-026-00691-7 | 날마다 차이 (StudentLife 2013, 대학생 47명). 본문 숫자의 앞뒤가 맞지 않는 곳이 있음 | PDF 전체 (사용자 제공) |
| arXiv 2609.24477 | Beyond Screen Time: Demonstrating the Value of App Activity Logs to Understand User Behavior Further. arXiv 2609.24477, 2026. https://arxiv.org/html/2609.24477v1 | 40초 미만 사용 41.4% (덴마크 13–17세, iOS, 2024) | 웹 페이지 |
| Common Sense 2023 | Common Sense Media. Constant Companion: A Week in the Life of a Young Person's Smartphone Use. 2023. https://www.commonsensemedia.org/sites/default/files/research/report/2023-cs-smartphone-research-report_final-for-web.pdf | 하루 집어 든 횟수 중앙값 51, 4.5시간, 알림 (미국 11–17세, 2022) | 웹 요약 |
| Hintze 2014 | Hintze 외, UbiComp 2014. https://ins.jku.at/publications/2014/Hintze_2014_UbiComp.pdf (제목과 공저자는 확인하지 않음) | 잠깐 보기(잠금 상태 사용), 사용 길이 (Android 1,960대) | 웹 요약 |
| Böhmer 2011 | Böhmer M., Hecht B., Schöning J., Krüger A., Bauer G. Falling Asleep with Angry Birds, Facebook and Kindle: A Large Scale Study on Mobile Application Usage. MobileHCI 2011. https://www.brenthecht.com/papers/bhecht_mobilehci2011_sleepbirds.pdf | 한 번에 쓰는 앱 수, 첫 앱과 다음 앱, 앱 한 번 71.6초 (4,125명) | 웹 요약 |
| Device Analyzer 2017 | How to Measure Sessions of Mobile Device Use? Quantification, Evaluation, and Applications. arXiv 1711.09408. https://arxiv.org/pdf/1711.09408 | 세션 정의(잠금 해제~잠금), 하루 세션 수 (4,017명) | 웹 요약 |
| Turner 2019 | Turner L. 외, Royal Society Open Science, 2019 (Cardiff 대학 보도자료). https://www.cardiff.ac.uk/news/view/1462214-humans-switch-between-apps-in-remarkably-similar-ways,-scientists-find | 하루 앱 전환 87번 (53명) | 보도자료 |
| Rana 2016 | https://www.cl.cam.ac.uk/~acr31/pubs/rana-smartphoneuse.pdf | 하루 앱 실행 38번, 앞 화면 중앙값 88분 (노르웨이 674명, 2013–14) | 웹 요약 |
| Samsung 자동 꺼짐 | Samsung UK 지원 페이지. https://www.samsung.com/uk/support/mobile-devices/how-to-stop-your-galaxy-phone-screen-going-dark-or-timing-out/ | 기본 30초, 최대 10분 | 웹 페이지 |
| Samsung 선탑재 앱 | 삼성전자 탑재 어플리케이션 정보 (SM-F966N). https://www.samsung.com/sec/consumer/mobile/Apps/SM-F966NDBEKOD/ | 기본 앱 목록 | 웹 페이지 |
| WiseApp 2024-11 | MTN 2024-12-17. https://news.mtn.co.kr/news-detail/2024121714574174615 | 한국 월 사용자·사용 시간 상위 앱 | 웹 페이지 |
| WiseApp 2025 | 전자신문 2025-12-30. https://m.etnews.com/20251230000083 | KakaoTalk, YouTube 1인당 | 웹 페이지 |
| WiseApp 2025-04 | 뉴스스페이스. https://www.newsspace.kr/mobile/article.html?no=6969 | 한국 음악 앱 점유율 | 웹 페이지 |
| WiseApp 2024-05 | 뉴시스 2024-06-09. https://mobile.newsis.com/view/NISX20240609_0002765600 | 앱 사용 시간·실행 횟수 총량 | 웹 페이지 |
| data.ai 2022 | 다음뉴스 2022-05-16. https://v.daum.net/v/20220516134848801 | 한국 하루 5.2시간 | 웹 페이지 |
| Gallup 2025 | 한국갤럽, 주방·환경·건강 가전 18종 보유율 2025. https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=1595 | 에어컨 98%, 공기청정기 66%, 가습기 39%, 식기세척기 24%, 오븐 21% | 웹 페이지 |
| Gallup 2023 | 한국갤럽, 마켓70 2023 (7). https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=1439 | 세탁기, 건조기 35%, 로봇청소기 15%, TV 99%, AI 스피커 18% | 웹 페이지 |
| AgentSense | AgentSense: Virtual Sensor Data Generation Using LLM Agents in Simulated Home Environments. AAAI. https://arxiv.org/abs/2506.11773 | 관련 연구: 생성 데이터를 실제 활동 인식 데이터로 검증 | 초록 |
| Android 문서 | 에뮬레이터 콘솔 https://developer.android.com/studio/run/emulator-console · netsim https://developer.android.com/studio/run/emulator-networking-advanced · Android 10 개인정보(클립보드) https://developer.android.com/about/versions/10/privacy/changes | 에뮬레이터 결정 | 웹 페이지 |

읽지 못한 것:
- Ferreira 외 2014 micro-usage: arXiv 2609.24477에 인용된 41.5%만 봤고, 기준 시간은 확인하지 않았다.
- PMC11303118: 10대의 하루 휴대폰 사용과 수면.
- Ohme 외 2021: iOS 스크린타임 데이터 기증. 초록만 봤다.
