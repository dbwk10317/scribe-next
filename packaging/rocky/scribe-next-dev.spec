%global debug_package %{nil}
%global private /opt/scribe-next-dev
%{!?source_revision:%{error:Pass the full source_revision commit}}
%{!?development_release:%{error:Pass a development_release such as 0.1.<shortsha>}}
%{!?thrift_source:%{error:Pass the verified Thrift 0.25.0 source directory}}

Name:           scribe-next-dev
Version:        1.5.0
Release:        %{development_release}%{?dist}
Summary:        Development build of the Scribe daemon for Rocky Linux
License:        Apache-2.0
URL:            https://github.com/dbwk10317/scribe-next
Source0:        scribe-next-%{version}.tar.gz
BuildRequires:  gcc-c++, make, autoconf, automake, libtool, libevent-devel
BuildRequires:  python3.12, python3.12-setuptools
Provides:       bundled(thrift) = 0.25.0
Provides:       bundled(fb303) = 0.25.0

%description
Development-only, non-HDFS/static-RPC Scribe daemon from %{source_revision}.
Matching Thrift runtime libraries live in a private prefix; scribed links no Boost library.
Python clients, configuration, service units and service scriptlets are excluded.
This package does not establish production deployment or upgrade compatibility.

%prep
%setup -q -n scribe-next-%{version}

%build
export PYTHON=/usr/bin/python3.12
export CXXFLAGS='-O2 -std=c++17 -D_GLIBCXX_USE_DEPRECATED=0'
# Boost headers only: the Thrift 0.25.0 and fb303 headers include them.
export CPPFLAGS='-I%{private}/deps/tools/include'
export LDFLAGS='-L%{private}/deps/thrift/lib -L%{private}/deps/fb303/lib -Wl,-rpath,%{private}/deps/thrift/lib'
export LD_LIBRARY_PATH=%{private}/deps/thrift/lib
export PATH=%{private}/deps/thrift/bin:$PATH
test "$(thrift --version)" = 'Thrift version 0.25.0'
sh ./bootstrap.sh --prefix=%{private} --with-thriftpath=%{private}/deps/thrift \
  --with-fb303path=%{private}/deps/fb303
make clean
make -j2

%install
install -D -m 0755 src/scribed %{buildroot}%{private}/bin/scribed
mkdir -p %{buildroot}%{private}/deps/thrift/lib
cp -a %{private}/deps/thrift/lib/libthrift.so* \
  %{private}/deps/thrift/lib/libthriftnb.so* %{buildroot}%{private}/deps/thrift/lib/
mkdir -p licenses/thrift licenses/fb303
cp %{thrift_source}/LICENSE %{thrift_source}/NOTICE licenses/thrift/
cp %{thrift_source}/contrib/fb303/LICENSE licenses/fb303/
cp %{thrift_source}/LICENSE licenses/fb303/Apache-2.0.txt
cp %{thrift_source}/NOTICE licenses/fb303/

%check
./src/scribed --help
export THRIFT_PREFIX=%{private}/deps/thrift FB303_PREFIX=%{private}/deps/fb303 TOOLS_PREFIX=%{private}/deps/tools
PYTHONPATH=test python3.12 -B -m unittest test_fb303_counter_safety

%files
%license LICENSE licenses
%dir %{private}
%dir %{private}/bin
%{private}/bin/scribed
%dir %{private}/deps
%dir %{private}/deps/thrift
%dir %{private}/deps/thrift/lib
%{private}/deps/thrift/lib/libthrift*.so*
