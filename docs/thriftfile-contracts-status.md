# ThriftFileStore의 제한된 transport 관찰

2026-10-06 정책 변경: 아래 승인·수정·측정은 당시 이력이다. 현재 기본 동작은 [원본 계약 우선 정책](legacy-compatibility-policy.md)을 따르며 route/byte/format/delivery/monitoring 변경은 되돌린다. 과거 raw 결과는 현재 검증으로 세지 않는다.

2026-10-05 · base/main `c3f3459b5d42672e7a8c21cc56bdd6cf94d97b76` · copy 최소 수정 작업 트리

관련 문서: [README](../README.md) · [manifest](thriftfile-contracts-manifest.json) · [수정 선택지와 승인 경계](thriftfile-fix-options.md) · [이전 store 수정](review-fixes-status.md)

## 승인된 copy 최소 수정 결과

production diff는 `src/store.cpp`의 `ThriftFileStore::copy`에서 `store->useSimpleFile = useSimpleFile;` 한 줄이다. IDL·build 규칙과 chunk/empty·retry/lost 처리 경로는 바꾸지 않았다. 사용자 결정은 [동작 보존 기록](thriftfile-fix-options.md)을 따른다.

- 서버 검증된 Library v18을 새 작업 사본으로 복원해 archive 크기·SHA256,1502개 기록,163개 source bytes/mode,8개 bundle ref,clean base와fsck 및 기존 overlay를 확인했다
- 수정 전 pristine v18 production+새 회귀에서 default 두 대조는 통과했다. simple1/2의 두 회귀는4개 subtest 모두 clone25 framed bytes 대 기대10 raw bytes로 실패했다. child 실행·actual-mode reader는 정상이며 stale-source/잘못된 reader 실패가 아니다
- 수정 후 새 normal C++17 clean compile/link·help0, 전체 **147 통과, 실패0/error0/skip0,37.197초**. 기존146개에 legacy clone 파일 보존 회귀1개를 더했다
- 별도 새 ASan+UBSan build의 **focused10 통과, 실패0/error0/skip0,8.688초**. Scribe production/generated13개 object와 fixture를 계측했고 기존 shared dependency transport는 비계측이다
- 첫 sanitizer help는 기본 LSan이 cloud ptrace 제약으로 실패했다. 기존 승인 범위인 `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`, `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`로 help0과focused10을 확인했다. LSan·Thrift 내부·full daemon 성공으로 세지 않는다

새 simple1/2 copy는 source와 같은 raw10 bytes를 기록하며 actual simple reader로 같은 payload를 복원한다. default copy는 기존 framed/padded25 bytes를 유지한다. copy는 closed 상태·새 category 경로로 시작하며 copy close 뒤 source transport가 계속 열려 있음을 확인한다. 기존 clone `_00000`/`_00007` framed bytes는 그대로이고 다음 `_00008`에 raw10 bytes를 기록한다. 이 결과는 기존 파일 자동 변환이나 회사/구 runtime 양방향 호환 검증이 아니다.

현재 focused는10개 method이며 subcases/반복 실행을 고유 시험 수에 더하지 않는다. retained 전후 fixture tree는 copytree가 symlink를 dereference한 byte mirror이며 실제 target은 cleanup 전 통과한 회귀에서 확인했다. 이를 retained tree 자체의 symlink 재검증으로 표현하지 않는다. 독립 normal focused10 재실행도4.703초/skip0으로 통과했고 source·회귀·수정 전 증거 검토에서 blocking finding은 없었다. 전후 retained evidence의 같은4개 method/6개 child도 수정 후4.747초에 통과했으며 각child exit0·parent reap을 확인했다. 최종 문서와 인계 무결성 검증은 별도 기록을 따른다. 같은 production·test 소스의 서버 재검증 결과는 다음 절에 기록하며 아래 v18 결과와 구분한다.

## 수정본 Ubuntu 재검증

Library v19의 archive SHA256 `0904dfc394cdf27c8fdbf9108dec0c23de9a1cc865160176166b4909c65b4cfb`, source163개·manifest1842개·bundle8 refs를 검증해 새 격리 폴더에 복원했다. Ubuntu26.04.1/GCC15.2·기존 Thrift/fb3030.25·Boost1.83 rootless prefix를 사용했다.

