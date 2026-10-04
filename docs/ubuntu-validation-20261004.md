# Ubuntu 26.04의 격리 C++ 빌드 검증

2026-10-04 UTC · 검증 source commit [`96a7fc1868639dcf4d479c0d94ab0886fb2776d3`](https://github.com/dbwk10317/scribe-next/commit/96a7fc1868639dcf4d479c0d94ab0886fb2776d3)

[클라우드 API 이식 기록](api-compat-status.md)의 동일 코드를 봉구서버에서 검증했다. Ubuntu 26.04.1 x86_64, GCC 15.2.0, C++17, 공식 Boost 1.83.0, Thrift compiler/runtime 0.25.0, 같은 release의 fb303, libevent 2.1.12, OpenSSL 3.5.5를 사용했다. source 124개 파일에 추가 변경 없이 기본 비-HDFS C++ lane의 clean compile/link와 집중 시험을 통과했다. 버전·패키지 SHA256·산출물·기록 위치는 [Ubuntu manifest](ubuntu-build-manifest.json)에 고정했다.

## 실제 결과

| 검증 | 결과 |
| --- | --- |
| Thrift compiler 및 C++ runtime | 빌드·작업 폴더 prefix 설치 성공 |
| Thrift upstream C++ 시험 | 29 실행 단위 PASS, skip 0; 초기 locale 실패와 최종 성공 구분 |
| fb303 C++ | build 및 작업 폴더 prefix 설치 성공 |
| Scribe `make -C src clean` 후 `make -C src -j2` | compile/link 성공 |
| 프로젝트 집중 시험 | 38 PASS, skip 0; mutex는 assertions on/off 포함 |
| `scribed --help` | exit 0, 기존 usage 출력 |
| 엄격한 원본 도입 비교 | exit 1, 기존 build/API 수정 15개 content mismatch만 보고 |
| source·시스템 불변성 | Scribe 124개 및 공식 Thrift 3,112개 파일 동일, dpkg 상태·APT source 해시 동일 |

Scribe 바이너리는 1,043,352 bytes이며 SHA256은 `109e00cd10593ec04ff3de68ada6a29af0162eaf931e155cee868567a684335c`다. `readelf`/`ldd`에서 의도한 공유 Thrift·Boost·libevent와 기존 시스템 OpenSSL을 확인했고 missing library는 없었다. 경로·도구가 포함된 단일 빌드의 식별값이며 다른 환경의 binary hash 일치를 보장하지 않는다.

## 의존성 준비와 실패 기록

새 작업 경로는 `/workspace/scribe-next-api-validation-20261004-7SqsM3`다. Mac의 자격증명 없는 Git bundle로 검증 commit과 고정 upstream object를 전달했다. 기존 서버 프로젝트·다른 검증 폴더는 수정하지 않았다.

- 서버 Ubuntu keyring으로 resolute/resolute-updates/resolute-security의 InRelease 3개를 `gpgv` 검증하고, main/universe Packages 6개의 크기·SHA256을 서명된 값과 비교했다. 날짜와 존재하는 Valid-Until을 검사했으며 유효기간 검사를 끄지 않았다. 이 세 Release에는 Valid-Until 필드가 없었다.
- 명시적으로 `libboost1.83-dev`와 필요한 1.83 모듈을 `1.83.0-5ubuntu5`로 고정했다. 같은 resolute의 공식 31개 payload만 SHA256 확인 후 `dpkg-deb --extract`로 작업 폴더에 풀었다. Ubuntu 기본 Boost 1.90 메타 패키지나 다른 배포판 패키지는 사용하지 않았다.
- 설치된 runtime과 같은 `libssl-dev 3.5.5-1ubuntu3.5`가 일반 공식 미러에서 404여서 [공식 Ubuntu snapshot](https://snapshot.ubuntu.com/)의 `20260928T160000Z` 경로에서 동일 payload를 받았다. 기존 인증 인덱스의 SHA256과 일치했다. 시스템 패키지 설치·maintainer script·APT source 변경은 없었다.
- 첫 runtime compile은 추출된 OpenSSL의 multiarch 헤더 경로가 빠져 실패했다. `tools/usr/include/x86_64-linux-gnu`를 CPPFLAGS에 추가했다. 다음 link는 개발용 상대 `.so` 링크의 대상이 작업 폴더에 없어 정적 OpenSSL을 선택하며 실패했다. 버전 일치를 확인한 기존 시스템 `libssl.so.3`, `libcrypto.so.3`, `libevent_core-2.1.so.7.0.1`을 작업 폴더의 symlink로 참조한 뒤 clean rebuild했다. 시스템 runtime과 공식 소스는 바꾸지 않았다.
- 첫 Thrift suite는 28/29 PASS였다. 실패한 UnitTests의 141 case 중 en_US/de_DE locale 2개가 누락됐음을 별도 실행으로 재현했다. 기존 `locales`/`libc-bin 2.43-2ubuntu2.4`의 자료와 `localedef --no-archive`로 작업 폴더에 생성하고 시험 프로세스에만 LOCPATH를 설정한 재실행에서 29/29 PASS였다. 시험 삭제·skip·시스템 locale 변경은 없었다.
- SSL 시험에는 공식 archive의 변경 없는 `test/keys`를 build-side `test/keys`로 연결했다. fixture key·dependency payload·바이너리는 Git이나 handoff archive에 넣지 않는다. fuzz target compile은 포함됐지만 fuzz campaign은 실행하지 않았다.

## 재실행 근거와 범위

개인 Library handoff의 `ubuntu-evidence/`에는 실제 실행 스크립트, toolchain 환경, 서명 메타데이터, 초기 실패와 최종 성공 로그가 있다. `records/ubuntu-build-manifest.json`의 해시는 저장소 manifest에 기록했다. Thrift와 Scribe의 기본 configure recipe는 [기존 manifest](build-manifest.json)의 command_templates를 따른다. Ubuntu에서는 위 multiarch CPPFLAGS, 동일 버전 runtime 링크, Automake 1.18 경로와 시험용 LOCPATH가 추가로 필요했다. 기록 스크립트는 그 실행 경로의 증거이며 다른 환경에서 무검토로 실행하는 설치 도구가 아니다.

Thrift 29개와 프로젝트 38개는 서로 다른 시험 묶음이다. 프로젝트 시험은 실제 생성 client/processor·메모리 transport·handler·mutex·CLI의 제한된 검증이며 Scribe daemon이나 외부 client를 실행하지 않았다. Thrift의 임시 socket 시험 외에 운영 서비스·DB·볼륨·배포·시스템 보안 설정은 변경하지 않았다.

이 결과는 Ubuntu 26.04 + Boost 1.83 lane만의 근거다. Boost 1.90, HDFS, FACEBOOK 비공개 lane, shared RPC/완전 정적 의존성, 전체 root make/Python packaging/PHP suite는 미검증이다. 승인된 전체 platform matrix와 old/new wire·10 store·양방향 spool/relay·fault·성능·회사 baseline 검증은 남아 있어 Gate A–D는 완료로 표시하지 않는다. 다음 단계는 회사의 실제 old runtime/config를 확보하고 old/new differential fixture를 설계하는 것이다. 회사 자료가 없으면 공개 upstream 기준임을 계속 표시한다.
