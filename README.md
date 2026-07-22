# Agent SDD Kit

AI coding agent와 함께 명세 기반 개발을 진행하고, 구현이 끝난 뒤 코드의 현재 동작을 business 문서에 반영하기 위한 실험적 규칙과 Skill 모음이다.

이 저장소는 특정 제품의 자동화 도구가 아니다. Agent가 반복 작업을 비슷한 절차로 수행하도록 안내하는 Markdown 기반 Skill과, 그 Skill의 공통 계약을 Codex와 Claude Code에서 반복 검증하는 참조 Eval Harness를 함께 제공한다.

> An experimental kit for staged SDD scaffolding and PR-time business documentation updates. It includes an executable, cross-harness evaluation template. The Skill instructions are currently written in Korean.

## 포함된 Skill

| Skill | 사용 시점 | 역할 |
|---|---|---|
| `sdd-doc-scaffold` | 작업 시작 | SDD 문서 골격과 Stage 게이트를 고정한다. |
| `pr-business-docs` | 구현 완료 후, PR 전 | 변경된 코드의 호출 관계를 추적해 관련 business 문서를 찾고 갱신한다. |

## 적용 범위

이 규칙은 REST 또는 메시지 기반 진입점에서 Service와 데이터 접근 계층으로 이어지는 레거시 애플리케이션을 기준으로 만들었다.

- Java/Spring 구조에서 처음 검증했다.
- Controller, Handler, Listener, Consumer, Batch Job 등 다른 진입점에도 규칙을 바꿔 적용할 수 있다.
- 저장소마다 business 문서 위치, 호출 계층, 기준 브랜치, 백로그 형식이 다르므로 첫 실행 전에 프로젝트 규칙을 확인해야 한다.
- 전체 개발 방법론이나 모든 프로젝트에 맞는 정답을 주장하지 않는다.

## 저장소 구조

```text
agent-sdd-kit/
├── skills/
│   ├── sdd-doc-scaffold/
│   └── pr-business-docs/
├── evals/
│   ├── harness/
│   │   ├── core.py
│   │   ├── codex.py
│   │   └── claude.py
│   ├── sdd-doc-scaffold/
│   │   ├── prompts.json
│   │   ├── checks.py
│   │   └── fixtures/
│   ├── pr-business-docs/
│   │   ├── prompts.json
│   │   ├── checks.py
│   │   └── fixtures/
│   └── artifacts/                 # 실행 결과, gitignore
├── scripts/
│   ├── validate_eval_specs.py
│   └── run_evals.py
└── tests/
```

Skill을 사용하기만 한다면 `skills/{skill-name}/`만 복사하면 된다. Eval을 재현하거나 프로젝트용 Eval로 확장하려면 저장소 전체가 필요하다.

## 현재 검증 상태

- `sdd-doc-scaffold`: 파일 구성, TODO 문구, 문서 관계 표와 Stage 게이트를 고정했다. 실제 feature, 코드 경로, 작업 ID는 치환 자리로 남겼다.
- `pr-business-docs`: diff에서 시작해 공유 호출 체인의 다른 진입점까지 확장하고, 기존 문서의 부분 갱신을 기본값으로 둔다.
- 두 Skill 모두 10개의 prompt를 `trigger`, `non-trigger`, `procedure`로 나눠 관리한다.
- prompt는 실제 Codex 또는 Claude Code CLI에 전달된다.
- 각 trial은 새 임시 Git 저장소에서 실행되고, 최종 응답·trace·diff·check 결과를 저장한다.
- 같은 prompt와 check ID를 두 Harness에 적용하되 결과는 Harness별로 분리한다.
- 기본 반복 횟수는 케이스당 3회다. 이 결과는 방향성을 보는 용도이며, 배포·회귀 판단에는 5회 실행을 권장한다.

이 검증은 모든 프로젝트에서의 성공을 보증하지 않는다. 기본 Skill이 지켜야 할 공통 계약을 재현하고, 채택자가 프로젝트 전용 fixture와 check를 추가할 수 있게 하는 참조 구현이다.

## Skill Eval 설계

