# 첫 actual-daemon old/new 비교의 재사용 harness

2026-10-05 · base main `fc3767bc4b44646e3eb232d65aa77ae47447d5fa`

## 실제 선행 결과와 이번 범위

공개 원본 `fcd294f` + Thrift/fb3030.9.0 daemon과 현재0.25 daemon을 각각의
runtime/ABI로 실제 실행한 첫 synthetic batch가 성공했다. 원본에는 승인된
autotools 한 줄 build-only patch만 적용됐고 현대화 production patch를 덮지 않았다.
현재 daemon binary SHA256은 `7142824130803f679ac7986bba1309413a1728e32924fdb5e7fa86d94e43c6f5`다.
당시 검증 source621dfd와 현재main의 production26개 bytes는 같았다.

두 lane의 요청9개와 비교한 응답7개 bytes가 일치했고 getVersion은 양쪽2.2였다.
getName/status/details/counters, 빈 Log, 정상3개(NUL/LF/non-UTF8 및 빈 payload
포함), 빈 category와 미정의 category 각각1개, oneway shutdown을 실행했다.
counter delta가 같고 파일9 bytes `4100420aff7461696c` 및
fixture_current → fixture_00000도 같았다. 양쪽 exit0과 listener 회수를 확인했다.
Docker는 networknone/lo-only/noports/nomount/uid65534/resource limits로 실행했고
기존 운영30개 container ID는 유지했다. 이것은 한 batch의 원본 대조다.

이번 변경은 당시 stdlib Python2/3 client/config를 tools/daemon_differential.py로
정리한 것이다. C++/IDL/store/배포 변경은 없다. source evidence archive SHA256은
`a9aeceba8c5d653c223b55d0ae30f33b83ae7e43b7a1288b91d546d5432db67f`다.
test/fixtures/first_daemon_differential에는 두 lane에서 실제 같았던 요청9/응답8
파일과 개인 경로·PID·command를 제외한 expected report만 보존한다. getVersion
raw 응답도 replay하지만 byte-equality 항목7개와 별도 identity 확인을 구분한다.
원본 실행 로그/개인 절대경로는 저장소에 넣지 않는다.

## 실제 실행은 별도 opt-in

이 도구는 Docker/namespace/dependency/권한을 설정하지 않는다. 이미 승인된
격리 환경을 준비한 뒤 old/modern의 절대 executable argv와 명시적 환경을 받는다.
modern은 필요하면 이미 검증한 loader + --inhibit-cache/--library-path argv를
command에 넣고 마지막에 scribed binary를 둔다. harness가 -c와 새 config를 붙인다.
LD_PRELOAD/LD_AUDIT injection은 거부하고 ambient LD_LIBRARY_PATH는 상속하지 않는다.

```json
{
  "old": {
    "command": ["/prepared/old/bin/scribed"],
    "environment": {"LD_LIBRARY_PATH": "/prepared/old/thrift/lib:/prepared/old/fb303/lib"}
  },
  "modern": {
    "command": ["/prepared/modern/lib/ld-linux-x86-64.so.2", "--inhibit-cache", "--library-path", "/prepared/modern/lib", "/prepared/modern/bin/scribed"],
    "environment": {}
  }
}
```

```sh
python tools/daemon_differential.py --run-isolated-daemons \
  --targets /prepared/targets.json --output /prepared/new-comparison-output
```

real/effective uid65534와 /sys/class/net의 lo-only, 새 checkout 밖 output, 사전 포트 비점유를
검사한다. 두 lane은 별도 output에서 순서대로 실행한다. client는127.0.0.1만
연결한다. 첫 RPC 전에 /proc의 established socket inode가 소유한 child PID의
fd인지 대조하며 확인할 수 없으면 요청을 보내지 않는다. child는 독립 session으로
실행하고 실패 시 그 session의 process group만 TERM/KILL하고 child를 wait한다.
stream/socket도 닫는다. 다른 process/group을 이름으로 찾아 종료하지 않는다.
기존 listener를 사용하거나 종료하지 않는다. 실제 Docker noports/nomount/limits와
networknone 상태는 외부 실행자가 별도로 확인해야 한다. host network, privileged,
Docker socket mount나 namespace/security 우회로 guard를 통과시키지 않는다.

출력은 evidence/{old,modern}/의 request/reply bytes, daemon stdout/stderr,
start/result.json과 evidence/comparison.json이다. 실제 command/path/PID는 이
consumer-local evidence에만 기록한다. 파일·counter·request sequence가 누락되거나
손상됐거나 실패한 lane이면 비교를 통과시키지 않는다.

## 이번 cloud 검증과 다음 순서

cloud에서는 새 actual daemon을 실행하지 않는다. namespace 제약을 우회하지 않고
검증된 wire/report replay, 잘못된 evidence 거부, isolation/port guard, fake child의
protocol 실패 cleanup/session kill fallback/연결 소유권만 독립 unittest로 검사한다. 이7개는 live daemon 성공 횟수가
아니다. 후속 서버 재검증에서 같은 source의 전체160개 시험이 failure/error/skip0으로
통과했다. 기존 compiled production과 source bytes를 확인하고 새 harness를 승인된
networknone 컨테이너에서 한 번 실행했다. 두 lane 모두 첫 RPC 전에 owned child의
소켓 inode를 확인했고 요청9/비교 응답7, version2.2, counter/file/symlink 및
shutdown exit0 비교가 통과했다. old/new runtime30개(바이너리 포함)의 hash와 loader/help를 확인했으며 운영30개 container ID도 유지됐다.
새 clean build는 수행하지 않았고, old/new runtime/ABI 차이는 유지했다.

다음 coverage는 null/multi/category의 구성·fan-out·clone routing, 그다음 file
rotation·재시작/reinitialize, 이어서 spool/relay의 장애·재시도 순으로 우선순위를
잡는다. 이번 PR에는 새 store workload를 추가하지 않는다. 전체10 store, bucket
mapping, 모든 fb303 method, old/new 양방향 spool 및 성능 완료로 확대하지 않는다.
기존 승인된 bug-fix 차이는 명시하며 oversized/empty 처리 보존 결정도 유지한다.
