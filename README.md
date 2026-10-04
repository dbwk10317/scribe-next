# scribe-next

기존 Facebook Scribe의 외부 동작을 보존하면서 현대 Linux 환경으로 이식하는 C++ 프로젝트다. 프로젝트 이름은 `scribe-next`이며 실행 바이너리·서비스·CLI·설정 이름은 기존 `scribed` 계약을 유지한다.

현재는 **고정 upstream의 첫 소스 도입 단계**다. 원본 105개 경로의 C++·IDL·기존 autotools·PHP 시험·라이선스를 가져왔고, 내용·Git 실행 권한 및 누락 방지 검증을 추가했다. 현대 Linux 이식이나 Scribe 빌드·실행, 성능 측정, 서버 배포를 완료한 상태는 아니다. 실제 실행 결과와 환경 제약은 [현재 상태](docs/source-status.md#첫-소스-도입-검증-2026-10-04)에 기록한다.

## 문서

- [설계 및 호환성 계약](docs/design.ko.md)
- [세부 구현 계획과 검증 gate](docs/implementation.ko.md)
- [개발 에이전트 지침](AGENTS.md)
- [문서 출처·현재 결정·코드 도입 전략](docs/source-status.md)

설계와 구현 문서는 사용자 지정 Library Markdown을 바탕으로 공개 upstream과 목표 Thrift의 정적 검토를 반영한 작업 문서다. 원본 파일명·버전·SHA256, 검토한 고정 소스와 미검증 범위는 출처 문서에 남겼다.

## 목표와 미확정 사항

기준은 [facebookarchive/scribe](https://github.com/facebookarchive/scribe)의 공개 SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. `scribe.thrift`와 `bucketupdater.thrift`, framed binary와 경로별 strict 설정, fb303, byte 보존, 메모리 큐 ACK, queue/batch/thread·종료·재시도, 10 store, 동적 목적지 갱신과 파일·설정·라우팅·spool 계약을 지킨다. durable ACK, exactly-once, 새 transport, 전면 재작성은 목표에 포함하지 않는다.

Linux는 대상 OS다. C++17과 Thrift 0.25.0은 검증 후보이며 아직 채택 완료 또는 빌드 성공을 뜻하지 않는다. 회사 fork SHA와 패치, 실측 baseline, 실제 config/client/store 사용, Linux 배포판과 GCC/Clang·의존성 버전은 미확인이다. 회사 운영 동등성은 이 자료와 승인된 판정 기준 없이 선언하지 않는다.

## 첫 개발 작업과 다음 단계

1. 회사 fork·설정·운영 기준과 Linux toolchain matrix를 확인한다. 회사 자료가 없으면 공개 upstream 이식 범위와 회사 호환성 미확정 상태를 구분한다.
2. 고정 SHA의 원본 tree와 `LICENSE`·파일별 고지는 도입했다. upstream에는 `NOTICE`가 없다. 118개 upstream commit은 별도 로컬 `refs/remotes/upstream/baseline`에 보존했으며 프로젝트 이력과의 merge·원격 반영은 아직 하지 않았다. 출처와 검증 절차는 [현재 상태](docs/source-status.md)를 따른다.
3. 재현 가능한 old binary를 확보하고 기존 PHP 시험을 격리 환경에 맞춘다. `make check`는 이 suite를 실행하지 않는다. 두 RPC·10 store·동적 라우팅·양방향 relay/spool fixture와 설정 inventory를 만든다.
4. 작은 PR로 의존성·빌드 경계, Thrift/fb303 API, 기존 파일 transport와 spool 호환, 제한된 C++ 정리 순으로 진행한다. Thrift 0.25.0의 `TFileTransport`를 먼저 재사용·검증한다. 원본의 메모리 결함은 외부 계약과 구분해 재현 시험이 있는 별도 수정으로 다룬다.

현재 실행 가능한 **소스 도입 검증**은 다음과 같다. Python 3와 `--no-lazy-fetch`를 지원하는 Git, 로컬에 보존된 고정 upstream object가 필요하며 외부 패키지는 필요하지 않다.

```sh
python3 -B test/verify_upstream_import.py
python3 -B -m unittest discover -s test -p 'test_verify_upstream_import.py' -v
```

첫 명령은 작업 트리 내용·Git 실행 권한·ignore 누락을 검사한다. 두 번째는 임시 checkout에서 변조·누락·symlink·ignore·Git object 실패와 실제 staging을 시험한다. 현재 작업 트리의 stage/commit이나 네트워크 fetch는 하지 않는다. 원본 Scribe build 명령은 [upstream README](README)에 있고, 구현 문서의 현대화 build 명령은 여전히 **미실행 예시**다. 기존 PHP suite는 `make check`에 연결돼 있지 않으며 고정 포트·삭제 경로·프로세스 종료를 먼저 격리해야 한다. Gate A–D는 모두 미통과 상태다.

## 소스와 배포 관례

현재 구현은 승인된 클라우드 작업 사본에서 이어가며, 검증된 변경의 동기화와 승인된 작업 브랜치 commit·push는 Mac checkout에서 수행한다. GitHub 허브는 사용자 승인 범위에 따라 `dbwk10317/scribe-next` 비공개 저장소로 관리한다. 봉구서버의 Ubuntu 26.04.1에서 격리된 소스 도입 검사 105개 경로와 회귀 시험 18개가 통과했다. 상세 환경과 검증한 checkpoint는 [서버 검증 기록](docs/source-status.md#봉구서버의-격리-import-검증)을 따른다. 첫 checkpoint는 commit 전 작업 트리로 검증했으며, 검증된 도입 변경은 `codex/upstream-baseline` 작업 브랜치로 반영한다. main merge·후속 push·서버 검증·배포는 각각 승인 범위와 검증 gate를 확인한 뒤 진행한다. Scribe 서비스 기동·배포는 수행하지 않았다.

## 라이선스와 출처

공개 upstream은 [Apache License 2.0](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)을 제공한다. 원본 [LICENSE](LICENSE), README와 파일별 copyright·attribution을 보존했다. 고정 upstream tree에 `NOTICE`는 없다. 원본 파일 중 `.gitignore`에만 표시된 프로젝트 규칙을 덧붙였으며 C++·IDL·기존 build/test 파일은 변경하지 않았다. 이 안내로 개인 또는 회사의 새 저작권·배포 권한을 주장하지 않는다. 후속 수정에도 변경 사실을 표시한다. 회사 fork의 공개·배포 권한은 Apache 2.0 여부와 별도로 확인한다.
