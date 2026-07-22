# Agent SDD Kit

AI coding agent와 함께 명세 기반 개발을 진행하고, 구현이 끝난 뒤 코드의 현재 동작을 business 문서에 반영하기 위한 실험적 규칙과 Skill 모음이다.

이 저장소는 특정 제품의 자동화 도구가 아니다. Agent가 반복 작업을 비슷한 절차로 수행하도록 안내하는 Markdown 기반 가이드다.

> An experimental, Markdown-based kit for staged SDD scaffolding and PR-time business documentation updates. It was first tested on a legacy Java/Spring application and is intended to be adapted to each repository's entrypoints, call layers, and documentation conventions. The Skill instructions are currently written in Korean.

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

## 현재 검증 상태

- `sdd-doc-scaffold`: 파일 구성, TODO 문구, 문서 관계 표를 고정했다. 실제 feature, 코드 경로, 작업 ID는 치환 자리로 남겨 강한 예시 값이 복사되지 않게 했다.
- `sdd-doc-scaffold`의 본문에는 등급·게이트·Stage 절차만 두고, `Medium` 이상에서 현재 Stage가 확정된 뒤 공통 규칙과 해당 Stage 템플릿만 reference에서 읽는다.
- `sdd-doc-scaffold`는 Stage마다 다시 호출할 수 있다. 골격 생성 뒤의 코드 조사와 내용 작성은 같은 에이전트 또는 후속 세션의 일반 작업으로 수행하고, Stage 완료는 사용자의 명시적인 확인으로 판정한다.
- Stage 3 진입은 as-is 분석과 to-be 설계 및 change plan이 작성되고 사용자 확인까지 끝났다는 의미다.
- `pr-business-docs`: diff에서 시작해 공유 호출 체인의 다른 진입점까지 확장하고, 저장 전 근거 대조로 잘못된 초안을 발견한 경험을 반영했다.
- 기존 문서의 부분 갱신을 기본값으로 두었지만, 같은 방식이 장기간 정보 손실 없이 반복되는지는 더 확인이 필요하다.
- Skill 사용 비용이 매번 코드를 다시 탐색하는 비용보다 항상 작다고 확인한 것은 아니다.

## Skill Eval

`evals/`에는 각 Skill의 대표 입력과 기대 동작을 JSON으로 관리한다. Eval은 세 종류로 나눈다.

- `trigger`: Skill이 선택되어야 하는 요청
- `non-trigger`: 비슷해 보이지만 Skill이 선택되면 안 되는 요청
- `procedure`: Skill이 선택된 뒤 반드시 지켜야 하는 절차와 금지 조건

현재 Eval에는 실제 사용 중 발견한 `내 Codex 사용 패턴을 분석해줘` 요청에서 `sdd-doc-scaffold`가 잘못 실행된 사례를 회귀 테스트로 포함했다.

```bash
python scripts/validate_evals.py
```

이 명령은 JSON 형식, 필수 필드, 중복 ID, 카테고리와 `should_trigger`의 정합성을 검사한다. GitHub Actions도 PR과 `main` push에서 같은 검증을 수행한다.

이 저장소는 특정 Agent의 통합 Eval 실행기를 제공하지 않는다. 실제 모델 평가는 `query`를 대상 Agent에 입력한 뒤 `expected.should_trigger`와 `expected.behaviors`를 기준으로 수동 또는 별도 러너에서 채점한다. Skill 설명이나 절차를 바꿀 때는 기존 Eval을 먼저 실행하고, 새로 발견한 실패 사례를 케이스로 추가한다.

### Eval 실행 안전성

Eval의 `query`는 테스트 전용 모드에서 가상으로 실행되지 않는다. 대상 Agent에 전달하면 일반 사용자 요청과 똑같이 처리되므로 `수정해줘`, `생성해줘`, `갱신해줘` 같은 실행형 문장은 실제 워킹트리를 바꿀 수 있다. 실제로 Non-trigger 확인용 코드 수정 요청을 현재 작업 저장소에서 실행했다가 Java 소스가 수정된 사례가 있었다.

Trigger 여부만 확인하는 smoke case는 다음 기준으로 작성한다.

- 저장소 전체를 탐색할 여지가 없도록 코드 조각이나 입력 범위를 query 안에 직접 제공한다.
- `원인을 분석해줘`처럼 범위가 열려 있는 표현 대신 `아래 코드 조각만 분석해줘`처럼 대상을 고정한다.
- 저장소 파일을 읽거나 수정하지 말고 결과를 응답으로만 제시하도록 명시한다.
- 파일 생성이나 코드 수정이 없어도 Trigger 여부를 판정할 수 있는 요청을 우선한다.

실제 파일 생성·수정 여부나 금지 절차 준수를 확인하는 case는 통합 테스트로 취급한다. 이런 case는 현재 작업 저장소가 아니라 임시 worktree 또는 복제 저장소에서만 실행하고, 실행 전후의 `git status`와 diff를 비교한다. 테스트 변경을 정리할 때도 `git checkout -- <path>`를 바로 실행하면 기존 작업까지 사라질 수 있으므로, diff를 먼저 확인하고 Eval이 만든 변경만 제거한다.

## 설치

사용하는 Agent가 지원하는 Skill 디렉터리에 필요한 폴더 하나를 그대로 복사한다.

```text
skills/
  sdd-doc-scaffold/
  pr-business-docs/
```

각 Skill은 자기 폴더 내부의 `references/`만 참조한다. 저장소 루트나 다른 Skill에 대한 상대경로 의존성은 없다.

Agent별 설치 위치와 발견 방식은 각 제품의 최신 문서를 따른다.

## 사용 예시

### SDD 문서 골격

```text
sdd-doc-scaffold를 사용해서 결제 오류 복구 작업의 SDD 골격을 만들어줘.
작업 등급은 Large, feature는 payment-recovery, ID prefix는 PAY-RECOVERY야.
```

Skill은 코드를 조사하지 않고 생성할 파일과 문서 관계를 먼저 보여준다. 사용자가 확정한 뒤에만 파일을 만든다. 골격 생성 후에는 일반 에이전트 작업으로 내용을 작성하고, 사용자가 해당 Stage의 완료를 확인한 뒤 다음 Stage에서 다시 호출한다.

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

## 배경

이 저장소는 [Agent SDD 실무 개발](https://seok-jun.github.io/ai-agent-diary/series/agent-sdd/) 시리즈에서 진행한 실험을 재사용 가능한 형태로 정리한 것이다.

## License

MIT License. 자세한 내용은 `LICENSE`를 확인한다.