Eval 구조는 Phil Schmid의 가이드에서 제시한 다음 흐름을 따른다.

```text
prompt set
→ 실제 Agent CLI 실행
→ trace·응답·파일 diff 수집
→ expected_checks를 check registry에 연결
→ trial별 통과 여부와 Harness별 결과 저장
```

폴더명이나 JSON 형식은 공식 표준이 아니다. 이 저장소가 채택한 형식은 가이드의 핵심 요소인 작은 prompt set, negative control, 격리 실행, deterministic check, 다회 반복, Harness별 측정을 실제로 연결하기 위한 참조 구조다.

### Prompt schema

각 케이스는 자연어 기대 동작 대신 실행 가능한 check ID를 선언한다.

```json
{
  "id": "trigger-explicit-scaffold",
  "category": "trigger",
  "prompt": "$sdd-doc-scaffold Skill을 사용해서 결제 오류 복구 작업의 SDD 문서 골격을 만들어줘.",
  "should_trigger": true,
  "expected_checks": [
    "skill_triggered",
    "proposes_task_grade",
    "asks_for_confirmation",
    "no_project_files_changed"
  ]
}
```

`checks.py`의 `CHECK_REGISTRY`가 각 ID를 실제 검사 함수에 연결한다.

```python
CHECK_REGISTRY = {
    **common_registry(),
    "proposes_task_grade": proposes_task_grade,
    "does_not_advance_stage": does_not_advance_stage,
}
```

검사 함수는 최종 응답, Agent가 사용한 tool trace, 실행 전후의 변경 경로와 Git diff를 받아 `passed`와 근거를 반환한다. 경로나 파일 존재처럼 코드로 판정할 수 있는 결과를 우선한다. 현재 참조 구현에는 별도 LLM judge를 넣지 않았다.

### 같은 기준과 같은 실행은 다르다

Codex와 Claude Code는 다음을 공유한다.

- 동일한 `prompt`
- 동일한 fixture의 기준 파일과 worktree 변경
- 동일한 `should_trigger`
- 동일한 `expected_checks`
- 동일한 trial 수

CLI 호출, Skill 설치 위치, trace 형식과 권한 모델은 서로 다르므로 adapter는 분리한다.

| 항목 | Codex | Claude Code |
|---|---|---|
| 프로젝트 Skill 위치 | `.agents/skills/{name}/` | `.claude/skills/{name}/` |
| 비대화형 실행 | `codex exec --json` | `claude --print --output-format stream-json` |
| 쓰기 권한 | `--sandbox workspace-write` | `dontAsk` + 제한된 `--tools`·`--allowedTools` |
| 세션 결과 | JSONL event | stream-json message |

따라서 이 저장소는 두 Agent가 같은 결과를 낸다고 가정하지 않는다. 같은 입력과 결과 계약을 적용하되 adapter에서 도구 event를 정규화하고, 결과는 Harness별로 분리한다. 권한 모델과 내장 도구가 완전히 같지는 않으므로 Harness 간 절대 pass rate 차이를 Skill의 우열로 해석하지 않는다. 각 Harness에서 같은 모델·CLI 버전으로 전후 변화를 추적하는 것이 기본 용도이며, Harness 간 비교는 탐색적 신호로만 사용한다.

### Trigger 판정

`skill_triggered`는 최종 답변에 Skill 이름이 포함됐는지를 보지 않는다. 문자열로 직렬화된 trace 전체를 검색하는 대신 구조화된 tool event를 읽는다.

- POSIX와 Windows 경로를 `/`로 정규화한 뒤 대상 `SKILL.md` 읽기를 찾는다.
- `Skill` 도구 호출은 tool 이름과 `input`의 Skill 식별자를 함께 확인한다.
- 사용자 prompt 자체에 Skill 이름이 있어도 tool event가 없으면 trigger로 판정하지 않는다.

with-Skill 실행에 trigger 케이스가 하나 이상 포함됐는데 모든 trial에서 trigger 증거가 0건이면 개별 행동 실패가 아니라 detector 또는 adapter 오류로 보고 run 전체를 `error`로 종료한다. non-trigger 케이스만 선택하면 detector를 검증할 수 없으므로 경고를 출력한다.

