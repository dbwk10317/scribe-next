# 문서 안내

사용법과 바뀐 점은 [저장소 README](../README.md), 개발 규칙은 [AGENTS.md](../AGENTS.md)에 있다.
이 폴더는 그 근거와 세부 절차만 둔다.

| 분류 | 문서 | 내용 |
| --- | --- | --- |
| 설계·정책 | [design.md](design.md) | 목표, 보존 구조, 호환 계약, 의존성, 현대화 단계 |
| 설계·정책 | [compatibility-policy.md](compatibility-policy.md) | 남긴 원본 버그, 고친 동작, 통신 크기 한도 |
| 빌드·설치·배포 | [build.md](build.md) | 의존성, 직접 빌드, 검증기 준비, fb303 patch, Rocky, RPM, Python client |
| 빌드·설치·배포 | [docker.md](docker.md) | Docker 이미지 빌드·실행·정지 |
| 빌드·설치·배포 | [hdfs.md](hdfs.md) | 선택 HDFS 빌드와 확인 범위 |
| 검증 | [verification.md](verification.md) | 검증기, 구·신 daemon 비교 case, 2026-10-07 최종 결과 |

단계별 검증 기록과 `*-manifest.json` 원시 기록은 2026-10-07 정리 전 git 이력(`9e8d775` 등)에 있다.
