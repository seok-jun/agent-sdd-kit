---
name: sdd-doc-scaffold
description: SDD 분석·설계 문서의 빈 골격을 단계별로 생성한다. 레거시 코드 수정이나 신규 기능 개발을 시작하며 as-is 분석서, to-be 매핑, 변경 계획, 구현 백로그의 일관된 구조가 필요할 때 사용한다. 코드를 분석하거나 내용을 채우는 Skill이 아니라 문서 구조와 연결 관계만 고정한다.
---

# SDD 문서 골격 생성

SDD 문서의 빈 골격을 단계별로 만든다. 사실 조사와 설계 내용 작성은 후속 작업으로 남긴다.

등급 기준은 [references/task-grading.md](references/task-grading.md), 문서별 골격은 [references/document-templates.md](references/document-templates.md)를 따른다.

## 절대 규칙

1. 파일을 만들기 전에 생성 목록, 경로, 섹션 헤더, 문서 관계를 출력하고 사용자 확인을 받는다.
2. 확인받은 목록 밖의 파일은 만들거나 수정하지 않는다.
3. 코드, 파일 목록, git 상태와 로그를 조사하지 않는다.
4. 사용자가 주지 않은 값은 추측하거나 저장소에서 찾지 말고 질문한다.
5. 템플릿의 치환 자리와 TODO 문구를 실제 내용처럼 채우지 않는다.
6. 현재 Stage가 확인되기 전에는 다음 Stage 파일을 만들지 않는다.

## 입력

다음 값을 확인한다.

- 작업 등급: `Trivial`, `Small`, `Medium`, `Large`, `Epic`
- feature 슬러그: SDD 폴더명에 사용할 kebab-case 문자열
- 작업 ID prefix: Stage 2부터 사용할 대문자 식별자
- 관련 코드 범위: 사용자가 제공한 경로 또는 설명
- 기준 ref: as-is를 고정할 commit hash, tag 또는 branch
- 작성일: 현재 날짜 또는 사용자가 지정한 날짜

작업 등급이 없으면 작업 설명만으로 등급 후보를 제안할 수 있다. 코드를 조사해 판정하지 말고 사용자 확인을 받는다.

`Trivial` 또는 `Small`이면 SDD 파일을 만들지 않고 이유를 알린다.

## Stage 1 - 현행 파악

다음 두 파일만 제안한다.

```text
docs/{feature}-sdd/
  README.md
  01-as-is-flow.md
```

`01-as-is-flow.md`가 작성되고 확인되기 전에는 Stage 2를 시작하지 않는다.

## Stage 2 - 목표 정의

다음 파일을 제안한다.

```text
docs/{feature}-sdd/
  02-to-be-mapping.md
  change-plans/
    README.md
```

to-be 매핑에서 실제 변경 항목이 확인된 뒤 각 항목에 작업 ID를 부여한다. ID가 확정되지 않은 change plan 파일은 만들지 않는다.

## Stage 3 - 실행 추적

다음 파일을 제안한다.

```text
docs/{feature}-sdd/
  backlog/
    {PREFIX}-{NN}.md
  implementation-backlog.md
```

backlog 파일은 확정된 작업 ID에 대해서만 만든다.

## 문서 관계

- 모든 문서는 제목 바로 아래에 문서 관계 표를 둔다.
- 아직 만들어지지 않은 문서는 파일명만 적고 링크하지 않는다.
- 파일이 실제로 생성된 시점에만 상대 링크로 바꾼다.
- 같은 변경 항목은 to-be 매핑, change plan, backlog에서 동일한 작업 ID를 사용한다.

## 실행 절차

1. 입력값과 작업 등급을 확인한다.
2. 현재 Stage에서 만들 파일과 각 파일의 섹션 헤더를 출력한다.
3. 문서 관계의 선행·후속 연결을 출력한다.
4. 사용자 확인을 받는다.
5. 확인받은 파일만 템플릿으로 만든다.
6. 생성된 상대 링크가 실제 파일을 가리키는지 확인한다.
7. 생성 목록 밖의 변경이 없는지 확인한다.
8. 다음 Stage로 넘어갈지 묻고 멈춘다.

## 출력 형식

```markdown
## 입력값
{등급, feature, ID prefix, 관련 코드 범위, 기준 ref, 작성일}

## 생성 예정 파일
{파일 목록}

## 문서별 섹션
{파일명과 섹션 헤더}

## 문서 관계
{선행·후속 연결}

## 확인 필요
{사용자가 결정해야 할 값}
```

## 금지

- 확인 전 파일 생성
- 템플릿을 실제 분석 내용으로 채우기
- 코드, git, 기존 문서를 조사해 입력값 보충하기
- 존재하지 않는 파일에 링크하기
- 작업 ID를 임의로 만들기
- 현재 Stage를 건너뛰기
