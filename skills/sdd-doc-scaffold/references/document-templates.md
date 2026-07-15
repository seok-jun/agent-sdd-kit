# SDD 문서 템플릿

`sdd-doc-scaffold`가 현재 Stage의 문서 구조를 제안하거나 파일을 생성할 때 읽는 필수 reference다.

전체 파일을 매번 읽지 않는다. `공통 규칙`과 현재 Stage 섹션만 읽는다. 현재 Stage 섹션은 해당 `## Stage N` 제목부터 다음 `## Stage` 제목 직전까지다.

## 공통 규칙

- `{...}`는 사용자가 제공하거나 이전 Stage에서 확인한 값으로만 치환한다.
- `> TODO:` 뒤 문장과 표·목록의 `TODO`는 scaffold 단계에서 바꾸지 않는다.
- 모든 문서는 제목 바로 아래에 문서 관계 표를 둔다.
- 아직 생성되지 않은 문서는 파일명만 적고 링크하지 않는다.
- 같은 Stage에서 함께 생성하는 문서는 상대 링크를 사용할 수 있다.
- 후속 문서가 실제로 생성되면 선행 문서의 후속 링크와 루트 README의 문서 구성 표를 확인 목록에 포함해 갱신한다.
- 같은 변경 항목은 to-be 매핑, change plan, backlog에서 동일한 작업 ID를 사용한다.
- 제목 구분자는 ASCII 하이픈 `-`, 흐름 화살표는 `->`를 사용한다. em dash와 유니코드 화살표를 사용하지 않는다.

파일별 선행 관계는 다음과 같다.

| 파일 | 선행 문서 |
|---|---|
| `README.md` | 없음 |
| `01-as-is-flow.md` | `[README.md](./README.md)` |
| `02-to-be-mapping.md` | `[01-as-is-flow.md](./01-as-is-flow.md)` |
| `change-plans/README.md` | `[02-to-be-mapping.md](../02-to-be-mapping.md)` |
| `change-plans/{PREFIX}-{NN}.md` | `[02-to-be-mapping.md](../02-to-be-mapping.md)` |
| `backlog/{PREFIX}-{NN}.md` | `[change-plans/{PREFIX}-{NN}.md](../change-plans/{PREFIX}-{NN}.md)` |
| `implementation-backlog.md` | `[02-to-be-mapping.md](./02-to-be-mapping.md)` |

## Stage 1

### README.md

```markdown
# {feature} SDD

| 항목 | 값 |
|---|---|
| 문서 종류 | README |
| feature | {feature} |
| 작업 ID | 해당 없음 |
| 선행 문서 | 없음 |
| 후속 문서 | [01-as-is-flow.md](./01-as-is-flow.md) |
| 관련 코드 | {사용자가 제공한 코드 범위} |

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

README의 문서 구성 상태는 다음 관리값을 사용한다.

- 파일이 없으면 `미생성`
- 골격을 만들었지만 내용 작성과 사용자 완료 확인이 끝나지 않았으면 `작성 중`
- 내용 작성 후 사용자가 Stage 완료를 확인했으면 `완료`

### 01-as-is-flow.md

```markdown
# {feature} - 현행 흐름

| 항목 | 값 |
|---|---|
| 문서 종류 | as-is |
| feature | {feature} |
| 작업 ID | 해당 없음 |
| 선행 문서 | [README.md](./README.md) |
| 후속 문서 | 미정 |
| 관련 코드 | {사용자가 제공한 코드 범위} |
| 기준 ref | {기준 ref} |
| 작성일 | {작성일} |

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

| 항목 | 값 |
|---|---|
| 문서 종류 | to-be |
| feature | {feature} |
| 작업 ID | 해당 없음 |
| 선행 문서 | [01-as-is-flow.md](./01-as-is-flow.md) |
| 후속 문서 | [change-plans/README.md](./change-plans/README.md) |
| 관련 코드 | {사용자가 제공한 코드 범위} |

| 작업 ID | 업무 | TO-BE | 현행 | 판정 | 변경 계획 |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

판정 기준: 매칭 / 변경 필요 / 신규 필요 / 확인 필요
```

작업 ID와 change plan 링크는 항목과 파일이 확인된 뒤에만 입력한다.

### change-plans/README.md

```markdown
# Change plans

| 항목 | 값 |
|---|---|
| 문서 종류 | change-plan-index |
| feature | {feature} |
| 작업 ID | 해당 없음 |
| 선행 문서 | [02-to-be-mapping.md](../02-to-be-mapping.md) |
| 후속 문서 | 미정 |
| 관련 코드 | {사용자가 제공한 코드 범위} |

| 작업 ID | 제목 | 상태 | 문서 |
|---|---|---|---|
| TODO | TODO | TODO | TODO |
```

### change-plans/{PREFIX}-{NN}.md

확정된 작업 ID에 대해서만 만든다.

```markdown
# {PREFIX}-{NN}. {제목}

| 항목 | 값 |
|---|---|
| 문서 종류 | change-plan |
| feature | {feature} |
| 작업 ID | {PREFIX}-{NN} |
| 선행 문서 | [02-to-be-mapping.md](../02-to-be-mapping.md) |
| 후속 문서 | 미정 |
| 관련 코드 | {사용자가 제공한 코드 범위} |

## 변경 대상
> TODO: 수정 / 참고 / 변경 금지 파일을 구분한다.

## 변경 내용
> TODO: 확정된 설계와 변경 범위.

## 검증 방법
> TODO: 구현 후 확인할 테스트와 회귀 범위.
```

## Stage 3

### backlog/{PREFIX}-{NN}.md

확정된 작업 ID에 대해서만 만든다.

```markdown
# {PREFIX}-{NN} Backlog

| 항목 | 값 |
|---|---|
| 문서 종류 | backlog |
| feature | {feature} |
| 작업 ID | {PREFIX}-{NN} |
| 선행 문서 | [change-plans/{PREFIX}-{NN}.md](../change-plans/{PREFIX}-{NN}.md) |
| 후속 문서 | 없음 |
| 관련 코드 | {사용자가 제공한 코드 범위} |

## Todo
- [ ] TODO

## Blocked
- 없음

## 변경 파일
- 대기

## Done
- 대기
```

`## 변경 파일`은 뼈대 단계에서는 `대기`로 둔다. 구현하면서 저장소 루트 기준 경로를 기록한다. 이 목록은 후속 business 문서 작성의 조사 시작점이며 전체 호출 체인 목록으로 간주하지 않는다.

### implementation-backlog.md

```markdown
# 구현 백로그

| 항목 | 값 |
|---|---|
| 문서 종류 | implementation-backlog |
| feature | {feature} |
| 작업 ID | 해당 없음 |
| 선행 문서 | [02-to-be-mapping.md](./02-to-be-mapping.md) |
| 후속 문서 | 없음 |
| 관련 코드 | {사용자가 제공한 코드 범위} |

| 작업 ID | 기능 | 우선순위 | 상태 | 선행 조건 |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO |
```
