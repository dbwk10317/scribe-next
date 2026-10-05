# 전체 autotools build와 Python 패키징 경계

2026-10-05 · 기준 main `97d082504bcb5e3ef4b2b64059f7f01116a75c0b`

## 후속 Ubuntu 확인과 시험 layout 수정

v23의 실제 Ubuntu26.04.1/Python3.14.4/setuptools78.1.1에서는 root configure,
clean/make, DESTDIR install와 staged help가 성공했다. 그러나 실제 설치 경로는
`usr/local/lib/python3.14/dist-packages/scribe`였고 v22 시험이 site-packages만
찾아 focused는0개 실행/setup error1, 전체는147개 통과/setup error1/skip0이었다.
이 결과는150개 통과가 아니다. 별도 path-independent 생성 bytes/import/wire
관찰은 성공했지만 실패한 suite를 대체하는 통과 결과로 세지 않는다.

후속 수정은 test/test_python_packaging.py만 바꾼다. configure가 선택한
PYTHON/PY_PREFIX와 install 추가 인자로 같은 setuptools install command를
finalize하여 install_lib를 조회하고, 그 정확한 DESTDIR 내부 package만 검증한다.
missing/duplicate/unexpected/outside/symlink 경로는 실패하며 임의 glob fallback은
없다. install-only hook도 같은 검사를 쓰고 wire smoke는 선택된 interpreter로
실행한다. site/dist synthetic 경계는 기존3개 시험 안의 subcase이며 unique
시험 수를 늘리지 않는다. production packaging/C++/IDL 수정은 추가하지 않았다.
실제 설치 전 finalized 경로 containment를 검사해 추가 --root가 DESTDIR를
벗어나면 설치 없이 실패시킨다. 개별 Python 파일을 포함한 symlink도 거부한다.
독립 검토가 두 경계를 따로 확인했다. 수정본 cloud focused3/1.139초와
전체150/34.174초는 fail0/error0/skip0으로 통과했다.
수정본은 새 Ubuntu26.04.1/GCC15.2/Python3.14.4/setuptools78.1.1에서도
root configure·clean·make, 작업 폴더 DESTDIR 설치와 staged scribed help를
통과했다. **focused3/0.654초, 전체150/24.024초**가 fail0/error0/skip0이다.
기존 Thrift/fb3030.25·Boost1.83 rootless prefix를 사용했고 실제 dist-packages
scheme을 유지했다. 누락 출력·미래 timestamp의 legacy cache 복구, 생성 bytes,
설치 경로 경계와 wire smoke가 모두 실행됐다. 같은165개 소스와 기존6295개
자료를 보존했고 새 설치·보안·서비스·전원 변경은 하지 않았다.

실제 command/log·설치 경로와 bytes/hash/mode는 Library v25의
`ubuntu-scheme-evidence`에42개 raw 기록으로 보존했다. evidence archive는
645,714 bytes, SHA256 `f689956dd782f78f616e85021cecdd4d97918015f96fcf53b6cae8c1bca378b3`다.
입력 v24의2797개 manifest 기록·source165개·bundle9 refs와 원본 복원을 검증했다.
이전 v23의147개 통과/setup error1 기록도 그대로 보존하며 이번150개 통과와
구분한다. 게시 준비에서는 이 문서만 갱신했으며 검증한 빌드·시험 파일은 같다.

## 재현과 최소 수정

기준 root `make -j2`와 작업 폴더 안의 `DESTDIR` 설치는 exit0이었다.
그러나 설치는 현재 `src/gen-py/scribe` 대신 오래된 `lib/py/scribe`를
패키징했다. Python3의 `scribe.scribe` import가 `ModuleNotFoundError: ttypes`로
실패했고, 설치 bytes와 실제 Thrift0.25 생성 결과도 달랐다. 수정 전 새 시험
2개가 각각 이 두 문제로 실패했다.

`setup.py`는 이미 있는 setuptools를 명시적으로 사용하고 package_dir만 현재
IDL 생성 결과로 연결한다. package 이름 `scribe`와 version `2.0`은 유지한다.
기존 Python build/install hook은 짧은 phony `pythonstyle`로 package 전체를
생성한 뒤 `build --force`를 사용한다. 누락한 sibling 출력과 더 최신인 구
build cache를 복구한다. compiler는 동일 내용의 출력 timestamp를 유지하므로
phony 생성만으로 stale cache를 막을 수 없다. C++ target에 강제 재생성을
걸지 않고 기존 compiler/include/IDL을 그대로 사용한다.

기존 committed Python 생성 파일은 수정하지 않았다. C++ source/header 22개와
두 IDL은 기준 main bytes와 동일하다. store/spool/queue/ACK와 chunk/empty
동작은 이번 범위가 아니다. bucketupdater package 설치를 추가하지 않고
기존 PY_PREFIX 기본 `/usr`, C++ prefix와 DESTDIR를 유지한다.

## 실제 검증

Debian13·GCC14.2·C++17, 기존 Boost1.83·Thrift/fb3030.25 prefix,
Python3.12.14·setuptools84.0.0으로 새 격리 소스의 bootstrap/configure,
root clean, root `make -j2`, staged install과 설치된 `scribed --help`를 통과했다.
최종 전체150개 시험은36.297초에 fail0/error0/skip0으로 통과했다.
C++ prefix `/opt/scribe`와 Python prefix `/usr` 모두 실제 대상은 작업 폴더의
DESTDIR 아래다. 시스템 설치·새 dependency 설치·daemon 기동은 하지 않았다.

새 focused3개는 설치된 네 Python 파일의 actual compiler/IDL 생성 bytes,
name/version과 bucketupdater 미설치, fb303 import/상속, non-strict binary
Log 요청/result golden 및 UTF-8/NUL/LF roundtrip을 확인한다. 직접 install
hook도 누락한 출력과 미래 timestamp의 legacy cache를 복구한다.
독립 검토의 별도 configured 사본에서도 newer legacy cache, 삭제한 scribe.py,
오염한 ttypes.py를 넣은 focused3개/skip0을 통과했다.

raw commands/logs와 설치 파일 path/mode/size/SHA256 manifest는 checkpoint의
build-evidence에 보존한다. 시험의 Thrift Python runtime과 fb303 Python module은
matching source tree/IDL로 임시 준비했으며 시스템에 설치하거나 번들하지 않았다.

## 미검증 범위

검증된 경계는 기존 in-source autotools build/install이다. standalone Python
sdist/wheel, VPATH, system Python3.13(현재 setuptools 없음)과
그 밖의 Python/dependency matrix는 미검증이다. setuptools는 caller가 제공해야
하며 자동 설치하지 않는다. 기존 make check의 PHP suite 미연결도 유지한다.

Python3 Thrift string은 UTF-8이므로 표본을 arbitrary non-UTF8 bytes 동등성으로
확대하지 않는다. socket/framed transport, old/new Python runtime, 회사 client,
전체 fb303 method와 성능은 별도 gate다. 이전 C++ ASan/UBSan 결과를 이번
packaging 수정의 새 sanitizer 실행으로 설명하지 않는다. Gate A–D는 모두 열린 상태다.
