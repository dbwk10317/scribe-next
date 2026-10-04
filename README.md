# scribe-next

기존 Facebook Scribe의 외부 동작을 보존하면서 현대 Linux 환경으로 이식하는 C++ 프로젝트다. 프로젝트 이름은 `scribe-next`이며 실행 바이너리·서비스·CLI·설정 이름은 기존 `scribed` 계약을 유지한다.

현재는 **문서만 있는 개발 준비 저장소**다. upstream 코드, 구현, 빌드 시스템, 테스트 harness와 CI는 아직 도입하지 않았다. 의존성 설치, 빌드, 실행, 성능 측정, 서버 배포를 수행하지 않았다.

## 문서

- [설계 및 호환성 계약](docs/design.ko.md)
- [세부 구현 계획과 검증 gate](docs/implementation.ko.md)
- [개발 에이전트 지침](AGENTS.md)
- [문서 출처·현재 결정·코드 도입 전략](docs/source-status.md)

설계와 구현 문서는 사용자 지정 최신 Library Markdown을 가져왔다. 저장소 안에서 안정적인 이름으로 배치하고 상대 링크만 추가했다. 원본 파일명·버전·SHA256과 공개 upstream 출처는 출처 문서에 남겼다.

## 목표와 미확정 사항

기준은 [facebookarchive/scribe](https://github.com/facebookarchive/scribe)의 공개 SHA `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. 기존 Thrift IDL, framed binary와 strict=false/false, fb303, byte 보존, 메모리 큐 ACK, queue/batch/thread·종료·재시도, 10 store, 파일·설정·라우팅 및 spool 계약을 지킨다. durable ACK, exactly-once, 새 transport, 전면 재작성은 목표에 포함하지 않는다.

Linux는 대상 OS다. C++17과 Thrift 0.25.0은 검증 후보이며 아직 채택 완료 또는 빌드 성공을 뜻하지 않는다. 회사 fork SHA와 패치, 실측 baseline, 실제 config/client/store 사용, Linux 배포판과 GCC/Clang·의존성 버전은 미확인이다. 회사 운영 동등성은 이 자료와 승인된 판정 기준 없이 선언하지 않는다.

## 첫 개발 작업

1. 회사 fork·설정·운영 기준과 Linux toolchain matrix를 확인한다. 회사 자료가 없으면 공개 upstream 이식 범위와 회사 호환성 미확정 상태를 구분한다.
2. 별도 코드 도입 작업에서 고정 SHA의 upstream tree를 원래 경로와 이력을 보존하는 방식으로 가져온다. `LICENSE`, 존재하는 `NOTICE`, 파일별 copyright·attribution과 의존성 고지를 함께 확인한다.
3. 기존 build/test driver와 설정 inventory를 조사하고 old 동작의 wire·10 store·양방향 relay/spool fixture를 만든다.
4. 작은 PR로 의존성·빌드 경계, Thrift/fb303 API, 필요한 파일 transport 호환, 제한된 C++ 정리 순으로 진행한다. 매 단계의 실제 검증 결과가 다음 단계를 연다.

현재 실행 가능한 프로젝트 build/test 명령은 없다. 구현 문서의 명령은 향후 전체 source tree와 도구를 확인한 뒤 조정할 **미실행 예시**다. Gate A–D는 모두 미통과 상태다.

## 소스와 배포 관례

Mac의 `~/workspace/scribe-next` 체크아웃을 소스 원본으로 사용한다. GitHub 허브는 사용자 승인 범위에 따라 `dbwk10317/scribe-next` 비공개 저장소로 관리하고, 서버는 향후 같은 저장소에서 clone/pull한다. 배포 순서는 Mac push → 서버 pull → 승인된 서비스 재시작이다. 현재 준비 범위는 문서·개발 지침이며 서버 실행을 포함하지 않는다.

## 라이선스와 출처

공개 upstream은 [Apache License 2.0](https://raw.githubusercontent.com/facebookarchive/scribe/fcd294faffd1e88af1643a3a8c2359c41713f7c2/LICENSE)을 제공한다. 아직 upstream 코드를 이 저장소에 복사하지 않았으며, 이 안내로 개인 또는 회사의 새 저작권·배포 권한을 주장하지 않는다. 코드 도입 시 원본 라이선스와 출처 고지를 유지하고 변경 파일의 변경 사실을 표시한다. 회사 fork의 공개·배포 권한은 Apache 2.0 여부와 별도로 확인한다.
