# fb303 0.25.0 counter 잠금의 예외 안전성

고정 Apache Thrift 0.25.0 `contrib/fb303/cpp/FacebookBase.cpp`의 SHA256은
`ac791badf8210c68694153fb507202b0ea4ef7baf0d5303b4d91f12ceabddcae`다.
`incrementCounter`와 `setCounter`는 `counters_.lock()` 뒤 새 map node 할당이
실패하면 unlock을 건너뛴다. `getCounters`도 반환 map 할당에 같은 문제가 있다.
실제 Log write 예외의 symbolized stack은 fb303 map insertion이었다. handler lock은
이미 해제돼 reinitialize까지 완료했지만 이후 counter 접근이 멈췄다.

2026-10-06 확인한 [공식 0.25.0](https://raw.githubusercontent.com/apache/thrift/v0.25.0/contrib/fb303/cpp/FacebookBase.cpp)과
[공식 master](https://raw.githubusercontent.com/apache/thrift/50bbda109593a0b5c7634ac21c5d98eee97fe7ec/contrib/fb303/cpp/FacebookBase.cpp)는
(master commit `50bbda109593a0b5c7634ac21c5d98eee97fe7ec`)는 cpp hash가 고정 release와 동일하며 해당 함수의 수동 counter 잠금을 유지한다. 이 소스 확인을 모든 공개 issue/PR의 부재 주장으로
확대하지 않는다. dependency 버전 변경 대신 [프로젝트 patch](../dependencies/fb303-0.25.0-counter-lock.patch)를 사용한다.

## 수정과 재현

네 counter 함수의 map/value 잠금은 기존 Thrift `Guard`가 소유한다. map → value 획득과
value → map 해제 순서, 삽입/조회/증가/반환과 오류 전까지의 partial snapshot을 유지한다.
값 연산·정상 counter 결과·헤더·IDL·ABI·dependency version은 바꾸지 않는다.
`getCounter`도 같은 잠금 쌍의 RAII 형태로 맞췄다.

준비된 실제 fb303 archive에 대한 [회귀](../test/test_fb303_counter_safety.py)는 새 increment,
새 set, snapshot의 실제 할당 실패를 각각 주입한다. 이전 archive는 세 경우 모두 후속
counter read가 2초 안에 완료하지 못해 실패했다. 일반 absent/signed/default amount/반환값,
snapshot과 4 caller의 2,000회 증가도 확인한다. daemon/socket을 사용하는 시험은 아니다.

## 별도 build source 준비

공식 archive·원본 release tree·system package를 수정하지 않는다. 입력 cpp/header의 고정
hash를 먼저 확인하고 [helper](../tools/prepare_fb303.py)로 새 copy에만 patch를 적용한다.
아래 prefix와 output은 프로젝트 소유 공간에서 서로 다른 새 경로여야 한다.

```sh
python3 -B tools/prepare_fb303.py --source "$THRIFT_SOURCE/contrib/fb303" --output "$FB303_BUILD"
cd "$FB303_BUILD"
aclocal -I ./aclocal && automake -a --copy && autoconf
./configure --prefix="$FB303_PREFIX" --with-thriftpath="$THRIFT_PREFIX" \
  --with-boost="$TOOLS_PREFIX" --without-java --without-php --without-python
make clean
make -j2 CXXFLAGS='-O2 -std=c++17' \
  CPPFLAGS="-I$THRIFT_PREFIX/include -I$TOOLS_PREFIX/include"
make install
mkdir -p "$FB303_PREFIX/share/scribe-next"
cp scribe-next-fb303-safety.json "$FB303_PREFIX/share/scribe-next/fb303-safety.json"
```

manifest는 canonical cpp/header, patch, patched cpp hash를 기록한다. Linux validator는
선택된 fb303 archive와 manifest hash를 기록하고 실제 archive의 예외 복구 회귀를 실행한다.
Rocky clean recipe와 RPM dependency recipe도 별도 copy를 빌드한다. 이미 검증한 프로젝트
image를 재사용할 때 [incremental dependency Dockerfile](../tools/rocky/Dockerfile.fb303-safety)로
새 image layer에서만 matching private fb303 prefix를 재생성한다. 기존 이미지와 컨테이너는 그대로 보존한다.
빌드 context에 `prepare_fb303.py`와 `fb303-0.25.0-counter-lock.patch`를 추가한다.
