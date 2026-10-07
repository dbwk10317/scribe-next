# Rocky daemon 전용 개발 RPM

아래 `dc0e327`와 RPM hashes는 당시 검증 이력이다. 후속 안전성 변경과 fb303 patch 뒤에는 최종 commit으로 새 RPM을 생성하고 그 source_revision·package hash·격리 검증 manifest를 별도로 기록한다. 이전 RPM에 후속 수정이 포함됐다고 해석하지 않는다.

2026-10-06. Source `dc0e3274c914bab81009be8cf3e2b07bfbd860bd`의 원본 version 1.5.0에
개발 release `0.1.gdc0e327.el8`/`.el9`를 붙여 Rocky 8.10/9.8에서 각각 빌드했다.
production source 수정 없이 기존 bootstrap/configure/make와 rpmbuild를 사용한다.
양쪽 clean build, package 생성과 격리 install/verify/help/remove가 성공했다.
이는 unsigned 개발 RPM이며 운영 release나 host 설치 승인이 아니다.

## 포함 범위와 의존성

[spec](../packaging/rocky/scribe-next-dev.spec)은 `scribe-next-dev` daemon 전용이다.
기본 env_default·비-HDFS·static RPC를 사용한다. CLI 이름은 `scribed`이며 payload는
`/opt/scribe-next-dev`에 있다. Python client, config, user/group 생성, service unit와
service scriptlet은 포함하지 않는다. 기존 `scribe` Python client 설치를 덮어쓰지 않는다.

Thrift 0.25.0 runtime과 matching fb303 static code를 private
`deps` prefix로 실제 빌드·링크한다. [fb303 safety patch](fb303-counter-safety.md)는 별도 source copy에만 적용한다. 기존 `/opt/tools` 라이브러리를 옮겨 성공을 만들지
않는다. scribed는 Boost 라이브러리를 링크하지 않으므로 RPM에 Boost runtime을 넣지 않는다.
Thrift 0.25.0 빌드와 Thrift·fb303 header가 요구하는 Boost 1.83 header만 private prefix에 준비한다.
compiler/runtime 버전과 source hash는 [Rocky 빌드 안내](rocky-build.md)를 따른다.

libevent, glibc, libgcc와 libstdc++는 배포판 의존성이다. RPM 자동 Requires/Provides와
`bundled(thrift/fb303)`를 유지하며 `--nodeps`나 private dependency 예외로 검사를
끄지 않는다. Rocky 8은 libevent soname 6, Rocky 9는 soname 7과 각 compiler ABI를 사용한다.
두 RPM을 다른 major 버전용으로 주장하지 않는다. dependency package 준비는 정상 DNF
GPG 검사를 유지한다. 이미지 digest 고정을 이미지 signature 검증으로 부르지 않는다.

Scribe LICENSE, Thrift LICENSE/NOTICE, fb303 자체 LICENSE와 전체 Apache license/NOTICE의
6개 원문을 `%license`로 수록한다. Boost 라이브러리를 동봉하지 않으므로 Boost LICENSE는 넣지 않는다. 실제 설치 bytes의 SHA256을
[고정 기대값](../packaging/rocky/expected-licenses.json)과 비교했다. 이는 법적 보장이 아닌
고정 원문의 수록 확인이다. Bison/Git은 build tool이며 RPM runtime에 동봉하지 않는다.

## 프로젝트 전용 컨테이너에서 재현

호스트 RPM 설치·제거와 다른 컨테이너 변경을 수행하지 않는다. 먼저 Rocky 빌드 안내의
고정 image·source·matching toolchain을 준비한다. build context는 프로젝트 전용으로
만들고 [dependency Dockerfile](../packaging/rocky/Dockerfile.dependencies) 및
[runtime Dockerfile](../packaging/rocky/Dockerfile.runtime)을 복사한다.

```sh
# MAJOR=8 or 9; BASE is the matching pinned RESF digest in rocky-build.md
# CONTEXT contains packaging Dockerfiles plus tools/prepare_fb303.py and
# dependencies/fb303-0.25.0-counter-lock.patch under their basenames
# TOP is a new writable project-owned RPM output directory

docker build -f "$CONTEXT/Dockerfile.dependencies" \
  --build-arg BASE="scribe-next-rocky-validation:$MAJOR" \
  -t "scribe-next-rocky-rpm-builder:$MAJOR" "$CONTEXT"
docker build -f "$CONTEXT/Dockerfile.runtime" --build-arg BASE="$BASE" \
  -t "scribe-next-rocky-rpm-runtime:$MAJOR" "$CONTEXT"

REVISION=$(git rev-parse HEAD)
mkdir -p "$TOP"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
git archive --format=tar.gz --prefix=scribe-next-1.5.0/ "$REVISION" \
  > "$TOP/SOURCES/scribe-next-1.5.0.tar.gz"
cp packaging/rocky/scribe-next-dev.spec "$TOP/SPECS/"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 6g --pids-limit 512 \
  --mount "type=bind,src=$TOP,dst=/rpmbuild" \
  "scribe-next-rocky-rpm-builder:$MAJOR" rpmbuild -ba \
  --define '_topdir /rpmbuild' --define "source_revision $REVISION" \
  --define "development_release 0.1.g${REVISION:0:7}" --define "dist .el$MAJOR" \
  --define 'thrift_source /sources/thrift-0.25.0' /rpmbuild/SPECS/scribe-next-dev.spec
```

