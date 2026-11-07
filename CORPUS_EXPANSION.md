# 공식 코퍼스 확장 후보 engineering-v2

기존 88건을 보존한 별도 후보 97건을 만들고 Codex CLI 수용 검사를 마쳤다. 활성 자료실과 실험 기본 경로는 기존 88건이며, 새 후보를 정식 비교에 채택한 것은 아니다.

## 확보와 검증

- 공식 발견 경로: [NASA JPL DESCANSO 목록](https://descanso.jpl.nasa.gov/DPSummary/summary.html). 목록 HTML과 관측한 PDF 주소를 후보 폴더에 보존했다.
- 추가 단위: MGS/Galileo/Odyssey/MER 통신/MER 항법/MRO/MSL 통신/Phoenix/MarCO의 독립된 전체 보고서 9건, 882쪽. 기존 Juno 중복 및 범위 밖 임무는 제외했다. 문서 분할이나 반복 패딩을 쓰지 않았다.
- 88 → 97건, 1,428,935 → 3,060,757자. 추가 본문 1,631,822자. 질문 10건 유지.
- 본문 SHA와 최종 URL 정확 중복 0. 7단어 Jaccard 0.25 이상인 쌍 1개는 기존 Europa Clipper 두 문서이며 추가 보고서와의 새 쌍은 없다. 이 기준이 의미 중복 부재를 보장하지는 않는다.
- 15개 PDF 바이트 해시 및 82개 HTML의 UTF-8/개행 복원 해시 확인. 기존 HTML 수집기는 응답 바이트를 해시한 뒤 Windows 텍스트 쓰기를 하므로 저장 파일의 CRLF를 LF로 복원해 확인했다. 원본 파일과 기존 메타데이터는 수정하지 않았다.
- 기존 88건 본문·기존 링크 보존, 원래 Corpus 로더·질문 힌트 검사 통과. 실제 관측 링크 86개 유지. 목록 페이지의 공통 탐색 링크를 문서간 링크로 만들지 않았다. 추가 보고서는 본문 링크 그래프에서 고립될 수 있으므로 시작 자료 또는 전체 후보 선택 경로가 필요하다.
- 대표 기술 페이지를 문서별 1쪽씩 렌더링하고 발췌 수치와 대조했다. `sample_page_review.json`/`visual_review/`에 보존. 전수 사람 검토는 아니다. 그림에만 있는 수치 누락, 좌표 나열, 선형화된 표, MSL 편집 필드 코드(예: 33B/6T), 사설 문자 등의 추출 한계가 남아 있다. 텍스트 추출 성공을 표·그림 재현 성공으로 쓰지 않는다.
- 화성43건·목성19건·수성13건·금성22건으로 화성 편중. 네 행성의 균형 있는 자료 확장이나 P04의 부족 해소를 주장하지 않는다.

후보: `data/planetary_exploration/versions/engineering-v2/`. `baseline/`에 기존 코퍼스·질문·입력·측정·토크나이저의 스냅샷과 해시를 보존했다. 원본 HTML/PDF는 기존 경로를 공유하며 신규 PDF는 후보의 `raw_pdf/`에 있다.

## 실제 Codex CLI 수용 검사

기록: `output/codex_context_checks/20261106-230646-264874/`. gpt-6.1-sol, 기존 ChatGPT 로그인, 도구 비활성화, 같은 세션 5턴, 공개 원문 97건. 모델·전역 설정·컨텍스트 한도를 변경하지 않았다. `received=true`는 수신 확인이며 원문 기억·이해 평가가 아니다.

| 묶음 | 해당 요청 입력 토큰 | 실행 기록 한도 |
|---|---:|---:|
| 1 | 149156 | 475000 |
| 2 | 271278 | 475000 |
| 3 | 437994 | 475000 |
| 4 | 580318 | 475000 |
| 압축 뒤 5 | 246785 | 475000 |

정확한 해당 세션에서 압축 이벤트 1개를 확인했다. 4번째 요청은 기록상 한도보다 큰 입력을 수용했으므로 475000을 실제 강제 거부 한도라고 단정할 수 없다. 누적 입력 1685531을 전체 본문 크기로 쓰지 않는다. 마지막 요청은 압축 후 보존 컨텍스트이며, 전체 원문이 그대로 공존했다는 증거가 아니다.

결론은 **자동 압축 관측, 과제 초과 조건 미확정**이다. 고립된 전체 본문의 정확한 Codex 토큰 수나 모델의 공개 최대 컨텍스트 초과를 입증하지 못했다. 후보 통계의 794054토큰은 NVIDIA 공식 토크나이저 수치이며 Codex 증거가 아니다. 해당 통계의 NVIDIA 1000000 기준 NOT_MET도 Codex 판정이 아니다. `expansion_audit.json`은 수용 검사 전 무결성 점검 시점의 기록이다.

## 재현

```powershell
.venv/Scripts/python.exe -X utf8 expand_planetary_corpus.py download
.venv/Scripts/python.exe -X utf8 expand_planetary_corpus.py extract
.venv/Scripts/python.exe -X utf8 expand_planetary_corpus.py build
.venv/Scripts/python.exe -X utf8 expand_planetary_corpus.py audit
.venv/Scripts/python.exe -X utf8 check_codex_corpus_fit.py --live --chunked --corpus data/planetary_exploration/versions/engineering-v2/corpus.json
```

download는 공식 PDF 취득이고, 마지막 live는 ChatGPT 로그인 실제 요청이다. extract/build/audit는 오프라인이다. 재측정은 새 기록을 만들고 기존 기록을 덮어쓰지 않는다. 기존 88건의 중간 실행에 97건을 끼워 넣지 않으며, 채택할 때 별도 실험을 시작한다.

다음은 과제의 분량 조건 원문 확인과 이 모델에서 증명 가능한 조건의 정리다. 자동 압축만으로 통과 처리하지 않고 모델·자료·질문·예산을 고정하는 실험 명세를 확정한다. P04의 과도한 부족 신고·중국어 혼입·내부 ID 표기, 웹 CLI 선택 UI, 동일 조건 실제 비교, 제출자의 원문 검토도 미완료다.
