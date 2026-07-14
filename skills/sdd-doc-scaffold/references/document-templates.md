# SDD 문서 템플릿

템플릿의 `{...}`는 사용자가 제공하거나 이전 Stage에서 확정한 값으로만 치환한다. `TODO`는 후속 분석·설계 작업이 채울 자리이며 scaffold 단계에서는 그대로 둔다.

## 공통 문서 관계 표

각 파일의 제목 바로 아래에 둔다.

```markdown
| 항목 | 값 |
|---|---|
| 문서 종류 | {이 파일의 문서 종류} |
| feature | {feature} |
| 작업 ID | {작업 ID 또는 해당 없음} |
| 선행 문서 | {확정된 선행 문서 링크 또는 없음} |
| 후속 문서 | {생성된 후속 문서 링크 또는 미정} |
| 관련 코드 | {사용자가 제공한 코드 범위} |
```

as-is 문서에만 다음 두 행을 추가한다.

```markdown
| 기준 ref | {기준 ref} |
| 작성일 | {작성일} |
```

## Stage 1

### README.md

```markdown
# {feature} SDD

{README용 문서 관계 표}

## 목적
> TODO: 이 SDD가 고정하려는 것 한 문단.

## 기준 자료
> TODO: as-is 코드 진입점, TO-BE 명세 위치, 불명확 항목 확인 방법.

## 문서 구성
| 문서 | 내용 | 상태 |
|---|---|---|
| [01-as-is-flow.md](./01-as-is-flow.md) | 현행 흐름 | 작성 중 |
| 02-to-be-mapping.md | 목표 매핑 | 미생성 |

## 작업 원칙
> TODO: 유지할 스택/제약, 우선 사용할 기존 구조, 변경 금지 대상.
```

### 01-as-is-flow.md

```markdown
# {feature} - 현행 흐름

{as-is용 문서 관계 표와 기준 ref·작성일}

## 처리 흐름
> TODO: 진입점 -> 비즈니스 처리 -> 데이터 또는 외부 호출 흐름.

## 참고한 business 문서
> TODO: 경로와 기준 ref. 없으면 "없음". 존재를 확인하기 전에는 링크하지 않는다.

## 위험 지점
> TODO: 잘못 변경하면 기존 동작이 깨질 수 있는 지점.

## 확인 못 한 것
> TODO: 코드만으로 판단할 수 없는 항목. 없으면 "없음".
```

## Stage 2

### 02-to-be-mapping.md

```markdown
# {feature} - TO-BE 매핑

{to-be용 문서 관계 표}

| 작업 ID | 업무 | TO-BE | 현행 | 판정 | 변경 계획 |
|---|---|---|---|---|---|
| {PREFIX}-{NN} | TODO | TODO | TODO | TODO | {생성된 경우에만 상대 링크} |

판정 기준: 매칭 / 변경 필요 / 신규 필요 / 확인 필요
```

### change-plans/README.md

```markdown
# Change plans

{change-plan index용 문서 관계 표}

| 작업 ID | 제목 | 상태 | 문서 |
|---|---|---|---|
| {PREFIX}-{NN} | TODO | TODO | {생성된 경우에만 상대 링크} |
```

### change-plans/{PREFIX}-{NN}.md

```markdown
# {PREFIX}-{NN}. {제목}

{change-plan용 문서 관계 표}

## 변경 대상
> TODO: 수정 / 참고 / 변경 금지 파일을 구분한다.

## 변경 내용
> TODO: 확정된 설계와 변경 범위.

## 검증 방법
> TODO: 구현 후 확인할 테스트와 회귀 범위.
```

## Stage 3

### backlog/{PREFIX}-{NN}.md

```markdown
# {PREFIX}-{NN} Backlog

{backlog용 문서 관계 표}

## Todo
- [ ] TODO

## Blocked
- 없음

## 변경 파일
- 대기

## Done
- 대기
```

`## 변경 파일`에는 구현하면서 저장소 루트 기준 경로를 적는다. 클래스명이나 메서드명만 적지 않는다.

### implementation-backlog.md

```markdown
# 구현 백로그

{통합 backlog용 문서 관계 표}

| 작업 ID | 기능 | 우선순위 | 상태 | 선행 조건 |
|---|---|---|---|---|
| {PREFIX}-{NN} | TODO | TODO | TODO | TODO |
```
