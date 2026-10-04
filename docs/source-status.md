# 문서 출처와 현재 결정

## 기준 문서

2026-10-04 사용자 지정 최신 Library 파일을 Mac의 실제 파일로 가져왔다. Library가 반환한 버전은 두 파일 모두 `0`이다. 아래 SHA256은 상대 링크 추가 전 원본 bytes 기준이다. 이전 Mac 문서를 대체 원본으로 사용하지 않았다.

| 역할 | 원본 파일명 | 저장소 경로 |
| --- | --- | --- |
| 설계 | scribe-next-설계문서.md | [design.ko.md](design.ko.md) |
| 구현 계획 | scribe-next-세부구현문서.md | [implementation.ko.md](implementation.ko.md) |

- 설계 원본 SHA256: `ecabaf7b48b535ae6f7e348631dbfce35a5020665e3a2fc868dd36cba76f296a`
- 구현 원본 SHA256: `66e13598a2d5a38d99f4437de53f1e04d7f23e89231247ba44db5bff33cd4488`

저장소 사본은 각 문서 날짜 아래에 서로와 README를 가리키는 상대 링크 한 줄을 추가했다. 그 외 원문 내용은 유지했다. 원문의 정적 검토·버전 확인 기록은 해당 마스터 문서의 근거 상태이며, 이번 저장소 준비를 통해 build·runtime 검증으로 승격되지 않는다.

## 현재 결정과 열려 있는 항목

| 구분 | 상태 |
| --- | --- |
| 확정 방향 | Linux 대상, 기존 Scribe 동작 보존, 기존 구조·autotools 우선, 작은 PR 단위의 단계적 이식 |
| 공개 기준 | [facebookarchive/scribe](https://github.com/facebookarchive/scribe), SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2` |
| 제안 후보 | C++17, Thrift 0.25.0; 실제 요구 표준·API·빌드 검증 후 확정 |
| 미확인 | 회사 fork·patch·production config·client/store/HDFS 사용, 실측 baseline, 배포판·compiler·dependency matrix |
| 저장소 상태 | 문서와 개발 지침만 있음. upstream source와 build/test/CI 없음 |
| 검증 gate | A compile/link, B wire/API/config/10 store, C spool/relay/fault/종료, D 회사 성능·운영: 모두 미실행·미통과 |
| 원격·배포 | GitHub `dbwk10317/scribe-next` 비공개 관리 승인, 서버 기동·배포 미실행 |

## upstream 코드 도입 전략

다음 코드 도입 작업은 고정 공개 SHA를 깨끗한 별도 checkout에서 검증하고 원본 source tree·경로·라이선스·이력을 보존하는 방향으로 수행한다. 현재 문서 저장소와 합치는 Git 방식은 원격 및 회사 fork 기준을 확인한 뒤 선택한다. 전체 repository를 먼저 조사하고 기존 build/test driver와 설정 inventory를 확인하며, 도입만 하는 변경과 이식 변경을 분리한다. 최신 branch를 임의 build 입력으로 삼거나 generated code를 수동 수정하지 않는다.

첫 완료 조건은 기준 commit/tree 확인, 출처 고지 보존, 회사 대비 차이와 Linux matrix 정리, 계약 fixture 계획이다. 실제 검증 결과는 구현 시 source path·symbol·fixture·old/new 결과에 연결한다. 회사 자료가 없으면 공개 upstream 작업과 회사 호환성 미확정을 분명히 구분한다.

## 라이선스 경계

공개 기준 SHA의 [upstream LICENSE](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)는 Apache License 2.0이다. 현재 저장소에는 upstream 코드가 없다. 향후 도입·배포 시 LICENSE와 원본 copyright·attribution을 보존하고, NOTICE 존재 여부를 전체 tree에서 확인해 필요한 고지를 유지하며 변경 파일에 변경 사실을 표시한다. 의존성 고지도 검토한다. 이 기록은 개인·회사 저작권의 새 주장이나 회사 fork 공개 권한을 부여하지 않는다.