CLI 버전에 따라 trace event 형식이 바뀌면 adapter의 추출 규칙도 갱신해야 한다. 결과가 예상과 다르면 먼저 `trace.jsonl`을 확인한다.

## 사전 준비

- Python 3.10 이상
- Git
- 평가할 Harness의 CLI와 인증
  - Codex CLI: `codex`
  - Claude Code CLI: `claude`

이 Harness는 Python 표준 라이브러리만 사용한다. Agent 호출에는 각 제품의 요금, 사용량 제한과 조직 정책이 그대로 적용된다.

## 명세와 Harness 자체 검증

```bash
python scripts/validate_eval_specs.py
python -m unittest discover -s tests -v
```

이 검증은 다음을 확인한다.

- Skill별 prompt가 10~20개인지
- `trigger`, `non-trigger`, `procedure`가 모두 있는지
- `should_trigger`와 category가 일치하는지
- 모든 `expected_checks`가 registry 함수에 연결되는지
- 기본 trial 수가 3~5인지
- 참조한 fixture에 `base/`가 있는지
- CLI command 구성, Windows·Skill tool trigger trace, fixture baseline과 신규 파일 내용을 포함한 diff 수집이 동작하는지

GitHub Actions도 PR과 `main` push에서 이 두 명령을 실행한다. CI는 Agent 계정과 비용이 필요한 실제 Codex·Claude 실행은 하지 않는다. 따라서 CI 통과는 Eval 프로그램과 데이터가 유효하다는 뜻이며, 특정 모델의 실제 pass rate를 뜻하지 않는다.

기존 `python scripts/validate_evals.py`와 `python -m scripts.validate_evals`는 호환용 wrapper로 남아 있지만 새 이름을 사용하는 것을 권장한다.

## Eval 실행

### 한 Harness에서 한 Skill 실행

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness codex \
  --trials 3
```

```bash
python scripts/run_evals.py \
  --skill pr-business-docs \
  --harness claude \
  --trials 3
```

### 두 Harness 비교

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness both \
  --trials 3
```

`--skill`을 생략하면 모든 Skill을 실행한다. `--case`, `--category`로 범위를 줄일 수 있다.

```bash
python scripts/run_evals.py \
  --harness codex \
  --skill pr-business-docs \
  --case trigger-bounded-doc-impact \
  --trials 1
```

`--trials 1`은 runner·adapter 점검용 smoke run이다. 기본 3회 결과는 방향성 신호이며, Skill 변경 채택이나 배포 판단에는 5회를 권장한다.

Runner는 시작 전에 실제 Agent 호출 수와 timeout 기준 최대 누적 시간을 출력한다. 예를 들어 2 Skills × 10 cases × 3 trials × 2 Harnesses는 120회다. 실행은 의도적으로 직렬이다. 병렬 실행은 계정 rate limit과 예상하지 못한 사용량 증가를 만들 수 있어 참조 구현에 포함하지 않았다.

### Skill 미적용 baseline

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness codex \
  --without-skill \
  --trials 3
```

baseline에서는 대상 Skill을 임시 저장소에 설치하지 않고 trigger check를 제외한 결과 check를 실행한다. Skill 적용 결과와 비교하면 모델 자체가 이미 같은 작업을 수행하는지, Skill이 실제 가치를 더하는지 확인할 수 있다.

with-Skill과 without-Skill을 같은 run ID와 조건으로 실행하려면 다음을 사용한다.

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness codex \
  --compare-baseline \
  --trials 5
```

`summary.json`의 `per_check`와 `baseline_deltas`에 check별 양쪽 통과율과 차이가 기록된다. 차이가 없는 행동 check는 판정식이 너무 느슨한지 검토해야 한다. 다만 파일 범위 제한 같은 안전 불변식은 Skill 유무와 상관없이 양쪽이 통과하는 것이 정상일 수 있으므로, delta 0을 모든 check의 자동 실패 조건으로 사용하지 않는다.

### 종료 코드와 임계값

trial 결과는 세 종류로 구분한다.

