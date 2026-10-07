# old-lane Docker 재현

`daemon_differential.py`의 old lane(공개 원본 `fcd294f` + Thrift/fb303 0.9.0)을 다시 만들고
modern lane과 함께 실행한다. 설명과 결과는 [검증 안내](../../docs/verification.md#구버전-lane-재현)에 있다.
전제: modern image `scribe-next-modern:rocky9`는 저장소 root의 [Dockerfile](../../Dockerfile)로 만든다(`docker build -t scribe-next-modern:rocky9 .`). 이 저장소의 `/usr/local/bin/scribed`와 python3를 담는다.
명령은 저장소 root에서 Linux shell로 실행하고 `$WORK`는 저장소 밖 새 디렉터리다.

```sh
# 1. old build image (Ubuntu 16.04, 원본에는 scribe-autotools.patch 한 변경만)
mkdir -p "$WORK/ctx" && cp tools/old-lane/Dockerfile.old tools/old-lane/scribe-autotools.patch "$WORK/ctx/"
git archive --prefix=scribe-fcd294f/ fcd294faffd1e88af1643a3a8c2359c41713f7c2 -o "$WORK/ctx/scribe-fcd294f.tar"
docker build -f "$WORK/ctx/Dockerfile.old" -t scribe-next-old-build:xenial "$WORK/ctx"

# 2. 두 lane runtime image (context 없음)
docker build -t scribe-next-differential:latest - < tools/old-lane/Dockerfile.runtime

# 3. 17개 case 실행 (performance 제외). 두 번째 인자는 새로 만들 출력 디렉터리
mkdir -p "$WORK/checkout" && git archive main | tar -x -C "$WORK/checkout"
sh tools/old-lane/run_differential.sh "$WORK/checkout" "$WORK/results/run-$(date -u +%Y%m%dT%H%M%SZ)"
```

case별 `exit=0`이 PASS다. 결과는 `<출력>/summary.txt`, `<case>.log`, `<case>/evidence/`에 남는다.
특정 case만 돌리려면 3번 명령 뒤에 case 이름을 붙인다.
