# scribed 이미지. build context는 로컬 checkout이다(git clone을 하지 않는다).
#   docker build -t scribe-next:local .
# 사용법과 한계는 docs/docker.md를 본다.

# ---- 빌드 단계: Thrift 0.25.0, matching fb303, scribed ----
FROM rockylinux:9 AS build
RUN dnf -y install git gcc gcc-c++ make cmake autoconf automake libtool bison flex libevent-devel boost-devel python3 python3-setuptools && \
    echo /usr/local/lib > /etc/ld.so.conf.d/scribe-local.conf
WORKDIR /build

# Thrift compiler/runtime 0.25.0: 공식 archive SHA256을 검사한 뒤 shared로 빌드한다.
# source를 COPY하기 전에 두어 source만 바뀌면 이 layer를 재사용한다.
RUN curl -LO https://archive.apache.org/dist/thrift/0.25.0/thrift-0.25.0.tar.gz && \
    echo '66da4707214c54c94bac082103dc67adaf9e08925662700f269170a7b534b214  thrift-0.25.0.tar.gz' | sha256sum -c - && \
    tar xzf thrift-0.25.0.tar.gz && \
    cmake -S thrift-0.25.0 -B thrift-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INSTALL_LIBDIR=lib \
      -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=ON -DWITH_CPP=ON -DWITH_C_GLIB=OFF -DWITH_JAVA=OFF -DWITH_JAVASCRIPT=OFF \
      -DWITH_NODEJS=OFF -DWITH_PYTHON=OFF -DWITH_OPENSSL=OFF -DWITH_LIBEVENT=ON -DWITH_ZLIB=OFF && \
    cmake --build thrift-build --parallel "$(nproc)" && cmake --install thrift-build && ldconfig

COPY . /build/scribe-next
# Windows checkout(core.autocrlf)의 CRLF는 autotools·shell·git apply·설정 parser를 깨뜨리므로 LF로 맞춘다.
RUN find scribe-next \( -name '*.sh' -o -name '*.ac' -o -name '*.am' -o -name '*.m4' -o -name '*.mk' -o -name '*.py' -o -name '*.patch' -o -name '*.thrift' -o -name '*.conf' \) -exec sed -i 's/\r$//' {} +

# fb303: 고정 0.25.0 source 사본에 counter-lock patch를 적용해 빌드한다.
RUN python3 scribe-next/tools/prepare_fb303.py --source thrift-0.25.0/contrib/fb303 --output fb303-build && \
    cd fb303-build && aclocal -I ./aclocal && automake -a --copy && autoconf && \
    ./configure --prefix=/usr/local --with-thriftpath=/usr/local --with-boost=/usr --without-java --without-php --without-python && \
    make -j"$(nproc)" CXXFLAGS='-O2 -std=c++17' CPPFLAGS='-I/usr/local/include' && make install && \
    mkdir -p /usr/local/share/scribe-next && cp scribe-next-fb303-safety.json /usr/local/share/scribe-next/fb303-safety.json

# scribed: 기존 autotools 경로 그대로(env_default, 비-HDFS, static RPC library).
RUN cd scribe-next && \
    ./bootstrap.sh --prefix=/usr/local --with-thriftpath=/usr/local --with-fb303path=/usr/local --with-boost=/usr \
      --with-boost-system=boost_system --with-boost-filesystem=boost_filesystem && \
    make -j"$(nproc)" && make install

# 실행 이미지에 넣을 LICENSE/NOTICE(scribe-next, Thrift runtime, scribed에 static link된 fb303).
RUN mkdir -p licenses/thrift licenses/fb303 && \
    cp scribe-next/LICENSE licenses/ && \
    cp thrift-0.25.0/LICENSE thrift-0.25.0/NOTICE licenses/thrift/ && \
    cp thrift-0.25.0/contrib/fb303/LICENSE licenses/fb303/ && chmod 0644 licenses/LICENSE licenses/*/*

# ---- 실행 단계: scribed와 Thrift runtime만 둔다 ----
FROM rockylinux:9
RUN dnf -y install libevent boost-filesystem boost-system && dnf clean all

COPY --from=build /usr/local/bin/scribed /usr/local/bin/scribed
COPY --from=build /usr/local/lib/libthrift.so.0.25.0 /usr/local/lib/libthriftnb.so.0.25.0 /usr/local/lib/
COPY --from=build /build/licenses/ /usr/share/licenses/scribe-next/
RUN echo /usr/local/lib > /etc/ld.so.conf.d/scribe-local.conf && ldconfig

# 비root 실행 사용자와 설정·로그 경로. 로그 경로 소유권은 VOLUME 선언 전에 정한다.
RUN useradd --system --no-create-home --shell /sbin/nologin scribe && \
    mkdir -p /etc/scribe /var/log/scribed && chown scribe:scribe /var/log/scribed
# CRLF를 정리한 build 단계 사본을 복사한다(Windows context의 0777 mode도 정리).
COPY --from=build --chmod=0644 /build/scribe-next/examples/docker.conf /etc/scribe/scribe.conf

USER scribe
EXPOSE 1463
VOLUME ["/var/log/scribed"]
ENTRYPOINT ["/usr/local/bin/scribed"]
CMD ["-c", "/etc/scribe/scribe.conf"]
