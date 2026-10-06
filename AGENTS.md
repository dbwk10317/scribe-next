# scribe-next 개발 지침

## 읽는 순서와 적용 범위

해당 checkout의 workspace 지침이 있으면 workspace `CLAUDE.md`/`AGENTS.md` → 이 저장소 `CLAUDE.md`/`AGENTS.md` → 작업 경로의 중첩 지침 순으로 각각 한 번 읽는다. 개인 절대경로나 특정 Mac의 skill 설치 경로를 요구하지 않는다. 독립 checkout에는 존재하지 않는 상위 workspace 파일을 가정하지 않는다.

이 저장소의 실질적인 개발 지침을 `AGENTS.md`에 구성하라는 사용자 요청에 따라 공통 지침을 이 파일에 둔다. [CLAUDE.md](CLAUDE.md)는 이 파일을 읽는 공유 진입점이며 지침 사본을 만들지 않는다. 시작할 때 [README](README.md), [현재 결정과 출처](docs/source-status.md), [설계](docs/design.ko.md), [구현 계획](docs/implementation.ko.md)을 읽는다. 사용자의 명시적 지시가 문서보다 우선한다.

## 최신 사용자 호환 정책

2026-10-06 명시 지시는 이전 예외 승인보다 우선한다. 신·구 송수신과 기존 로그
reader의 route/byte/format/delivery/monitoring 계약을 바꾸는 semantic 수정은
원본의 정의된 동작으로 되돌린다. 원본 UB/crash는 재도입하지 않으며 되돌린
버그는 문서에 남기고 새 옵션을 만들지 않는다. [현재 정책](docs/legacy-compatibility-policy.md)을 따른다.
아래 승인·시험 수는 각 역사 단계의 기록이며 현재 후보 성공을 뜻하지 않는다.

## 현재 상태와 근거

- 최신 사용자 목표는 공개 upstream `fcd294f`의 기능 보존이다. 회사 fork/config/성능 자료는 현재 범위 밖이며 요청하거나 완료 조건으로 삼지 않는다. 제한 build MVP와 재사용 검증, 공개 원본 old/new 다음 우선순위는 [현재 범위](docs/linux-build-mvp.md)를 따른다. 과거 회사 gate를 현재 지시로 되살리지 않는다.
- 고정 upstream 도입 뒤 제한된 빌드 진입부 수정을 진행 중이다. 의존성·통합 시험 이력은 [빌드 경계 기록](docs/build-status.md), scribed compile/link·API 시험 이력은 [API 이식 기록](docs/api-compat-status.md), 일반 spool·설정 계약과 최소 메모리 수정은 [계약 검증 이력](docs/contracts-status.md), 실제 FileStore 통합과 수정 전 손실 경로는 [FileStore 기록](docs/filestore-contracts-status.md), 승인된 최소 truncate 수정과 74개 시험은 [수정 기록](docs/truncate-fix-status.md), test-only loopback TCP·worker 계약은 [loopback 기록](docs/loopback-rpc-status.md), 최신 NetworkStore/ConnPool·명시적 재시도 계약은 [relay 기록](docs/relay-contracts-status.md), 도입 이력은 [현재 상태](docs/source-status.md)를 따른다. import 검증기는 의도된 build 파일 수정도 실패로 표시하는 원본 보존 검사다. 원본 도입 commit의 검사와 현재 build 회귀 시험을 구분하며, 부분 build·의존성 시험과 단일 Linux compile/link 결과를 전체 matrix·runtime 호환성으로 확대하지 않는다.
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
7. 데이터 손실·보안·입력 경계 보호를 단순화로 없애지 않는다. 원본의 오류·중복·손실 가능성은 별도 이슈와 호환성 결정으로 다루며 조용히 의미를 바꾸지 않는다. 재현된 부분 replay 손실은 사용자 예외 승인 후 openTruncate의 app 제거만 적용했다. 이것을 다른 loss/retry 정책 변경 승인으로 확대하지 않는다. 미정의 동작 자체는 보존 계약이 아니다. 원본 메모리 결함은 재현 시험과 외부 영향 비교를 갖춘 별도 수정으로 처리한다. StdFile의 malloc/delete[] 불일치는 실제 재현과 component bytes 비교 후 free로 수정했다. 클라우드 LSan은 ptrace 제약으로 미검증이며, 별도 Ubuntu에서 양성 대조 및 제한된 reader의 LSan 활성 검증만 통과했다. 전체 daemon 누수·runtime 동등성을 뜻하지 않는다.

## 반드시 보존할 계약

