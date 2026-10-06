# Rocky daemon 전용 개발 RPM

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

Thrift 0.25.0 runtime, matching fb303 static code와 Boost 1.83 runtime을 private
`deps` prefix로 실제 빌드·링크한다. 기존 `/opt/tools` 라이브러리를 옮겨 성공을 만들지
않는다. Boost filesystem의 atomic dependency도 포함한다. compiler/runtime 버전과
source hash는 [Rocky 빌드 안내](rocky-build.md)를 따른다.

libevent, glibc, libgcc와 libstdc++는 배포판 의존성이다. RPM 자동 Requires/Provides와
`bundled(thrift/fb303/boost)`를 유지하며 `--nodeps`나 private dependency 예외로 검사를
끄지 않는다. Rocky 8은 libevent soname 6, Rocky 9는 soname 7과 각 compiler ABI를 사용한다.
두 RPM을 다른 major 버전용으로 주장하지 않는다. dependency package 준비는 정상 DNF
GPG 검사를 유지한다. 이미지 digest 고정을 이미지 signature 검증으로 부르지 않는다.

Scribe LICENSE, Thrift LICENSE/NOTICE, fb303 자체 LICENSE와 전체 Apache license/NOTICE,
Boost LICENSE_1_0.txt의 7개 원문을 `%license`로 수록했다. 실제 설치 bytes의 SHA256을
[고정 기대값](../packaging/rocky/expected-licenses.json)과 비교했다. 이는 법적 보장이 아닌
고정 원문의 수록 확인이다. Bison/Git은 build tool이며 RPM runtime에 동봉하지 않는다.

## 프로젝트 전용 컨테이너에서 재현

호스트 RPM 설치·제거와 다른 컨테이너 변경을 수행하지 않는다. 먼저 Rocky 빌드 안내의
고정 image·source·matching toolchain을 준비한다. build context는 프로젝트 전용으로
만들고 [dependency Dockerfile](../packaging/rocky/Dockerfile.dependencies) 및
[runtime Dockerfile](../packaging/rocky/Dockerfile.runtime)을 복사한다.

```sh
# MAJOR=8 or 9; BASE is the matching pinned RESF digest in rocky-build.md
# CONTEXT contains the two packaging Dockerfiles only
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
  --define 'thrift_source /sources/thrift-0.25.0' \
  --define 'boost_source /sources/boost_1_83_0' /rpmbuild/SPECS/scribe-next-dev.spec
```

Source archive hash와 full revision을 결과에 기록한다. SRPM도 생성하지만 matching 의존성
source/prefix는 위 recipe로 준비해야 한다. SRPM 단독으로 의존성을 자동 준비하지 않는다.

[컨테이너 검증 script](../packaging/rocky/verify-container.py)는 Docker 컨테이너 안의 root만
실행하도록 제한한다. root는 컨테이너 RPM database를 갱신하는 데 사용하며 host bind는
read-only, network none, cap-drop ALL, no-new-privileges를 유지한다. `/verify.py`에 script,
`/expected-licenses.json`에 고정 기대값, `/packages`에 RPM 폴더를 read-only bind하고
matching runtime image의 `/usr/libexec/platform-python -B /verify.py /packages/<rpm>`을 호출한다.
script는 Requires/Provides, 빈 scriptlet, `rpm -V`, 7개 license hash, loader closure,
설치된 help와 제거 후 package 디렉터리 및 6개 build-id 링크 삭제를 확인한다.
RPM의 표준 build-id metadata는 payload를 가리키는 symlink인지 검사한다.
다른 패키지와 공유하는 시스템 디렉터리 전체를 지우도록 요구하지 않는다.

## 확인 결과와 남는 범위

| Rocky | Binary RPM SHA256 | 결과 |
| --- | --- | --- |
| 8.10 | `8b3945583e0e7b939263528f56b3a1d9d8a7469b72cf0f11308825aeac314f25` | build/install/verify/licenses/help/remove PASS |
| 9.8 | `3a24b0bb1cf70a2e44ade80838c930f40f64dcdaa37f530b25f17b7ce2be0192` | build/install/verify/licenses/help/remove PASS |

`LD_LIBRARY_PATH` 없이 private Thrift/Boost를 읽는 것을 확인했다. 첫 검증 script는 RPM이
생성하는 build-id 경로를 예상하지 못해 실패했다. 기대 경로를 바로잡고 새 컨테이너에서
payload 안으로 향하는 링크 및 제거 후 삭제까지 확인했다. 실패 기록을 성공으로 세지 않는다.

각 major의 기본 userland 패키지 검증이며, 패키지 안 실제 daemon의 송수신, upgrade,
reinstall, 비정상 중단, HDFS/shared RPC와 production kernel/service 배포는 미검증이다.
기존 core 218 tests/skip 0과 actual old/new 검증 범위를 이 RPM help 결과로 넓히지 않는다.
