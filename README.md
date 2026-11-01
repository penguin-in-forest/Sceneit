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
- 3~4분 정도의 원본에 맞춰져 있다. 길수록 비용이 늘어난다(15~30초 결과물 기준 약 $1).

## 준비물

- Python 3.10+ (`pip install -r requirements.txt`)
- ffmpeg, ffprobe
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
| `--cut` | `minimal` | `minimal`: 원본 순서 유지, 꼭 뺄 부분만 자름 / `paced`: 1.5~4초 컷으로 재구성 |
| `--layout` | `auto` | `cover`: 세로로 꽉 채움 / `fit`: 원본을 가운데 두고 위아래 흐린 배경. `auto`는 세로 영상이면 cover, 가로·정사각이면 fit |
| `--length` | `15~30` | 목표 길이(초) |
| `--style` | `sceneit/assets/style.md` | 말투 파일. 계정 말투를 적어 두면 따라 쓴다 |
| `--rules` | `sceneit/assets/rules.md` | 자막 작성 규칙 |
| `--model` | `claude-opus-5-5` | |
| `--no-render` | | 편집 화면 등록까지만 |

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
| `sceneit/sheets.py` | 0.5초 간격 프레임을 4장씩 이어 붙인 시트 |
| `sceneit/cut.py` | 고른 구간을 잘라 이어 붙임 (원본 소리 유지) |
| `sceneit/ai.py` | `claude -p` 호출 |
| `sceneit/export.py` | 자막 결과를 편집 화면 파일로 변환 |
| `sceneit/prompts/` | 1단계(`plan.txt`), 2단계(`subs.txt`) 프롬프트 |
| `sceneit/assets/` | 기본 규칙·말투 |
| `studio/` | Remotion 프로젝트. 자막 효과는 Animate.css |

`claude` 대신 다른 실행 파일을 쓰려면 환경변수 `SCENEIT_CLAUDE`에 경로를 넣는다.