| 상태 | 의미 |
|---|---|
| `pass` | Agent 실행이 정상 종료되고 모든 행동 check가 통과했다. |
| `fail` | Agent 실행은 정상이지만 하나 이상의 행동 check가 실패했다. |
| `error` | CLI 비정상 종료, timeout 또는 trigger detector 무결성 오류가 발생했다. |

통과율을 측정하는 기본 실행은 행동 실패가 있어도 종료 코드 0을 반환하고, 인프라 오류는 2를 반환한다. CI에서 회귀 임계값을 적용하려면 `--min-pass-rate`를 지정한다.

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness codex \
  --trials 5 \
  --min-pass-rate 0.8
```

측정 조건의 pass rate가 80% 미만이면 종료 코드 1을 반환한다. `--compare-baseline`에서는 with-Skill 결과에 임계값을 적용한다.

### 명령 구성만 확인

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness both \
  --case trigger-explicit-scaffold \
  --trials 1 \
  --dry-run
```

`--dry-run`은 fixture와 CLI command만 준비하고 Agent를 호출하지 않는다.

## 격리와 권한

모든 trial은 다음 순서로 준비된다.

1. fixture의 `base/`를 새 임시 디렉터리에 복사한다.
2. 대상 Harness의 프로젝트 Skill 경로에 Skill을 설치한다.
3. 이 상태를 임시 Git 저장소의 baseline commit으로 만든다.
4. fixture의 `worktree/`를 덮어써 테스트용 변경사항을 만든다.
5. Agent를 실행하고 baseline 대비 변경 파일과 diff를 수집한다.
6. 기본값에서는 임시 저장소를 삭제한다.

이 방식은 케이스 간 파일과 대화 문맥의 누적을 막는다. 하지만 임시 Git 저장소가 운영체제 수준 sandbox는 아니다.

- Codex adapter는 `--ephemeral --sandbox workspace-write --ignore-user-config`를 사용한다.
- Claude adapter는 `--dangerously-skip-permissions`를 사용하지 않고 `dontAsk`, project 설정 source, 제한된 built-in tools, 필요한 Git·`rg` allow-list, strict MCP 설정을 사용한다.
- Runner는 같은 이름의 사용자 전역 Skill(`~/.agents/skills`, 이전 Codex 경로인 `~/.codex/skills`, `~/.claude/skills`)을 발견하면 기본적으로 중단한다. 오염 가능성을 알고도 실행하려면 `--allow-global-skill`을 명시한다.
- 관리형 정책과 CLI 자체의 내장 동작은 여전히 결과에 영향을 줄 수 있다.
- 엄격한 재현성과 host 격리가 필요하면 깨끗한 CLI profile, dev container, container 또는 VM 안에서 runner를 실행한다.
- 실제 회사 저장소를 fixture로 복사하지 않는다. 공개 가능한 최소 재현 코드만 만든다.

## 결과 artifact

결과는 기본적으로 다음 위치에 저장된다.

```text
evals/artifacts/{run-id}/
├── summary.json
├── with-skill/
│   └── {harness}/{skill}/{case}/trial-{n}/
│       ├── trace.jsonl
│       ├── stderr.txt
│       ├── response.md
│       ├── workspace.diff
│       └── result.json
└── without-skill/                  # baseline 실행 시
```

`result.json`에는 실행 조건, 요청 모델, CLI 버전, prompt set 버전, timeout, trial, exit code, token usage, 변경 경로, check별 판정과 근거가 들어간다. `summary.json`은 다음 재현성 정보와 집계를 추가한다.

- repository commit과 Skill 디렉터리 SHA-256
- Harness별 CLI 버전과 요청 모델
- with-Skill / without-Skill 조건
- timeout과 실제/default trial 설정
- pass / fail / error 수
- Harness·Skill·조건별 통과율
- check별 통과율과 baseline delta
- Harness·조건별 token usage 합계
- trigger detector gate 결과

신규 파일은 `git add --intent-to-add` 후 diff를 수집하므로 `workspace.diff`에 파일명뿐 아니라 실제 내용도 남는다. 실패를 고칠 때는 최종 응답만 보지 말고 trace와 diff를 함께 확인한다.

