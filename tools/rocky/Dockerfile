ARG BASE=rockylinux/rockylinux@sha256:e8a49c5403b687db05d4d67333fa45808fbe74f36e683cec7abb1f7d0f2338c6
FROM ${BASE}
LABEL purpose="scribe-next-rocky-validation"
RUN dnf -y install gcc gcc-c++ make cmake autoconf automake libtool bison flex \
    libevent-devel zlib-devel libcurl-devel openssl-devel expat-devel gettext \
    perl-ExtUtils-MakeMaker python3.12 python3.12-setuptools python3.12-pip \
    tar bzip2 xz git binutils rpm-build && dnf clean all
COPY thrift-0.25.0.tar.gz boost_1_83_0.tar.bz2 git-2.53.0.tar.xz /sources/
RUN cd /sources && \
    echo '66da4707214c54c94bac082103dc67adaf9e08925662700f269170a7b534b214  thrift-0.25.0.tar.gz' | sha256sum -c - && \
    echo '6478edfe2f3305127cffe8caf73ea0176c53769f4bf1585be237eb30798c3b8e  boost_1_83_0.tar.bz2' | sha256sum -c - && \
    echo '5818bd7d80b061bbbdfec8a433d609dc8818a05991f731ffc4a561e2ca18c653  git-2.53.0.tar.xz' | sha256sum -c - && \
    tar -xjf boost_1_83_0.tar.bz2 && cd boost_1_83_0 && \
    ./bootstrap.sh --prefix=/opt/tools --with-libraries=filesystem,system && \
    ./b2 -j4 variant=release link=shared threading=multi cxxflags=-std=c++17 install
ARG BUILD_BISON=1
COPY bison-3.8.2.tar.xz /sources/
RUN if [ "$BUILD_BISON" = 1 ]; then cd /sources && \
    echo '9bba0214ccf7f1079c5d59210045227bcf619519840ebfa80cd3849cff5a5bf2  bison-3.8.2.tar.xz' | sha256sum -c - && \
    tar -xJf bison-3.8.2.tar.xz && cd bison-3.8.2 && \
    ./configure --prefix=/opt/bison-3.8.2 && make -j4 && make install; fi
ENV PATH="/opt/bison-3.8.2/bin:${PATH}"
RUN cd /sources && tar -xzf thrift-0.25.0.tar.gz && \
    cmake -S thrift-0.25.0 -B thrift-build -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/thrift-0.25.0 -DCMAKE_PREFIX_PATH=/opt/tools \
      -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=ON -DWITH_CPP=ON -DWITH_C_GLIB=OFF \
      -DWITH_JAVA=OFF -DWITH_JAVASCRIPT=OFF -DWITH_NODEJS=OFF -DWITH_PYTHON=OFF \
      -DWITH_OPENSSL=OFF -DWITH_LIBEVENT=ON -DWITH_ZLIB=OFF && \
    cmake --build thrift-build --parallel 4 && cmake --install thrift-build
RUN cd /sources/thrift-0.25.0/contrib/fb303 && \
    aclocal -I ./aclocal && automake -a && autoconf && \
    ./configure --prefix=/opt/fb303-0.25.0 --with-thriftpath=/opt/thrift-0.25.0 \
      --with-boost=/opt/tools --without-java --without-php --without-python && \
    make clean && make -j4 CXXFLAGS='-O2 -std=c++17' \
      CPPFLAGS='-I/opt/thrift-0.25.0/include -I/opt/tools/include' && make install
RUN cd /sources && tar -xJf git-2.53.0.tar.xz && cd git-2.53.0 && \
    make -j4 prefix=/opt/git-2.53.0 NO_TCLTK=YesPlease all && \
    make prefix=/opt/git-2.53.0 NO_TCLTK=YesPlease install && \
    /opt/git-2.53.0/bin/git --no-lazy-fetch --no-replace-objects --version
ENV PATH="/opt/git-2.53.0/bin:${PATH}" \
    THRIFT_PREFIX=/opt/thrift-0.25.0 FB303_PREFIX=/opt/fb303-0.25.0 \
    TOOLS_PREFIX=/opt/tools THRIFT_PYTHON_SOURCE=/sources/thrift-0.25.0/lib/py/src \
    LD_LIBRARY_PATH=/opt/tools/lib:/opt/thrift-0.25.0/lib:/opt/fb303-0.25.0/lib \
    LDFLAGS="-L/opt/tools/lib -L/opt/thrift-0.25.0/lib -L/opt/fb303-0.25.0/lib -Wl,-rpath,/opt/tools/lib -Wl,-rpath,/opt/thrift-0.25.0/lib -Wl,-rpath,/opt/fb303-0.25.0/lib" \
    PYTHON=/usr/bin/python3.12 PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /validation-input /validation-output && chmod 0777 /validation-output && \
    rpm -qa | sort > /sources/package-versions.txt && \
    /usr/bin/python3.12 --version && gcc --version && cmake --version
WORKDIR /validation-input
