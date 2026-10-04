# 문서 출처와 현재 결정

## 기준 문서

2026-10-04 사용자 지정 최신 Library 파일을 Mac의 실제 파일로 가져왔다. Library가 반환한 버전은 두 파일 모두 `0`이다. 아래 SHA256은 상대 링크 추가 전 원본 bytes 기준이다. 이전 Mac 문서를 대체 원본으로 사용하지 않았다.

| 역할 | 원본 파일명 | 저장소 경로 |
| --- | --- | --- |
| 설계 | scribe-next-설계문서.md | [design.ko.md](design.ko.md) |
| 구현 계획 | scribe-next-세부구현문서.md | [implementation.ko.md](implementation.ko.md) |

- 설계 원본 SHA256: `ecabaf7b48b535ae6f7e348631dbfce35a5020665e3a2fc868dd36cba76f296a`
- 구현 원본 SHA256: `66e13598a2d5a38d99f4437de53f1e04d7f23e89231247ba44db5bff33cd4488`

저장소 사본은 원본을 바탕으로 상대 링크와 아래 고정 source의 정적 검토를 반영한 작업 문서다. 위 해시는 Library 원본 식별용이며 현재 수정본의 해시가 아니다. 현재 문서에는 두 번째 RPC·동적 라우팅, 목표 Thrift API, 원본 메모리 결함과 시험 실행 경계를 반영했다. source 열람은 build·runtime 검증으로 승격되지 않는다.

## 현재 결정과 열려 있는 항목

| 구분 | 상태 |
| --- | --- |
| 확정 방향 | Linux 대상, 기존 Scribe 동작 보존, 기존 구조·autotools 우선, 작은 PR 단위의 단계적 이식 |
| 공개 기준 | [facebookarchive/scribe](https://github.com/facebookarchive/scribe), SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2` |
| 제안 후보 | C++17, Thrift 0.25.0; 요구 표준과 주요 API는 정적 확인, 실제 build·runtime 채택은 미확정 |
| 미확인 | 회사 fork·patch·production config·client/store/HDFS 사용, 실측 baseline, 배포판·compiler·dependency matrix |
| 저장소 상태 | 문서와 개발 지침만 있음. upstream source와 build/test/CI 없음 |
| 검증 gate | A compile/link, B 두 RPC/API/config/10 store/동적 목적지 갱신, C spool/relay/fault/종료, D 회사 성능·운영: 모두 미실행·미통과 |
| 원격·배포 | GitHub `dbwk10317/scribe-next` 비공개 관리 승인, 서버 기동·배포 미실행 |

## upstream 코드 도입 전략

다음 코드 도입 작업은 이미 정적으로 검토한 고정 공개 SHA를 다시 확인하고 원본 source tree·경로·라이선스·이력을 보존하는 방향으로 수행한다. 현재 문서 저장소와 합치는 Git 방식은 원격 및 회사 fork 기준을 확인한 뒤 선택한다. 재현 가능한 old binary와 격리된 기존 PHP driver·fixture를 먼저 확보하며 도입만 하는 변경과 이식 변경을 분리한다. 최신 branch를 임의 build 입력으로 삼거나 generated code를 수동 수정하지 않는다.

첫 완료 조건은 기준 commit/tree 확인, 출처 고지 보존, 회사 대비 차이와 Linux matrix 정리, 계약 fixture 계획이다. 실제 검증 결과는 구현 시 source path·symbol·fixture·old/new 결과에 연결한다. 회사 자료가 없으면 공개 upstream 작업과 회사 호환성 미확정을 분명히 구분한다.

## 정적 검토의 근거 범위

검토 기준일은 2026-10-04다. 공개 upstream `fcd294faffd1e88af1643a3a8c2359c41713f7c2`와 Thrift v0.25.0의 commit `27e8a425ffb498e190df3a12e239326bf5ba9ed6` 전체 tree를 별도 checkout에서 확보했다. 주요 경계의 source 링크와 채택 방향은 [설계의 의존성 전략](design.ko.md#의존성-전략)과 [근거 목록](design.ko.md#근거와-적용한-원칙)에 둔다.

두 번째 RPC와 동적 routing, PHP suite의 build 미연결, 목표 파일 transport·fb303 C++ source의 존재와 API 경계를 정적으로 확인했다. 원본 `StdFile`의 할당·해제 불일치는 [별도 재현·수정 계획](implementation.ko.md#원본-메모리-결함의-별도-검증)이며 실행 재현은 하지 않았다. 코드 도입, 의존성/Scribe build, wire·spool differential, sanitizer와 성능 시험은 모두 미실행이다. 임시 source checkout을 이 저장소에 포함하지 않는다.

## 라이선스 경계

공개 기준 SHA의 [upstream LICENSE](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)는 Apache License 2.0이다. 현재 저장소에는 upstream 코드가 없다. 향후 도입·배포 시 LICENSE와 원본 copyright·attribution을 보존하고, NOTICE 존재 여부를 전체 tree에서 확인해 필요한 고지를 유지하며 변경 파일에 변경 사실을 표시한다. 의존성 고지도 검토한다. 이 기록은 개인·회사 저작권의 새 주장이나 회사 fork 공개 권한을 부여하지 않는다.