## 배포 전 smoke gate

명세·단위 테스트만 통과한 상태와 실제 실행 검증을 구분한다. adapter, CLI flag, Skill 설치 경로 또는 trace parser를 변경한 PR은 merge 전에 다음 최소 실행을 각 Harness에서 수행하고 생성된 artifact를 PR에 첨부한다.

```bash
python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness codex \
  --case trigger-explicit-scaffold \
  --trials 1

python scripts/run_evals.py \
  --skill sdd-doc-scaffold \
  --harness claude \
  --case trigger-explicit-scaffold \
  --trials 1
```

이 smoke gate는 CLI가 argv를 받아 prompt를 실행하고, 프로젝트 Skill을 발견하며, trace parser가 실제 event 형식을 읽는지 확인한다. CI의 명세·단위 테스트만으로 이 조건을 대체하지 않는다.

## 프로젝트 전용 Eval 추가

배포자가 제공하는 Eval은 공통 계약만 검증한다. Skill을 프로젝트 규칙에 맞게 수정했다면 해당 변경을 검증하는 로컬 Eval도 추가해야 한다.

1. `evals/{skill}/fixtures/{project-case}/base/`에 공개 가능한 최소 기준 파일을 둔다.
2. 변경 전후 비교가 필요하면 `worktree/`에 변경 파일만 같은 경로로 둔다.
3. `checks.py`에 결과 중심의 작은 검사 함수를 추가한다.
4. `CHECK_REGISTRY`에 ID를 등록한다.
5. `prompts.json`에 실제 사용 prompt와 `expected_checks`를 추가한다.
6. 명세 검증, 1회 smoke run, 3~5회 본 실행 순서로 확인한다.

예를 들어 프로젝트가 business 문서를 `docs/features/{feature}/BUSINESS.md`에 둔다면 특정 샘플 문장을 강제하기보다 다음 결과를 검사한다.

- 변경된 진입점과 연결된 문서만 후보가 됐다.
- 사용자 확인 전에는 문서를 수정하지 않았다.
- 저장 후 변경 경로가 합의한 business 문서로 제한됐다.
- 코드와 SDD 파일은 수정되지 않았다.

Agent가 예상과 다른 경로로 같은 결과를 만들 수 있으므로 가능한 한 수행 절차보다 산출 결과를 채점한다.

## Eval 개선 루프

이 저장소가 제공하는 범위는 재현 가능한 실행과 채점까지다.

```text
Skill 수정
→ Codex·Claude Eval 실행
→ 실패 trace와 diff 확인
→ 실패 원인을 새 case 또는 check로 고정
→ Skill 수정
→ 전체 prompt set 재실행
→ pass rate와 비용을 Harness별로 비교
```

Agent가 Skill 파일을 자동으로 고치고 결과가 좋아질 때까지 반복하는 자동 최적화 loop는 제공하지 않는다. Agent의 수정 제안은 참고할 수 있지만, 채택 여부는 전체 Eval 재실행 결과로 판단한다.

## 설치

사용하는 Agent가 지원하는 Skill 디렉터리에 필요한 폴더 하나를 그대로 복사한다.

```text
skills/
  sdd-doc-scaffold/
  pr-business-docs/
```

각 Skill은 자기 폴더 내부의 `references/`만 참조한다. 저장소 루트나 다른 Skill에 대한 상대경로 의존성은 없다. Agent별 설치 위치와 발견 방식은 각 제품의 최신 문서를 따른다.

## 사용 예시

### SDD 문서 골격

```text
sdd-doc-scaffold를 사용해서 결제 오류 복구 작업의 SDD 골격을 만들어줘.
작업 등급은 Large, feature는 payment-recovery, ID prefix는 PAY-RECOVERY야.
```

Skill은 코드를 조사하지 않고 생성할 파일과 문서 관계를 먼저 보여준다. 사용자가 확정한 뒤에만 파일을 만든다.

### PR business 문서 갱신

```text
pr-business-docs를 사용해서 현재 변경으로 오래된 business 문서를 찾아 갱신해줘.
비교 기준과 대상 문서는 저장 전에 먼저 보여줘.
```