- 새 일반 C++17 build와 `scribed --help` exit0, focused **10개/skip0·2.448초**, 전체 **147개/skip0·23.288초**
- 별도 새 ASan+UBSan build/help exit0, focused **10개/skip0·4.767초**. 각 build의 새13개 object와 production/test source 일치를 확인했다. 기존 shared dependency 비계측과 `detect_leaks=0` 경계는 위와 같다
- 별도 raw 관찰 재실행은 normal10개·4.715초, sanitizer10개·9.082초. 각16개 child가 모두 exit0·parent reap·pipe close를 완료했다. 반복/subcase는 고유 시험 수에 더하지 않는다
- simple1/2 source/copy raw10 bytes와 actual simple reader 결과 일치. default copy는 framed/padded25 bytes다. 기존 framed suffix0/7은 각13 bytes 그대로이고 suffix8에 raw10 bytes를 기록했으며 실제 `_current` target을 확인했다
- chunk8/payload9의 기존 오류 로그·생략·성공 반환과 `events_written=1/current_size=9/output=0`, empty를 포함한3건의 성공 집계와2개 event 출력은 그대로다
- 기존4607개 source/build/evidence/dependency/system 기록과 입력source163개의 bytes/mode를 보존했다. 전체 suite의50ms 관찰에서14개 listener는 모두127.0.0.1이며 종료 후 관찰된 listener inode와 owned process-group child가 없었다. 샘플링은 전체 syscall 추적이 아니다

실제 raw349개와 symlink target46개를 회수·검증해 Library v20에 보존했다. raw archive527,275 bytes의 SHA256은 `0a22d01a2f969cf930a051c29fc3276f3b45109c4b94cb2a2915586e30dc0966`이며 자세한 command/log/build·bytes hash는 manifest의 `ubuntu_copy_fix_validation`을 따른다. 게시 준비에서는 이 결과를 문서에 반영했으며 검증된 production·test·IDL·build 파일은 변경하지 않았다.

## 앞선 test-only 관찰 결과

아래는 v17 관찰 source와 v18 서버 재검증의 역사적 결과다. **당시 production·IDL·build 규칙은 바꾸지 않았다.** 기존 fixture를 확장해 Thrift0.25.0의 실제 TFileTransport/TSimpleFileTransport를 관찰했다. 시험 통과는 아래 결함의 해결을 뜻하지 않는다.

- Library v16의158개 committed files·934개 archive records·8개 bundle refs·clean main/fsck를 확인하고 새 checkout으로 복원했다
- 새 Debian13/GCC14 C++17 비-HDFS compile/link와 `scribed --help` exit0. `_GLIBCXX_USE_DEPRECATED=0`도 적용했다
- 기존 main137개를 여기서 직접 재검증: **137 통과, 실패0/skip0,34.132초**. 이전 PR5의 Ubuntu137/ASan82 보고와 구분한다
- 추가 ThriftFileStore9개와 기존 suite를 합친 **146 통과, 실패0/skip0,37.154초**
- 새9개 focused 실행5.034초, 별도 ASan+UBSan focused9개8.602초, 각각skip0
- sanitizer는 새 current Scribe production/generated objects와 fixture를 계측했고 기존 Thrift/fb303/Boost 등 dependency libraries는 비계측이다. `detect_leaks=0`이며 Thrift 내부·full daemon·LSan/TSan/crash-durability 성공을 뜻하지 않는다
- 독립 review의 focused9개 재실행4.712초/skip0과 source·bytes·bounded cleanup·최종 문서 검토도 통과했다. test-only 인계 범위에서 blocking finding은 없으며 미수정 문제와 승인 전 후보를 구분했다

v18에서 수신한 실제 Ubuntu26.04.1/GCC15.2 raw evidence287개도 archive manifest의 크기·hash로 검증했다. 당시 test-only source의 새 clean build·help, focused9/skip0·2.422초, 전체146/skip0·27.045초, 새 ASan+UBSan focused9/skip0·4.693초와13개 child의 정상 종료가 기록돼 있다. 이 숫자는 위 새 copy source의 서버 결과가 아니다.