- **IDL·wire·운영 API:** 기존 `if/scribe.thrift`와 `if/bucketupdater.thrift`의 method, field ID, enum, requiredness, namespace, 예외 표현과 fb303 상속·method/counter/status/details를 유지한다. framed binary를 보존한다. 서버·bucket mapping·relay client 세 경로의 기존 명시적 strictRead=false/strictWrite=false를 유지한다. relay가 기본값에 의존한다던 이전 기록은 고정 source의 setStrict(false, false) 확인으로 정정했다. old/new client·server, 양방향 relay와 bucket mapping 호출을 비교한다.
- **bytes·ACK:** category/message의 byte sequence를 보존한다. UTF-8 정규화, newline 보정과 payload 변환을 하지 않는다. OK는 기존 메모리 큐 수락 의미이며 영속 기록 완료가 아니다. 빈/미정의 category discard, queue limit의 TRY_LATER, 부분 수락 후 재시도 중복 등 원본 결과를 숨기지 않는다.
- **queue·batch·thread:** message bytes 기준 큐 크기, `target_write_size=16384`, `max_write_interval=1초`, worker 수, lock 순서·scope, wakeup, command·실패 batch 우선순위, must_succeed, retry, flush_streaming, shutdown 의미를 유지한다. 새로운 thread/time API는 build에 필요한 경계만 다룬다.
- **10 store:** file, buffer, network, bucket, thriftfile, null, multi, category, multifile, thriftmultifile과 해당 설정 이름을 유지한다. 미사용 store도 upstream 지원·검증 대상에서 조용히 제외하지 않는다.
- **파일·라우팅·설정:** exact/prefix/default route와 정렬된 map의 첫 prefix 일치, 기존 hash와 bucket 경계, 동적 목적지의 TTL·갱신 실패·counter, fan-out 순서, filename·rotation·newline·meta·`_current` symlink, config default·파싱·오류·상속과 CLI 우선순위를 유지한다. 서비스 이름 조회는 회사 환경 구현을 확인한다. 프로젝트 이름은 scribe-next지만 바이너리·서비스·CLI/config 이름은 legacy `scribed` 계약을 유지한다.
- **spool:** 일반 replay는 4-byte little-endian 길이+payload이며 write_category의 category/newline은 별도 frame이다. thriftfile transport 형식은 별도다. old-write/new-read와 new-write/old-read를 두 형식 모두 검증한다. 동일 spool 경로에 두 프로세스가 동시에 쓰지 않는다.
- **보장 수준:** stream flush를 fsync로 설명하지 않는다. durable ACK, exactly-once, 새 transport, 전역 ordering과 crash durability를 추가하거나 약속하지 않는다. 기존 retry·shutdown의 loss/duplicate 가능성을 설명한다.
- **의존성:** [검증된 Linux recipe](README.md#검증된-linux-c-빌드-recipe)의 dependency/include/link prefix와 세 Boost 옵션을 명시한다. CFLAGS/CXXFLAGS의 사용자 값·빈 값을 보존하고 빈 constants 파일을 요구하거나 수동 생성하지 않는다. compiler와 Thrift C++ runtime 버전을 맞추고 hash·flag·생성 결과를 고정한다. fb303 C++ 소스의 존재만으로 build 호환성을 증명하지 않는다. Thrift 0.25.0에 남아 있는 파일 transport를 먼저 검증하며 제거됐다고 가정해 재구현하지 않는다. optional HDFS 사용 여부와 feature lane을 조사한다. generated code는 생성 규칙으로 바꾸며 손으로 수정하지 않는다.
- **입력 보호·thread:** review 작업 트리의 전역 `thrift_max_frame_size`·`thrift_max_message_size`는 각각 256 MiB 기본값의 양의 십진수 startup-only byte 한도다. server/socket/input-memory와 두 client에 일관되게 적용하며 outgoing relay 초과 batch를 자동 분할하거나 drop하지 않는다. 회사 동등성·무제한 호환성·oversized spool 해결로 확대하지 않는다. Thrift 0.9.0의 명시적 1 MiB thread stack과 0.25.0 std::thread의 OS/runtime 기본값을 구분하고 8 MiB라고 가정하지 않는다.
- **import 검증:** object-free capability check를 먼저 수행하며 `--no-lazy-fetch`와 `--no-replace-objects`는 모두 필수다. 미지원 Git과 누락 object를 구분하고 보호 제거·자동 fetch fallback을 추가하지 않는다. 원본 도입 checkout의 PASS와 의도된 현재 source 차이를 구분한다.

## 완료 기준

Gate A: 확인된 Linux platform/feature matrix의 compile·link 성공.

Gate B: 두 IDL/wire/fb303/config, 10 store와 동적 목적지 갱신의 golden·old/new differential 통과.

Gate C: 양방향 ordinary spool·thriftfile·relay, fault/retry와 종료 계약 검증 통과.

Gate D: 공개 원본 baseline·명시 허용 차이에 따른 성능과 운영 검증. 그 뒤 배포·롤백 실행 권한을 확인한다.

어느 gate도 현재 전체 통과하지 않았다. 클라우드 및 Ubuntu의 비-HDFS 기본 C++ lane은 scribed compile/link와 당시 프로젝트 55개 시험을 통과했고, 후속 cloud FileStore characterization은 70개, 승인된 truncate 수정본은 cloud·Ubuntu에서 새 clean build·74개 시험을 통과했으나 전체 platform/feature matrix와 runtime 동등성은 미검증이다. 후속 TCP fixture는 명시적 127.0.0.1 bind로 실제 handler/worker를 검증하며 cloud·Ubuntu에서 각 89개 시험을 통과했다. Ubuntu는 v8의 새 clean build·help, TCP 반복 50회와 listener/자식 회수도 통과했다. 당시 상위 작업 요약 뒤 v10에서 raw records를 수신·검증했다. 후속 relay suite는 cloud·Ubuntu에서 각101개 시험을 통과했다. Ubuntu v11의 새 clean build·help, relay 반복50회와 loopback/자식 회수는 당시 v12 요약 뒤 v13 main 인계의 raw records로 확인했다. relay 구현 `5594efaae67e214880a31c755c0f5cb86cfc192a`는 PR #3/main `ddca67e6c3485459648e4cbc975d5dae9ddccfc2`에 반영됐다. 이 101개는 이전 relay 단계의 수이며 후속 review 수정본의 최종 결과가 아니다. 후속 승인된 독립 범위는 새 clean build·help, 전체124개/skip0과 ASan+UBSan API69개/skip0 및 독립 검토를 통과했다. 후속 store 수정은 Ubuntu clean build·help, 전체137개/skip0과 ASan+UBSan API82개/skip0을 통과했다. 해결된 store 5건의 검증 범위와 전체 미완료 gate는 [review 기록](docs/review-fixes-status.md)을 따른다. 실제 두-worker 정상 연결과 직접 호출 fault/retry를 구분한다. 응답 유실 재시도의 중복 관찰과 downstream prefix 모의를 실제 old-runtime/company differential로 확대하지 않는다. production main/startServer 실행과 구분한다. GNU --wrap mutex lane의 non-Linux skip을 Linux 성공으로 세지 않는다. 동일 장비·조건에서 old/new를 비교하고 source·fixture·결과의 근거를 연결한다. 실제 명령은 확인된 source와 toolchain에서 실행하고, import 시험 성공을 Scribe build/test 성공으로 기록하지 않는다.

## 저장소·배포·고지

main `c3f3459` 이후 test-only ThriftFileStore 관찰은 cloud·Ubuntu의146개/skip0과 focused ASan+UBSan9개/skip0을 통과했다. 후속 승인된 copy 설정 보존은 `useSimpleFile` 한 필드만 수정했으며 새 cloud clean build/help·전체147개/skip0·focused ASan+UBSan10개/skip0을 통과했다. 기존 framed clone 파일을 변환하지 않고 다음 suffix에 설정된 raw mode로 기록한다. 사용자는 chunk 초과의 기존 Thrift 처리와 반환/집계를 유지하도록 결정했고 empty도 새 정책으로 바꾸지 않는다. [실측 범위](docs/thriftfile-contracts-status.md)와 [승인 범위·보존 결정](docs/thriftfile-fix-options.md)을 따르며 해당 유실 동작이 해결됐다고 설명하지 않는다. 같은 production·test 소스는 새 Ubuntu clean build/help·전체147개/skip0·focused ASan+UBSan10개/skip0도 통과했다. 이번 배치의 commit·push·main merge는 사용자가 별도로 승인했으며 서비스·배포 권한으로 확대하지 않는다.

현재 구현은 사용자가 승인한 클라우드 작업 사본에서 수행한다. 검증된 변경의 동기화와 승인된 작업 브랜치의 commit·push는 Mac checkout에서 수행하며 다음 구현은 클라우드에서 이어간다. 이번 push 승인을 후속 push나 main merge 권한으로 확대하지 않는다. 봉구서버에서 첫 소스 도입의 격리 검증을 통과했으며 상세 결과는 [현재 상태](docs/source-status.md)를 따른다. 이후 실제 Linux build·runtime 검증은 별도 승인 범위에서 사용한다. 작업 사본 이전은 서버 기동·배포 권한을 뜻하지 않는다. 사용자가 승인한 원격 비공개 범위를 준수하고 공개 범위를 임의로 바꾸지 않는다. 기존 변경과 unrelated 파일을 보존하고 stage할 경로를 명시한다. 전역 Git 설정, 임의 Git identity, 비밀 값·캐시·runtime spool·거대 산출물을 저장소에 넣지 않는다.

upstream 코드 도입 시 원본 Apache 2.0 `LICENSE`, 존재하는 `NOTICE`, 파일별 copyright·attribution 및 의존성 고지를 유지한다. 변경 사실을 표시하되 임의의 개인 저작권이나 회사 권리를 주장하지 않는다. 회사 fork의 공개·배포 권한은 별도로 확인한다.