Skill은 비교 기준, 동작 변경 파일, 진입점, 관련 문서 후보를 먼저 출력하고 확인받는다. 그다음 코드를 읽어 문서 초안을 만들며, 코드 수정이나 PR 생성은 하지 않는다.

## 프로젝트에 연결하기

`examples/`의 짧은 조각을 프로젝트의 `AGENTS.md` 또는 `CLAUDE.md`에 맞게 옮긴다.

프로젝트별로 달라지는 항목은 다음과 같다.

- 기본 브랜치와 PR 비교 기준
- business 문서의 위치와 이름 규칙
- 외부 요청을 받는 진입점 유형
- 호출 체인의 계층과 종료 지점
- SDD 백로그 위치와 변경 파일 섹션 이름
- 실행 가능한 빌드·테스트 명령

이 값들을 Skill 본문에 하드코딩하지 않는다. 프로젝트 지침이나 사용자 입력에서 확인한다.

## 안전 원칙

- 코드에서 근거를 확인하지 않은 동작을 business 문서에 사실처럼 쓰지 않는다.
- 기존 문서는 기본적으로 변경된 동작과 직접 닿은 부분만 갱신한다.
- 전체 재작성은 이유와 범위를 제시하고 사용자 확인을 받은 뒤 수행한다.
- 문서 갱신 중 발견한 코드 문제는 보고만 하며 임의로 수정하지 않는다.
- 실제 프로젝트에서 생성한 문서를 공개하기 전에는 회사명, 내부 URL, 패키지명, 토픽, 테이블, 환경 이름, 업무 식별자를 별도로 검사한다.

## 참고 기준

이 Eval Harness는 다음 자료를 기준으로 설계했다.

| 기준 | 이 저장소에 반영한 내용 | URL |
|---|---|---|
| Phil Schmid, Practical Guide to Evaluating and Testing Agent Skills | 10~20개 prompt, negative test, deterministic check registry, 케이스 격리, 3~5회 반복, Harness별 실행, Skill 미적용 baseline | https://www.philschmid.de/testing-skills |
| OpenAI, Testing Agent Skills Systematically with Evals | `codex exec --json`, JSONL trace 수집, deterministic grader, artifact 저장, 결과 중심 검사 | https://developers.openai.com/blog/eval-skills |
| OpenAI, Non-interactive mode | Codex CLI의 스크립트 실행과 JSONL event 형식 | https://developers.openai.com/codex/non-interactive-mode |
| OpenAI, Build skills | 현재 Codex 프로젝트·사용자 Skill 위치 | https://developers.openai.com/codex/build-skills |
| Claude Code CLI reference | `--print`, `stream-json`, `--no-session-persistence`, permission mode와 tool allow-list | https://code.claude.com/docs/en/cli-reference |
| Claude Code Skills | 프로젝트 Skill 발견 위치와 Skill 호출 방식 | https://code.claude.com/docs/en/skills |
| Claude Code sandbox environments | 임시 workspace와 OS·container 수준 격리의 차이 | https://code.claude.com/docs/en/sandbox-environments |
| Agent Skills specification | `SKILL.md`, `scripts/`, `references/`, `assets/`로 구성되는 공통 Skill 형식 | https://agentskills.io/specification |

Phil Schmid의 글은 공식 패키지 규격이 아니라 실전 Eval 구현 가이드다. 따라서 이 저장소는 해당 글과 동일한 공식 표준을 주장하지 않고, 그 글의 검증 원칙을 Codex와 Claude Code에 적용한 참조 템플릿이라고 표현한다.

## 배경

이 저장소는 [Agent SDD 실무 개발](https://seok-jun.github.io/ai-agent-diary/series/agent-sdd/) 시리즈에서 진행한 실험을 재사용 가능한 형태로 정리한 것이다.

초기 Eval 명세의 배경은 [Skill 검증을 위한 Eval, 직접 돌려보았다](https://seok-jun.github.io/ai-agent-diary/series/agent-sdd/008-skill-eval-validation/)에서 확인할 수 있다.

## License

MIT License. 자세한 내용은 `LICENSE`를 확인한다.