당시 new9개는 defaults, configured/copy settings, default bytes/empty, simple bytes, chunk padding, reopen, open-model copy, known copy-format mismatch, known over-chunk omission이다. simple 값1/2와 reopen0/1×rotate no/yes 때문에13개 bounded child가 실행되며 이를 고유 시험 수에 더하지 않는다.

## 실제 bytes와 설정

입력은 message `A\0B\n\xff`(5 bytes), empty(0), `ends\n`(5)의3개다. category에는 NUL·비UTF-8·빈 문자열을 넣는다. caller batch 길이와 category/message bytes는 그대로 유지한다.

- 기본 TFileTransport는 nonempty message마다 **native uint32 length + payload**를 쓴다. 현재 little-endian x86 Linux의 독립 golden은 `struct.pack('=I',len)`이다. 일반 spool의 고정 little-endian 계약과 같은 형식이라고 가정하지 않는다
- default 출력은 두9-byte event, 총18 bytes. 실제 non-tailing TFileTransport reader가2개 event의10 payload bytes를 복원한다. empty event는 없다
- chunk_size16은 첫9-byte event 뒤7-byte zero padding과 두 번째9-byte event로 총25 bytes다. reader에도 같은 chunk setting을 적용해 읽는다
- use_simple_file1/2는 raw payload를 이어붙인10 bytes다. 실제 TSimpleFileTransport reader로 같은 bytes를 읽지만 event 경계나 empty entry는 복원하지 않는다
- write_category=yes/add_newlines=1을 주어도 ThriftFileStore는 category/LF를 추가하지 않는다. 원본 payload의 LF만 보존된다. ordinary FileStore 옵션 동작으로 확대하지 않는다
- 기본 transport chunk16,777,216/flush3,000,000µs/event buffer10,000, Scribe 설정값0/0/0을 관찰했다. chunk16/flush_frequency_ms7/msg_buffer_size3은 실제 transport16/7000/3으로 전달되고 default-mode copy도 유지한다
- simple transport는 chunk/flush/event-buffer 설정을 적용하는 TFileTransport 객체가 아니다
- open 모델의 copy는 live transport를 공유하지 않으며 새 category의 별도 하위 경로·파일명과 sub_directory/기존 symlink policy를 사용한다
- close 후 reopen은 rotate_on_reopen=no/yes 모두 새 suffix를 사용한다. 기존 `_00000`/`_00007` bytes는 유지하고 `_00008`/`_00009`를 생성했다. ordinary FileStore append policy와 구분한다

## 수정 전 확인한 문제

1. **simple mode copy가 format을 바꾼다.** source는 use_simple_file1/raw10 bytes인데 실제 copy는 useSimpleFile0/TFileTransport25 bytes다. source/clone 각각의 올바른 reader로 nonempty10 bytes는 읽힌다. `ThriftFileStore::copy`가 useSimpleFile을 복사하지 않는 것은 고정 공개 upstream와 현재 main 모두의 source에서 확인했다. 이 정적 비교는 구 runtime differential 실행이 아니다
2. **표현 불가능한 event가 성공으로 집계된다.** 기본 mode의 empty entry는 transport가 event로 쓰지 않지만 Scribe events_written3/current_size10에 포함된다. chunk_size8에9-byte message(4-byte header 포함13)를 보내면 handleMessages=true·caller1개 그대로·events_written1/current_size9인데 정상 close 후 파일/readback0 bytes다. 이 tiny fixture의 결과로 모든 오류·거대 입력을 검증했다고 주장하지 않는다

기본 TFileTransport chunk16MiB에서 event header4 bytes를 포함한 frame이 chunk보다 크면 같은 deterministic omission 경로가 가능하다. 이는 network의256MiB 한도와 별개다. 이번 실행은9-byte/8-byte 작은 재현이며16MiB+ 또는256MiB+ 거대 event를 새로 만들지 않았다. 사용자는 이 초과 경로를 기존처럼 Thrift에 넘겨 동작을 유지하도록 결정했다. empty event도 새 정책으로 변경하지 않는다. [승인 범위와 보존 결정](thriftfile-fix-options.md)을 따르며 새 실패 파일·분할·재시도·lost 계측을 추가하지 않는다.