Source archive hash와 full revision을 결과에 기록한다. SRPM도 생성하지만 matching 의존성
source/prefix는 위 recipe로 준비해야 한다. SRPM 단독으로 의존성을 자동 준비하지 않는다.

[컨테이너 검증 script](../packaging/rocky/verify-container.py)는 Docker 컨테이너 안의 root만
실행하도록 제한한다. root는 컨테이너 RPM database를 갱신하는 데 사용하며 host bind는
read-only, network none, cap-drop ALL, no-new-privileges를 유지한다. `/verify.py`에 script,
`/expected-licenses.json`에 고정 기대값, `/packages`에 RPM 폴더를 read-only bind하고
matching runtime image의 `/usr/libexec/platform-python -B /verify.py /packages/<rpm>`을 호출한다.
script는 Requires/Provides, 빈 scriptlet, `rpm -V`, 6개 license hash, Boost가 없는 loader closure,
설치된 help와 실제 daemon RPC·동일 RPM 재설치, 제거 후 package 디렉터리 및
3개 build-id 링크 삭제를 확인한다. 기존 `test/loopback_rpc.py`도 `/loopback_rpc.py`에
read-only bind한다. 설치된 Python Thrift client 대신 기존 독립 IDL wire helper를 사용한다.
RPM의 표준 build-id metadata는 payload를 가리키는 symlink인지 검사한다.
다른 패키지와 공유하는 시스템 디렉터리 전체를 지우도록 요구하지 않는다.

## 확인 결과와 남는 범위

| Rocky | Binary RPM SHA256 | 결과 |
| --- | --- | --- |
| 8.10 | `8b3945583e0e7b939263528f56b3a1d9d8a7469b72cf0f11308825aeac314f25` | build/install/verify/licenses/help/remove PASS |
| 9.8 | `3a24b0bb1cf70a2e44ade80838c930f40f64dcdaa37f530b25f17b7ce2be0192` | build/install/verify/licenses/help/remove PASS |

`LD_LIBRARY_PATH` 없이 private Thrift/Boost를 읽는 것을 확인했다(위 두 RPM은 Boost 제거 전 결과다). 첫 검증 script는 RPM이
생성하는 build-id 경로를 예상하지 못해 실패했다. 기대 경로를 바로잡고 새 컨테이너에서
payload 안으로 향하는 링크 및 제거 후 삭제까지 확인했다. 실패 기록을 성공으로 세지 않는다.

2026-10-07 Boost 제거(현대화 2단계) 뒤 작업 tree로 Rocky 8.10/GCC 8.5 RPM을 다시 만들었다.
configure가 `-lstdc++fs`를 붙였고, 격리 install/verify, 6개 license hash, 3개 build-id 링크,
Boost가 없는 `ldd`, 설치된 daemon의 송수신·동일 RPM 재설치·제거가 통과했다. Rocky 9 RPM은 다시 만들지 않았다.

각 major의 기본 userland 패키지 검증이며, 서로 다른 버전 간 upgrade, 비정상 중단,
HDFS/shared RPC와 production kernel/service 배포는 미검증이다.
기존 core 218 tests/skip 0과 actual old/new 검증 범위를 이 RPM help 결과로 넓히지 않는다.

## 설치된 daemon과 동일 RPM 재설치

위 두 개발 RPM을 새 Rocky 8/9 runtime 컨테이너에 실제 설치한 뒤 각 2회 daemon을
실행했다. namespace는 network none이며 source/RPM/script mounts는 read-only다.
고정 포트 1463은 이 전용 namespace 안에서만 사용하며 포트를 publish하지 않는다.
client의 127.0.0.1 peer와 실제 child가 소유하는 listener socket inode도 검사한다.

각 실행에서 ALIVE status, framed binary `Log`의 OK, `accepted:received good` counter,
기존 fb303 oneway `shutdown`과 exit 0을 확인한다. `add_newlines=0`·rotation never의
file fixture를 사용하며 queue 수락 ACK와 실제 파일 완료를 구분한다. shutdown 뒤
정확한 bytes를 비교하므로 정상 종료의 worker flush도 검증한다. timeout이 나면 owned
child만 terminate/kill/reap하고 해당 실행을 실패로 처리한다.

첫 종료 후 파일은 `4100420affc3a96265666f72650a`이고 수신 count는 2다.
`rpm -U --replacepkgs`로 **같은 RPM**을 재설치하며 `rpm -V`, 고정 설정·로그의
bytes/hash·mode·uid/gid 보존을 검사한다. 재시작해 메시지 1개를 더 보내고 정상
shutdown 후 같은 파일은 `4100420affc3a96265666f72650a7461696c00ff0a`다.
재시작한 프로세스의 수신 count는 1이다. 두 Rocky에서 모든 단계가 성공했다.
fixture는 컨테이너 안 새 임시 폴더이며 사용자 데이터가 아니다. 이를 다른 원본 버전의
upgrade·downgrade 안전성이나 durable ACK·exactly-once 보장으로 확대하지 않는다.
