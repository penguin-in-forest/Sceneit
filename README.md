# Sceneit

촬영 원본과 상황 한 줄을 넣으면 AI가 컷 편집과 자막(문구·폰트·효과·색)까지 정해서 세로형 숏폼 영상을 만든다. 결과는 브라우저 편집 화면에서 바로 고칠 수 있다.

```
원본 영상 + 상황 한 줄
  → 1단계: 영상 파악, 스크립트, 쓸 구간 고르기   (Claude)
  → 컷 편집                                       (ffmpeg)
  → 2단계: 자막 문구·시간·위치·폰트·색·효과       (Claude)
  → 편집 화면 등록 → 렌더                         (Remotion)
```

- AI는 소리를 듣지 않고 0.5초마다 뽑은 화면을 보고 판단한다.
- 3~4분 정도의 원본에 맞춰져 있다. 길수록 비용이 늘어난다(2분 20초 원본 → 20초대 결과물 기준 컷 약 $0.9 + 자막 약 $0.4, 채팅으로 고칠 때마다 $0.1~0.2).

## 준비물

- Python 3.10+ (`pip install -r requirements.txt`)
- ffmpeg, ffprobe
  - HDR 원본을 처리하려면 FFmpeg에 `zscale`과 `tonemap` 필터가 필요하다. 해당 필터가 없으면 SDR 원본을 사용한다.
