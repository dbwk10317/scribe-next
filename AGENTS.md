# scribe-next 개발 지침

이 파일이 저장소의 공통 개발 지침이다. `CLAUDE.md`는 이 파일을 안내하는 진입점이다.
저장소 밖 지침이 실제로 존재하면 먼저 읽되 개인 컴퓨터의 경로나 도구 설정을 가정하지 않는다.
사용자의 최신 명시 지시가 이전 문서와 승인보다 우선한다.

## 목표와 먼저 읽을 문서

공개 [Facebook Scribe 원본](https://github.com/facebookarchive/scribe/tree/fcd294faffd1e88af1643a3a8c2359c41713f7c2)을
현대 Linux에서 빌드하면서 기존 구조와 외부 계약을 보존한다. 회사 fork·설정·성능 자료는 현재 범위 밖이다.

작업 전에 [README](README.md)와 [현재 호환성 정책](docs/legacy-compatibility-policy.md)을 읽는다.
빌드·실행 작업은 [빌드 안내](docs/linux-build-mvp.md), HDFS는 [HDFS 안내](docs/hdfs-compatibility.md)를 추가로 읽는다.
기존 설계가 필요한 변경은 [설계](docs/design.ko.md)와 [구현 계획](docs/implementation.ko.md)을 확인한다.
과거 검증 기록을 현재 코드의 성공이나 미완료 조건으로 그대로 해석하지 않는다.

## 원본 계약 보존

최신 방침은 구·신 송수신 양방향 혼용과 기존 로그 소비 client의 계약을 우선한다.
로그의 분배·내용·파일 형식·전달·손실 집계·상태 조회를 바꾸는 semantic 수정은 원본의 정의된 동작으로 되돌렸다.
그 버그는 문서에 남기며 새 수정 옵션을 추가하지 않는다. UB/crash 방지는 유지하되 미정의 결과 자체를 재현하지 않는다.
예외로 2026-10-07에 분배·파일 형식·전달 결과를 바꾸지 않는다고 확인한 세 가지(동적 목적지의 pooled close 순서,
service_list 재연결 후보 누적, StdFile partial replay 보존)만 [정책](docs/legacy-compatibility-policy.md#다시-고친-동작-2026-10-07)대로 다시 적용했다.

- 두 IDL의 method, field ID, enum, requiredness, namespace, 예외와 fb303 API를 유지한다
- framed binary 및 server·relay·mapping의 명시적 strictRead=false/strictWrite=false를 유지한다
- category/message bytes를 정규화하거나 줄바꿈을 보정하지 않는다. 기존 옵션의 줄바꿈 추가도 유지한다
- queue byte 계산, batch, retry, 실패 처리 우선순위, shutdown, lock 순서·범위를 임의로 바꾸지 않는다
- 10 store, 설정 이름·기본값·상속·오류 처리, CLI 우선순위, routing/hash, 파일 이름·rotation·`_current`를 유지한다
- 일반 spool의 little-endian frame과 ThriftFile 형식을 구분하고 구→신·신→구 writer/reader를 대표 조건으로 확인한다
- `OK`는 메모리 큐 수락이다. durable ACK, exactly-once나 fsync를 새로 보장하지 않는다
- 같은 data/spool에 구·신 프로세스를 동시에 쓰게 하지 않고 파일을 자동 변환·삭제하지 않는다

현재 이식본의 frame/message 기본 한도는 각각 256 MiB이며 server·relay·mapping에 일관되게 적용한다.
초과 relay batch를 자동 분할하거나 버리지 않는다. 큰 retained spool의 반복 재시도는 남은 한계다.
원본 ThriftFile의 empty/청크 초과 처리·로그·반환·성공 집계도 유지한다.
새 외부 동작 차이를 발견하면 재현 결과와 영향부터 보고하고 정책을 조용히 바꾸지 않는다.

## 근본 원인 우선

증상을 피하는 임시 경로보다 원인을 재현하고 정상 설정·계약을 바로잡는 일을 먼저 한다.
임시 우회가 불가피하면 사유·한계·영구 해결 계획을 설명하고 사용자 승인을 받는다.
권한·보안 제한을 우회하지 않는다. 이 원칙을 이유로 사용자가 선택한 원본 호환 동작을 다시 바꾸지 않는다.

## 작고 검증 가능한 변경

기존 함수·driver·autotools와 표준 라이브러리를 먼저 사용한다.
요청과 이식에 필요한 부분만 바꾸고 일괄 formatting, 전체 Boost 제거, build system 교체,
새 framework·registry·transport·thread 설계, 미리 만드는 기능과 의존성을 추가하지 않는다.
빌드 복구와 외부 동작 변경을 한 변경에 섞지 않는다.

관련 호출 경로를 읽고 완료 조건을 정한 뒤 수정한다. 버그 수정은 실패 재현과 수정 후 확인을 남긴다.
한 변경에 맞는 최소 시험을 실행하며 반복·subcase를 고유 시험 수로 합산하지 않는다.
문서 수정만으로 불필요한 C++ 재빌드나 성능 시험을 하지 않는다. 상세 성능 비교는 현재 보류다.

## 빌드와 결과 기록

- Linux x86_64, C++17, 같은 버전의 Thrift compiler/runtime 0.25.0와 맞춰 준비한 fb303를 사용한다
- Boost system/filesystem, libevent와 실제 dependency prefix/include/link 경로를 명시한다. 직접 configure할 때는 `--with-boost`, `--with-boost-system=boost_system`, `--with-boost-filesystem=boost_filesystem`을 지정한다
- 사용자 CFLAGS/CXXFLAGS의 명시값과 빈 값을 보존한다. generated code는 규칙으로 생성하고 손으로 고치지 않는다
- 기본 검증은 `tools/validate_linux.py`를 프로젝트 밖의 새 출력 폴더에 실행한다. 이는 임시 설치이며 service 기동이 아니다
- 선택 shared RPC와 HDFS는 기본 빌드와 구분한다. HDFS 기능을 삭제하거나 기본 검사만으로 HDFS 성공을 주장하지 않는다
- source·generated·dependency 일치 검사를 우회하거나 예전 objects를 복사해 성공을 만들지 않는다
- 실제 daemon 결과, component/모의 결과, static 검토와 미실행을 구분한다. 한 환경 성공을 전체 호환성이나 운영 준비 완료로 확대하지 않는다
- sanitizer 범위와 skip·실패를 기록하며 LSan/TSan 미실행을 성공으로 세지 않는다
- 실행 권한이나 격리가 없으면 namespace·network·보안 제한을 우회하지 않는다. 설치·배포·실제 서버 실행은 승인된 환경과 범위에서만 한다

원본 source 조회는 Git의 object-free capability 확인을 먼저 한다.
`--no-lazy-fetch`와 `--no-replace-objects`를 모두 유지하고 미지원 Git과 누락 object를 구분한다.
보호 flag 제거와 자동 fetch fallback을 추가하지 않는다. 원본 도입의 content 검사와 의도된 이식 diff를 구분한다.

## 저장소와 고지

관련 파일만 stage한다. 기존 사용자 변경을 보존하고 전역 Git 설정·임의 identity를 바꾸지 않는다.
인증 정보, 개인 절대경로, cache·실행 파일·objects·runtime spool과 거대 실행 결과를 commit하지 않는다.
실행 raw는 별도 보관하고 문서에서 필요한 결과와 출처만 연결한다.

원본 LICENSE, copyright·attribution과 존재하는 NOTICE를 보존한다.
변경된 원본 파일에는 실제 변경 사실을 표시하되 임의 권리자나 법적 보장을 만들지 않는다.
의존성을 동봉하는 배포는 해당 LICENSE/NOTICE도 확인한다. source 검증을 배포 승인으로 해석하지 않는다.

## 적용할 원문 지침

요약만으로 대체하지 않고 다음 고정 원문을 실제로 읽는다.
이미 가진 사본은 SHA256이 일치하는지 확인한다. 원문을 구할 수 없으면 그 사실을 보고한다.

- [Karpathy guidelines](https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/2c606141936f1eeef17fa3043a72095b4765b9c2/skills/karpathy-guidelines/SKILL.md)
  - SHA256: `6e22cc54cb02a5e98ae42d06d9d7292db0c1b43894831b32879beb0166b2aea7`
- [Ponytail](https://raw.githubusercontent.com/DietrichGebert/ponytail/6d6317716fb15eb1bafb898f74498bd9331b31c8/skills/ponytail/SKILL.md)
  - SHA256: `1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2`

핵심은 변경 전 가정·영향을 확인하고, 기존 기능을 재사용하며, 가장 작은 수정과 실행 가능한 확인으로 끝내는 것이다.
