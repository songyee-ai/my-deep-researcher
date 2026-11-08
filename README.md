# my-deep-researcher — 행성 탐사 딥리서처

질문 하나를 코디네이터가 **내용 단위 절**로 나누고, 연구원 서브에이전트들이 공식 원문을 나눠 읽어 각자 절을 쓴 뒤, 종합 단계가 원고만 받아 장문 보고서로 잇는 LangGraph 파이프라인입니다. 자료는 수성·금성·화성·목성 무인 탐사에 관한 NASA·ESA 공식 문서입니다.

설계·지표·실험 결과·회고는 [REPORT.md](REPORT.md)에 있습니다.

```
질문 → ① plan(목차·역할·시작 자료·예산 배정, 배정 검증)
     → ② researcher × N 동시 파견(남의 구역 공유, 원문은 연구원에게만)
     → ③ inspect(부족 신고한 절만 재파견, 바퀴 상한, 두 번째 원고 채택 규칙)
     → ④ synthesize(원고만 받아 종합)
     → ⑤ 측정(정답표 없는 지표 + 스위치를 하나씩 끈 비교 + 단일 에이전트 대조군)
```

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `data/planetary_exploration/` | 기본 코퍼스 88건(`corpus.json`: 문서·링크), `questions.json`(질문 10건과 "왜 나눌 만한가") |
| `data/planetary_exploration/versions/engineering-v2/` | 정식 비교에 쓴 확장 코퍼스 97건 |
| `config.json` | 도메인에 묶인 값: 절 수·절 예산·재조사 상한·최소 분량·역할 명단·스위치 |
| `graph.py` | 기획 → 배치 → 연구원 → 점검 → 종합 (LangGraph) |
| `metrics.py` | 지표. 정답표·판정 모델을 쓰지 않음 |
| `ablation.py` | 스위치(역할·시작 자료·구역·재조사)를 하나씩 끄는 비교 실험 |
| `baseline.py` | 단일 에이전트 대조군(같은 도구·같은 읽기 예산, 예산 소진 여부 검증) |
| `codex_graph.py`, `codex_cli_bridge.py`, `structured_facts.py` | Codex CLI 모델 연결, 줄 번호 사실표 읽기, 실행 조건별 엔진 생성 |
| `run_codex_comparison.py` | 실제 모델로 비교 실험을 돌리는 실행기(중단 후 이어 돌리기 지원) |
| `server.py`, `web/` | 로컬 웹 데모 |
| `output/codex_comparisons/` | 비교 실험 기록: `manifest.json`·`runs.jsonl`·`ablation.json`·`reports/` |
| `output/engineering_runs/` | 기능 진단 실행 기록과 검토 메모 |

## 설치 (Windows PowerShell)

[uv](https://docs.astral.sh/uv/)가 필요합니다.

```powershell
.\setup.ps1
```

Python 3.12 가상환경(`.venv`)을 만들고 `requirements.txt`를 설치합니다.

## 웹 데모 실행

```powershell
.\start.ps1 -Port 8787
```

브라우저에서 http://127.0.0.1:8787/ 을 엽니다. 저장된 기록을 여는 화면은 모델을 부르지 않습니다.

**새 연구 돌려 보기(선택)**: `.env`에 OpenRouter 키를 넣으면 첫 화면에서 질문을 입력해 새 연구를 실행할 수 있습니다. 무료 모델만 쓰며, 모델은 메인 화면 질문 입력줄 옆 목록에서 고릅니다.
- 기본은 `nvidia/nemotron-3.5-super-vl:free`입니다. Dots, Gemma도 고를 수 있습니다.
- 구조화 출력을 지원하는 모델에는 목차 단계에 실제 문서·역할 목록과 절 수를, 다음 문서 고르기 단계에 후보 목록을 응답 형식으로 강제합니다.
- 목차가 검사에서 거부되면, 모델에 이유를 알려 주고 한 번만 다시 쓰게 합니다.
- 조사 노트의 발췌가 원문에 없거나 형식이 깨지면 그 연구원만 한 번 다시 읽습니다. 또 틀리면 그 문서의 근거만 빼고 부족으로 신고하며, 다른 연구원은 계속 진행합니다. 지어낸 발췌는 통과시키지 않고, 이 과정은 실행 기록에 남습니다.
- 무료 모델은 붐비면 "요청 제한(429)"으로 멈출 수 있습니다. 이때는 다른 모델을 고릅니다.
- 웹에서 돌린 새 연구의 내용 품질은 검증하지 않았습니다. 정식 실험 결과는 Codex로 돌린 것입니다.

- **탐사 자료실 → 공식 원문**: 문서 본문, 출처 URL, 문서 사이 링크
- **연구 질문**: 질문 10건과 분업이 필요한(또는 불필요한) 이유
- **실행과 실패 추적**: 절마다 어느 연구원이 어떤 원문을 읽고 어떤 사실표·원고를 썼는지, 경보와 실패 분석
- **비교 실행 결과**: 같은 질문·같은 반복의 조건별 보고서를 나란히 보기. 단일 대조군의 예산 소진 여부, 0이 아닌 경보를 강조합니다. 점수나 순위는 매기지 않습니다.

## 비교 실험 다시 돌리기 (선택)

실험은 [Codex CLI](https://github.com/openai/codex)를 ChatGPT 로그인으로 사용합니다(API 키 과금 경로는 쓰지 않음). 실행 전에 확인합니다.

```powershell
codex login status   # "Logged in using ChatGPT" 이어야 함
```

`codex`가 PATH에 없으면 설치 위치를 PATH 앞에 붙입니다. Codex 데스크톱 앱만 설치했다면 앱 폴더의 `app\resources` 아래에 `codex.exe`가 있습니다.

```powershell
.venv\Scripts\python.exe -X utf8 run_codex_comparison.py --live --scope formal `
  --corpus-dir data/planetary_exploration/versions/engineering-v2 `
  --questions P01,P04,P08 --repeats 2 --sections 3 --budget 2 --rounds 1
```

- 결과는 `output/codex_comparisons/<시각>-<꼬리표>/`에 쌓입니다.
- ChatGPT 사용 한도에 걸리면 그 자리에서 멈추고 `manifest.json`에 `stopped_usage_limit`로 남습니다. 한도가 풀린 뒤 같은 설정으로 이어 돌립니다. 완료된 실행은 다시 부르지 않습니다.

```powershell
.venv\Scripts\python.exe -X utf8 run_codex_comparison.py --live --resume output/codex_comparisons/<폴더>
```

## 키와 비용

- 저장소에는 API 키가 없습니다. OpenRouter 경로를 쓰려면 프로젝트 루트에 `.env`를 만들고 `OPENROUTER_API_KEY`만 넣습니다(`.env.example` 참고). 비교 실험 자체는 이 키를 쓰지 않습니다.
- 공개 배포는 하지 않았습니다. 데모는 로컬 실행용입니다.