- Node.js 20+
- [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI 로그인 (`claude` 명령)

```bash
pip install -r requirements.txt
cd studio
npm install
python3 scripts/get_fonts.py
```

`get_fonts.py`는 Google Fonts 저장소에서 한글 무료 폰트 35종(OFL)을 `studio/public/fonts/`로 받는다.

## 사용법

```bash
python -m sceneit.run all 내영상 \
  --video clip1.mp4 --video clip2.mp4 \
  --situation "주말에 친구들과 한강에서 자전거를 탔다"
```

결과는 `work/<이름>/<id>.mp4`.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--video` | (필수, 여러 번 가능) | 원본 영상 |
| `--situation` | (필수) | 상황 한 줄. 자막 문구를 직접 적어도 된다 |
| `--preset` | | 말투·규칙·기본값·자동 검사 묶음. `roblox_ko`, `roblox_en` (아래 '프리셋') |
| `--cut` | `minimal` | `minimal`: 원본 순서 유지, 꼭 뺄 부분만 자름 / `paced`: 1.5~4초 컷으로 재구성 / `rhythm`: 10~20초마다 장면 전환 / `flow`: 내용 흐름대로 3~8초마다 |
| `--layout` | `auto` | `cover`: 세로로 꽉 채움 / `fit`: 원본을 가운데 두고 위아래 흐린 배경(프리셋에 따라 검은 여백). `auto`는 세로 영상이면 cover, 가로·정사각이면 fit |
| `--length` | `15~30` | 목표 길이(초) |
| `--style` | `sceneit/assets/style.md` | 말투 파일. 계정 말투를 적어 두면 따라 쓴다 |
| `--rules` | `sceneit/assets/rules.md` | 자막 작성 규칙 |
| `--model` | `claude-opus-5-5` | |
| `--no-render` | | 편집 화면 등록까지만 |

`--cut`, `--length`, `--style`, `--rules`를 직접 주면 프리셋 값보다 우선한다.

단계별로 다시 돌릴 수도 있다. 앞 단계 결과는 `work/<이름>/`에 남는다.

```bash
python -m sceneit.run new 내영상 --video a.mp4 --situation "..."
python -m sceneit.run prep 내영상
python -m sceneit.run plan 내영상
python -m sceneit.run cut 내영상
python -m sceneit.run subs 내영상
python -m sceneit.run export 내영상
python -m sceneit.run render 내영상
```

## 채팅 편집 화면

```bash
python -m sceneit.app        # http://localhost:8000 (Remotion Studio도 3000번에 같이 띄움)
```

- 왼쪽은 편집 화면(Remotion Studio), 오른쪽은 채팅.
- 오른쪽에서 원본 영상과 상황을 넣고 시작하면 단계별로 진행한다.
  1. **컷 편집**: Claude가 쓸 구간을 고르고 자른다. 왼쪽에서 잘린 영상을 본다.
  2. **자막**: Claude가 자막을 넣는다. 왼쪽에서 직접 고쳐도 된다.
  3. **완성**: 최종 mp4를 렌더한다.
- 단계마다 결과가 마음에 들면 **좋아요** 버튼으로 다음 단계, 아니면 채팅으로 고칠 점을 적는다. 그 단계만 다시 돈다.
- 다시 돌릴 때는 같은 Claude 대화를 이어 가서(`claude -p --resume`) 이미 본 화면을 다시 읽지 않는다. 자막 단계에서는 편집 화면에서 직접 고친 내용을 기준으로 고친다.
- 자막 단계에서 **← 컷 다시**로 돌아갈 수 있다. 컷을 다시 고치면 자막은 새로 쓴다.
- 대화와 결과는 `work/<이름>/`(`chat.json`, `plan.json`, `subs.json`)에 남아서 서버를 다시 켜도 이어진다.

## 프리셋

`sceneit/presets/<이름>/`에 말투(`style.md`), 규칙(`rules.md`), 기본값과 자동 검사(`preset.json`)가 있다. 로블록스 프리셋 두 개는 2026-11 인스타그램 로블록스 릴스 1,325개 조사(같은 계정 안 비교)에서 나왔다.

```bash
python -m sceneit.run all 왁뿌 --video play.mp4 --situation "왁뿌 ASMR 맵 구경" --preset roblox_ko
python -m sceneit.run all obby --video play.mp4 --situation "first time in this obby" --preset roblox_en
```

| | `roblox_ko` | `roblox_en` |
|---|---|---|
| 길이 | 20~30초 | 45~60초 |
| 컷 | `rhythm`: 10~20초마다 장면 전환, 10초에 4번 이상 금지 | `flow`: 내용 흐름대로 |
| 가로 원본 | 검은 여백 + 위 여백에 제목 | 검은 여백 + 위 여백에 제목 |
| 자막 | 상단 고정 제목 + 아래쪽 문장형 자막(1인칭 해요체 중계 등) | 상단 제목 + 화면 중앙 대문자 1~3단어 |
| 자동 검사 | 길이, 장면 전환 리듬, 본문 자막 75% 이상·빈 구간 3초 이하, 제목 명확도 점검 | 길이 |

- 1단계가 끝나면 컷 목록으로, 2단계가 끝나면 자막으로 규칙을 검사한다. 걸리면 같은 Claude 대화를 이어 가서 문제 목록만 보내 한 번 다시 만들게 하고, 문제가 더 적은 쪽을 쓴다(그만큼 비용이 든다). 채팅으로 고칠 때도 같은 검사를 한다. 결과는 `plan.json`, `subs.json`의 `checks`에 남는다.
- 장면 전환은 이어지지 않는 컷 경계와, 컷 안에서 원본 화면이 크게 바뀌는 시각(ffmpeg 장면 감지)을 합쳐 센다. 원본의 장면 전환 시각은 `prep` 단계에서 재서 `work/<이름>/scenes.json`에 둔다.
- 본문 자막이 없는 1초 이하 빈틈은 앞 자막을 늘려 자동으로 메운다. 쇼케이스(아바타·스킨·댄스·맵 구경)는 자막 비율 검사를 건너뛴다.
- 인스타 설명란과 해시태그는 `work/<이름>/caption.txt`에 저장된다.
- 자막에 `box`(`black`, `yellow`, `white`)를 주면 배경 박스 자막이 된다(POV 문구, 게임 속 대사).
- 채팅 편집 화면에서는 아직 프리셋을 고를 수 없다. 명령줄로 만든 프로젝트는 채팅 화면에서 이어서 고칠 수 있다.

## 편집 화면

```bash
cd studio
npm run studio
```

- 왼쪽에서 프로젝트를 고른다.
- 아래 타임라인의 자막 막대를 끌면 시간이 바뀐다.
- 막대를 누르면 오른쪽에서 문구, 폰트, 등장·강조·퇴장 효과, 속도, 위치, 크기, 색을 고칠 수 있다.
- 고친 값은 `studio/src/projects/<id>.tsx`에 바로 저장된다. 다시 렌더하면 반영된다.
- 문구에서 `[[이렇게]]` 감싼 부분은 강조색으로 나온다.

## 구성

| 경로 | 내용 |
|---|---|
| `sceneit/run.py` | 명령줄 진입점 |
| `sceneit/app.py`, `sceneit/web/` | 채팅 편집 화면 (FastAPI + 단일 HTML) |
| `sceneit/sheets.py` | 0.5초 간격 프레임을 4장씩 이어 붙인 시트 |
| `sceneit/cut.py` | 고른 구간을 잘라 이어 붙임 (원본 소리 유지) |
| `sceneit/ai.py` | `claude -p` 호출 |
| `sceneit/export.py` | 자막 결과를 편집 화면 파일로 변환 |
| `sceneit/presets.py` | 프리셋 불러오기, 단계별 자동 검사와 재시도 |
| `sceneit/checks.py` | 길이·장면 전환·자막 비율 검사 (`python -m unittest discover -s tests`) |
| `sceneit/scenes.py` | 원본 장면 전환 감지 |
| `sceneit/presets/` | 내장 프리셋 (`roblox_ko`, `roblox_en`) |
| `sceneit/prompts/` | 1단계(`plan.txt`), 2단계(`subs.txt`), 고치기(`revise.txt`) 프롬프트 |
| `sceneit/assets/` | 기본 규칙·말투 |
| `studio/` | Remotion 프로젝트. 자막 효과는 Animate.css |

`claude` 대신 다른 실행 파일을 쓰려면 환경변수 `SCENEIT_CLAUDE`에 경로를 넣는다.
