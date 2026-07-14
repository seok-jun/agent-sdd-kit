# Agent SDD Kit

AI coding agent와 함께 명세 기반 개발을 진행하고, 구현이 끝난 뒤 코드의 현재 동작을 business 문서에 반영하기 위한 실험적 규칙과 Skill 모음이다.

이 저장소는 특정 제품의 자동화 도구가 아니다. Agent가 반복 작업을 비슷한 절차로 수행하도록 안내하는 Markdown 기반 가이드다.

> An experimental, Markdown-based kit for staged SDD scaffolding and PR-time business documentation updates. It was first tested on a legacy Java/Spring application and is intended to be adapted to each repository's entrypoints, call layers, and documentation conventions. The Skill instructions are currently written in Korean.

## 포함된 Skill

| Skill | 사용 시점 | 역할 |
|---|---|---|
| `sdd-doc-scaffold` | 작업 시작 | SDD 분석·설계 문서의 빈 골격을 단계별로 만든다. |
| `pr-business-docs` | 구현 완료 후, PR 전 | 변경된 코드의 호출 관계를 추적해 관련 business 문서를 찾고 갱신한다. |

## 적용 범위

이 규칙은 REST 또는 메시지 기반 진입점에서 Service와 데이터 접근 계층으로 이어지는 레거시 애플리케이션을 기준으로 만들었다.

- Java/Spring 구조에서 처음 검증했다.
- Controller, Handler, Listener, Consumer, Batch Job 등 다른 진입점에도 규칙을 바꿔 적용할 수 있다.
- 저장소마다 business 문서 위치, 호출 계층, 기준 브랜치, 백로그 형식이 다르므로 첫 실행 전에 프로젝트 규칙을 확인해야 한다.
- 전체 개발 방법론이나 모든 프로젝트에 맞는 정답을 주장하지 않는다.

## 현재 검증 상태

- `sdd-doc-scaffold`: 파일 구성과 문서 연결 구조를 반복 생성해봤다. 강한 예시 값이 그대로 복사될 수 있어 템플릿에는 치환 자리만 남겼다.
- `sdd-doc-scaffold`는 Stage마다 다시 호출할 수 있다. Stage 완료는 파일 상태가 아니라 사용자의 명시적인 확인으로 판정한다.
- `pr-business-docs`: diff에서 시작해 공유 호출 체인의 다른 진입점까지 확장하고, 저장 전 근거 대조로 잘못된 초안을 발견한 경험을 반영했다.
- 기존 문서의 부분 갱신을 기본값으로 두었지만, 같은 방식이 장기간 정보 손실 없이 반복되는지는 더 확인이 필요하다.
- Skill 사용 비용이 매번 코드를 다시 탐색하는 비용보다 항상 작다고 확인한 것은 아니다.

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

## 배경

이 저장소는 [Agent SDD 실무 개발](https://seok-jun.github.io/ai-agent-diary/series/agent-sdd/) 시리즈에서 진행한 실험을 재사용 가능한 형태로 정리한 것이다.

## License

MIT License. 자세한 내용은 `LICENSE`를 확인한다.
