# scribe-next 개발 지침

## 읽는 순서와 적용 범위

해당 checkout의 workspace 지침이 있으면 workspace `CLAUDE.md`/`AGENTS.md` → 이 저장소 `CLAUDE.md`/`AGENTS.md` → 작업 경로의 중첩 지침 순으로 각각 한 번 읽는다. 개인 절대경로나 특정 Mac의 skill 설치 경로를 요구하지 않는다. 독립 checkout에는 존재하지 않는 상위 workspace 파일을 가정하지 않는다.

이 저장소의 실질적인 개발 지침을 `AGENTS.md`에 구성하라는 사용자 요청에 따라 공통 지침을 이 파일에 둔다. [CLAUDE.md](CLAUDE.md)는 이 파일을 읽는 공유 진입점이며 지침 사본을 만들지 않는다. 시작할 때 [README](README.md), [현재 결정과 출처](docs/source-status.md), [설계](docs/design.ko.md), [구현 계획](docs/implementation.ko.md)을 읽는다. 사용자의 명시적 지시가 문서보다 우선한다.

## 현재 상태와 근거

- 문서 준비 상태다. 소스 코드, build system, harness와 CI가 아직 없다. 실제 파일과 실행 결과로 확인되지 않은 명령·기능을 존재하거나 성공한 것처럼 쓰지 않는다.
- 기준 upstream은 [facebookarchive/scribe](https://github.com/facebookarchive/scribe), 공개 SHA는 `fcd294faffd1e88af1643a3a8c2359c41713f7c2`다. 회사 fork·실제 config·실측 baseline·배포판·toolchain은 미확인이다.
- 대상 OS는 Linux다. C++17과 Thrift 0.25.0은 제안 검증 후보다. target release의 실제 요구 표준과 API를 확인하기 전 확정하거나 빌드 성공을 주장하지 않는다.
- 문서의 공개 소스 정적 검토 사실, 사용자 보존 요구, 구현 제안, 실제 실행·실패·미실행을 구분한다. 한 환경에서의 결과로 회사 운영 동등성이나 전체 platform 지원을 선언하지 않는다.

## 작업 방식

karpathy-guidelines와 ponytail의 핵심 원칙을 이 저장소에 적용한다.

1. 변경 전에 가정·불확실성·호환성 영향을 명시하고 관찰 가능한 완료 조건을 정한다. 모호함이 결과에 영향을 주면 근거를 조사하고 필요한 부분만 확인한다.
2. 관련 source와 호출 경로를 먼저 읽는다. 기존 클래스·함수·test driver·build 구조를 재사용하고 표준 라이브러리나 이미 있는 의존성이 계약을 만족하는지 먼저 본다.
3. 요청과 이식에 필요한 변경만 한다. 인접 코드 정리, formatting 일괄 변경, speculative framework·registry·adapter, 새 의존성, 빈 scaffolding과 CI를 추가하지 않는다.
4. 기존 autotools와 구조를 우선한다. 전체 Boost 제거, 즉시 CMake 전환, 전체 ownership·thread·I/O 재설계는 별도 근거와 범위가 없으면 하지 않는다.
5. build 경계 → Thrift/fb303 API 및 필요한 file transport 호환 → 행동 검증 → 통과한 모듈의 제한된 C++ 정리 순으로 작은 review 가능한 PR을 만든다. build 복구와 동작 변경을 한 diff에 섞지 않는다.
6. 각 PR은 실제 수행한 검증, 결과, 미실행 항목과 남은 위험을 적는다. 필요한 실패 재현 또는 계약 검증을 최소로 남긴다. 구현을 그대로 반복하는 테스트와 목적 없는 framework는 만들지 않는다.
7. 데이터 손실·보안·입력 경계 보호를 단순화로 없애지 않는다. 원본의 오류·중복·손실 가능성은 별도 이슈와 호환성 결정으로 다루며 조용히 의미를 바꾸지 않는다.

## 반드시 보존할 계약

- **IDL·wire·운영 API:** 기존 `if/scribe.thrift`의 method, field ID, enum, requiredness, namespace, 예외 표현과 fb303 상속·method/counter/status/details를 유지한다. client/server 모두 framed binary, strictRead=false/strictWrite=false를 명시한다. old/new client·server와 양방향 relay를 비교한다.
- **bytes·ACK:** category/message의 byte sequence를 보존한다. UTF-8 정규화, newline 보정과 payload 변환을 하지 않는다. OK는 기존 메모리 큐 수락 의미이며 영속 기록 완료가 아니다. 빈/미정의 category discard, queue limit의 TRY_LATER, 부분 수락 후 재시도 중복 등 원본 결과를 숨기지 않는다.
- **queue·batch·thread:** message bytes 기준 큐 크기, `target_write_size=16384`, `max_write_interval=1초`, worker 수, lock 순서·scope, wakeup, command·실패 batch 우선순위, must_succeed, retry, flush_streaming, shutdown 의미를 유지한다. 새로운 thread/time API는 build에 필요한 경계만 다룬다.
- **10 store:** file, buffer, network, bucket, thriftfile, null, multi, category, multifile, thriftmultifile과 해당 설정 이름을 유지한다. 미사용 store도 upstream 지원·검증 대상에서 조용히 제외하지 않는다.
- **파일·라우팅·설정:** exact/prefix/default route, 기존 hash와 bucket 경계, fan-out 순서, filename·rotation·newline·meta·`_current` symlink, config default·파싱·오류·상속과 CLI 우선순위를 유지한다. 프로젝트 이름은 scribe-next지만 바이너리·서비스·CLI/config 이름은 legacy `scribed` 계약을 유지한다.
- **spool:** 일반 replay는 4-byte little-endian 길이+payload이며 write_category의 category/newline은 별도 frame이다. thriftfile transport 형식은 별도다. old-write/new-read와 new-write/old-read를 두 형식 모두 검증한다. 동일 spool 경로에 두 프로세스가 동시에 쓰지 않는다.
- **보장 수준:** stream flush를 fsync로 설명하지 않는다. durable ACK, exactly-once, 새 transport, 전역 ordering과 crash durability를 추가하거나 약속하지 않는다. 기존 retry·shutdown의 loss/duplicate 가능성을 설명한다.
- **의존성:** compiler와 Thrift C++ runtime 버전을 맞추고 hash·flag·생성 결과를 고정한다. fb303 IDL 존재만으로 C++ 지원을 증명하지 않는다. optional HDFS 사용 여부와 feature lane을 조사한다. generated code는 생성 규칙으로 바꾸며 손으로 수정하지 않는다.

## 완료 기준

Gate A: 확인된 Linux platform/feature matrix의 compile·link 성공.

Gate B: IDL/wire/fb303/config 및 10 store의 golden·old/new differential 통과.

Gate C: 양방향 ordinary spool·thriftfile·relay, fault/retry와 종료 계약 검증 통과.

Gate D: 회사가 승인한 baseline·허용 차이에 따른 성능과 운영 승인. 그 뒤 배포·롤백 실행 권한을 확인한다.

어느 gate도 현재 통과하지 않았다. 의존성 build 성공을 Scribe build 성공 또는 runtime 호환성으로 확대하지 않는다. 동일 장비·조건에서 old/new를 비교하고 source·fixture·결과의 근거를 연결한다. 실제 명령은 source와 toolchain 도입 후 확인하며 지금 가짜 build/test 성공을 기록하지 않는다.

## 저장소·배포·고지

Mac workspace checkout을 소스 원본으로 사용하고 서버는 향후 동일 원격에서 clone/pull한다. 사용자가 승인한 원격 비공개 범위를 준수하고 공개 범위를 임의로 바꾸지 않는다. 기존 변경과 unrelated 파일을 보존하고 stage할 경로를 명시한다. 전역 Git 설정, 임의 Git identity, 비밀 값·캐시·runtime spool·거대 산출물을 저장소에 넣지 않는다.

upstream 코드 도입 시 원본 Apache 2.0 `LICENSE`, 존재하는 `NOTICE`, 파일별 copyright·attribution 및 의존성 고지를 유지한다. 변경 사실을 표시하되 임의의 개인 저작권이나 회사 권리를 주장하지 않는다. 회사 fork의 공개·배포 권한은 별도로 확인한다.
