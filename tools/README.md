# tools

## timeline-extract.py — 구글 타임라인에서 여행 기간만 뽑기

구글 타임라인(위치기록) 내보내기는 보통 수백 MB라 그대로 주고받기 어렵습니다.
이 스크립트는 파일을 통째로 메모리에 올리지 않고 스트리밍으로 훑어서,
지정한 날짜 구간만 남긴 수십 KB짜리 파일 두 개를 만듭니다.

- `timeline-trip.json` — 프로그램이 읽기 좋은 형태
- `timeline-trip.txt` — 사람이 읽는 형태 (그대로 붙여넣기 좋음)

### 쓰는 법

파이썬 3만 있으면 됩니다. 설치할 것 없습니다.

```bash
python3 tools/timeline-extract.py <파일이나폴더> --from 2025-06-01 --to 2025-06-20
```

Takeout 폴더를 통째로 줘도 알아서 찾습니다.

```bash
python3 tools/timeline-extract.py ~/Downloads/Takeout --from 2025-06-01 --to 2025-06-20 --out prague.json
```

### 옵션

| 옵션 | 설명 |
|---|---|
| `--from`, `--to` | 뽑을 기간 (종료일 포함) |
| `--out` | 결과 파일 이름 (기본 `timeline-trip.json`) |
| `--min-minutes` | 이보다 짧게 머문 곳은 뺀다 (기본 10분) |
| `--point-every` | `Records.json`처럼 좌표만 있을 때 몇 분 간격으로 남길지 (기본 30분) |

### 지원 형식

| 형식 | 파일 | 장소 이름 |
|---|---|---|
| 요즘 휴대폰 내보내기 | `Timeline.json` (`semanticSegments`) | 없음 — 좌표와 placeId만 |
| 예전 Takeout | `2025_JUNE.json` (`timelineObjects`) | **있음** |
| 원시 위치 점 | `Records.json` (`locations`) | 없음 — 좌표만 |

장소 이름이 필요하면 예전 Takeout 형식(Semantic Location History)이 가장 좋습니다.

### 성능

149MB 파일 기준 16초, 최대 메모리 25MB. 500MB짜리도 1분 남짓입니다.

### 주의

내보낸 원본에는 **집·직장을 포함한 전체 이동 기록**이 들어 있습니다.

- 원본을 공개 저장소에 올리지 마세요. `.gitignore`로 막아뒀습니다.
- 이 스크립트의 결과물도 올리기 전에 한 번 열어보세요.
  여행지와 무관한 장소가 섞여 있으면 지우면 됩니다.