## close·flush와 안전 경계

ThriftFileStore::flush는 production no-op이다. default close는 TFileTransport 참조를 해제해 writer destructor/join을 완료한 뒤 reader를 연다. 해당 transport source는 정상 종료/주기 flush에서 fsync를 호출하지만 이번 fixture는 fsync system call을 계측한 durability 시험이 아니다. simple close의 descriptor 해제도 durable ACK를 뜻하지 않는다. handler ACK는 기존 queue 수락이며 비동기 writer의 모든 실제 I/O 결과를 동기 확인하는 API가 아니다.

각 새 fixture에는10초 C++ alarm이 있다. 통합 suite의 공유 subprocess deadline은20초이며 별도 raw-evidence runner는15초 owner timeout을 사용한다. reader는128-byte buffer,8회/256-byte 출력 상한과 non-tailing EOF를 사용한다. payload는 작고 모든 파일은 소유 temporary directory 아래다. transport writer는 정상 close/join 후 읽으며 동시 동일-file writer를 만들지 않는다. 새 sockets·서비스·namespace·권한·의존성 설치·commit/push/merge는 없다. 전체 기존 suite의 loopback 시험은 이전과 같은 격리 경계를 사용한다.

## 남은 검증

- 이 단계는 현재0.25 source의 small golden/readback이다. 회사 binary와 old-write/new-read/new-write/old-read, endianness/platform matrix·손상/복구·I/O failure·crash·성능·thriftmultifile 전체는 미완료다
- simple-copy의 승인된 한 필드 수정과 회귀 결과는 위 후속 기록을 따른다. empty/over-chunk의 생략·성공 집계는 사용자 결정대로 유지하며 유실 문제 해결로 표현하지 않는다
- 이전 다섯 store 수정은 PR5/main에 이미 반영됐으며 이번 단계에서 중복 구현하지 않았다. 기존137개 regression을 유지했다
- retained ordinary spool256MiB 초과, 실제 production CLI listener, 회사 old/new 동등성과 Gate A–D 전체는 계속 미완료다

## 서버 재현과 인계

기존 승인된 matched Thrift/fb3030.25/Boost/libevent/Autotools prefixes를 사용해 새 source copy에서 [README recipe](../README.md#검증된-linux-c-빌드-recipe)를 실행한다. source/generated code/object freshness 검사를 유지하며 cloud objects/binaries를 복사하지 않는다.

```sh
export THRIFT_PREFIX=/absolute/existing/thrift-0.25.0
export FB303_PREFIX=/absolute/existing/fb303-0.25.0
export TOOLS_PREFIX=/absolute/existing/tools/usr
export SCRIBE_BUILD=/absolute/new-source-matching-built-copy
python3 -B -m unittest discover -s test -p test_scribe_api_compat.py -k thriftfile -v
python3 -B -m unittest discover -s test -p 'test_*.py' -v
git diff --check
sh -n bootstrap.sh
```

수정본 기대값은 focused10/total147,skip0이다. tiny raw/default/copy bytes와 legacy files의 bytes 보존, owned child의 exit/cleanup, source bytes/modes, 실행command/log/binary hash를 보존한다. ASan+UBSan lane은 별도의fresh build와`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`로 같은focused10을 실행한다. 기존dependency libraries의 비계측과leak 검사 제외를 명시한다.

checkpoint에는source, credential-free history, 이번과 이전의raw evidence, 복원 검증과 재현 명령을 포함한다. dependency caches, ELF/object, 개인Git 설정, runtime spool이나 인증 값은 제외한다. copy 설정 보존은 승인 범위다. 사용자는 검증된 characterization/copy 배치의 commit·push·main merge를 별도로 승인했다. 서비스 기동·배포는 포함하지 않으며 최종 게시 식별자는 Git 이력과 Library 인계를 따른다.
