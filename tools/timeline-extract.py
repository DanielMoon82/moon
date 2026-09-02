#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구글 타임라인(위치기록) 내보내기에서 특정 기간만 뽑아 작은 요약 파일로 만든다.

원본은 보통 수백 MB라 그대로 주고받기 어렵다. 이 스크립트는 파일을 통째로
메모리에 올리지 않고 스트리밍으로 훑어서, 지정한 날짜 구간의 방문지와 이동만
남긴 수십 KB짜리 JSON 하나를 만든다.

지원하는 형식
  1) Timeline.json            — 요즘 휴대폰에서 바로 내보내는 형식 (semanticSegments)
  2) 2025_JUNE.json 등        — 예전 Takeout 의 Semantic Location History (timelineObjects)
  3) Records.json             — 원시 위치 점 (locations). 장소 이름이 없어 좌표만 나온다.
  폴더를 주면 그 아래 위 파일들을 알아서 찾는다.

사용법
  python3 tools/timeline-extract.py <파일이나폴더> --from 2025-06-01 --to 2025-06-20
  python3 tools/timeline-extract.py ~/Downloads/Takeout --from 2025-06-01 --to 2025-06-20 --out prague.json

주의: 내보낸 원본에는 집·직장을 포함한 전체 이동 기록이 들어 있다.
      공개 저장소에 원본을 올리지 말 것. 이 스크립트의 결과물도 올리기 전에 한 번 열어볼 것.
"""

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta

# ----------------------------------------------------------------- 스트리밍 파서

TOKEN = re.compile(r'["{}\[\]]')
# 문자열 안에서는 \" 를 건너뛰고 닫는 따옴표까지 한 번에 넘어간다.
STR_END = re.compile(r'(?:[^"\\]|\\.)*"')


def iter_array_elements(path, key, chunk_size=1 << 20):
    """파일에서 "key": [ ... ] 배열을 찾아 원소를 하나씩 문자열로 돌려준다.

    파일 전체를 메모리에 올리지 않으려고 직접 괄호 깊이를 센다.
    의미 있는 문자로만 정규식으로 건너뛰기 때문에, 수백 MB짜리도 일정한
    메모리로 훑는다.
    """
    with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
        needle = '"%s"' % key
        buf = ''
        while True:                                  # 1) 배열 시작 지점 찾기
            more = f.read(chunk_size)
            if not more:
                return
            buf += more
            i = buf.find(needle)
            if i != -1:
                j = buf.find('[', i + len(needle))
                if j != -1:
                    buf = buf[j + 1:]
                    break
            elif len(buf) > 4 * chunk_size:
                buf = buf[-len(needle):]

        depth = 0
        start = None
        pos = 0
        while True:                                  # 2) 원소 하나씩 잘라내기
            need_more = False
            while True:
                m = TOKEN.search(buf, pos)
                if not m:
                    need_more = True
                    break
                i = m.start()
                c = buf[i]
                if c == '"':
                    e = STR_END.match(buf, i + 1)
                    if not e:                        # 문자열이 청크 경계에 걸림
                        if start is None:
                            start = i
                        need_more = True
                        break
                    pos = e.end()
                    continue
                if c in '{[':
                    if depth == 0:
                        start = i
                    depth += 1
                else:
                    if depth == 0:                   # 배열이 닫혔다
                        return
                    depth -= 1
                    if depth == 0 and start is not None:
                        yield buf[start:i + 1]
                        start = None
                pos = i + 1
            if not need_more:
                return
            keep = start if start is not None else pos
            buf = buf[keep:]
            pos -= keep
            if start is not None:
                start = 0
            more = f.read(chunk_size)
            if not more:
                return
            buf += more


def detect_kind(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
        head = f.read(8192)
    if 'semanticSegments' in head:
        return 'timeline'
    if 'timelineObjects' in head:
        return 'semantic'
    if '"locations"' in head:
        return 'records'
    return None


# ----------------------------------------------------------------- 값 뽑기 도우미

ISO_FIX = re.compile(r'(\.\d{6})\d+')

def parse_time(v):
    """구글이 쓰는 여러 시간 표기를 datetime 으로. 현지 시각 오프셋이 있으면 살린다."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.utcfromtimestamp(float(v) / 1000.0)
    s = str(v).strip()
    if s.isdigit():                                   # timestampMs
        return datetime.utcfromtimestamp(int(s) / 1000.0)
    s = ISO_FIX.sub(r'\1', s)
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


LATLNG = re.compile(r'(-?\d+\.\d+)\s*°?\s*,\s*(-?\d+\.\d+)')

def parse_latlng(v):
    """ {"latitudeE7":..} / "geo:37.1,127.1" / "37.1°, 127.1°" / {"latLng":"..."} 전부 처리."""
    if v is None:
        return None
    if isinstance(v, dict):
        if 'latitudeE7' in v:
            return (v['latitudeE7'] / 1e7, v['longitudeE7'] / 1e7)
        for k in ('latLng', 'placeLocation', 'location'):
            if k in v:
                got = parse_latlng(v[k])
                if got:
                    return got
        return None
    m = LATLNG.search(str(v))
    return (float(m.group(1)), float(m.group(2))) if m else None


def dig(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# ----------------------------------------------------------------- 형식별 정규화

def from_timeline(obj):
    """요즘 형식(semanticSegments)의 원소 하나 -> 표준 레코드."""
    start, end = parse_time(obj.get('startTime')), parse_time(obj.get('endTime'))
    if not start:
        return None
    visit = obj.get('visit')
    if visit:
        cand = visit.get('topCandidate') or {}
        return dict(kind='visit', start=start, end=end,
                    name=None, address=None,
                    place_id=cand.get('placeId'),
                    latlng=parse_latlng(cand.get('placeLocation')),
                    semantic=cand.get('semanticType'))
    act = obj.get('activity')
    if act:
        km = act.get('distanceMeters')
        return dict(kind='move', start=start, end=end,
                    mode=dig(act, 'topCandidate', 'type'),
                    km=(float(km) / 1000.0) if km else None,
                    frm=parse_latlng(act.get('start')), to=parse_latlng(act.get('end')))
    return None


def from_semantic(obj):
    """예전 Takeout 형식(timelineObjects)의 원소 하나 -> 표준 레코드."""
    pv = obj.get('placeVisit')
    if pv:
        loc = pv.get('location') or {}
        return dict(kind='visit',
                    start=parse_time(dig(pv, 'duration', 'startTimestamp')
                                     or dig(pv, 'duration', 'startTimestampMs')),
                    end=parse_time(dig(pv, 'duration', 'endTimestamp')
                                   or dig(pv, 'duration', 'endTimestampMs')),
                    name=loc.get('name'), address=loc.get('address'),
                    place_id=loc.get('placeId'), latlng=parse_latlng(loc),
                    semantic=pv.get('placeConfidence'))
    seg = obj.get('activitySegment')
    if seg:
        m = seg.get('distance') or seg.get('distanceMeters')
        return dict(kind='move',
                    start=parse_time(dig(seg, 'duration', 'startTimestamp')
                                     or dig(seg, 'duration', 'startTimestampMs')),
                    end=parse_time(dig(seg, 'duration', 'endTimestamp')
                                   or dig(seg, 'duration', 'endTimestampMs')),
                    mode=seg.get('activityType'),
                    km=(float(m) / 1000.0) if m else None,
                    frm=parse_latlng(seg.get('startLocation')),
                    to=parse_latlng(seg.get('endLocation')))
    return None


def from_records(obj):
    t = parse_time(obj.get('timestamp') or obj.get('timestampMs'))
    ll = parse_latlng(obj)
    if not t or not ll:
        return None
    return dict(kind='point', start=t, end=t, latlng=ll)


# ----------------------------------------------------------------- 본체

def collect(paths, d_from, d_to, point_every=30):
    recs = []
    used = []
    last_point = {}          # 날짜별 마지막으로 남긴 원시 위치 점의 시각
    for p in paths:
        kind = detect_kind(p)
        if not kind:
            continue
        key = {'timeline': 'semanticSegments',
               'semantic': 'timelineObjects',
               'records': 'locations'}[kind]
        conv = {'timeline': from_timeline,
                'semantic': from_semantic,
                'records': from_records}[kind]
        n = 0
        for raw in iter_array_elements(p, key):
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            r = conv(obj)
            if not r or not r.get('start'):
                continue
            day = r['start'].date()
            if not (d_from <= day <= d_to):
                continue
            if r['kind'] == 'point':
                # 원시 위치 점은 몇 초 간격으로 쌓여 있어 그대로 두면 수십만 개가 된다.
                prev = last_point.get(day)
                if prev is not None and abs((r['start'] - prev).total_seconds()) < point_every * 60:
                    continue
                last_point[day] = r['start']
            recs.append(r)
            n += 1
        used.append((p, kind, n))
    return recs, used


def summarize(recs, d_from, d_to, min_minutes):
    days = {}
    for r in sorted(recs, key=lambda x: x['start']):
        d = r['start'].date().isoformat()
        day = days.setdefault(d, {'date': d, 'visits': [], 'moves': [], 'points': 0})
        if r['kind'] == 'point':
            day['points'] += 1
            day.setdefault('track', []).append({
                'at': r['start'].strftime('%H:%M'),
                'lat': round(r['latlng'][0], 5), 'lng': round(r['latlng'][1], 5)})
            continue
        mins = int((r['end'] - r['start']).total_seconds() // 60) if r.get('end') else None
        if r['kind'] == 'visit':
            if mins is not None and mins < min_minutes:
                continue
            day['visits'].append({
                'name': r.get('name'), 'address': r.get('address'),
                'lat': round(r['latlng'][0], 5) if r.get('latlng') else None,
                'lng': round(r['latlng'][1], 5) if r.get('latlng') else None,
                'placeId': r.get('place_id'),
                'from': r['start'].strftime('%H:%M'),
                'to': r['end'].strftime('%H:%M') if r.get('end') else None,
                'minutes': mins,
            })
        else:
            day['moves'].append({
                'mode': r.get('mode'),
                'km': round(r['km'], 1) if r.get('km') else None,
                'from': r['start'].strftime('%H:%M'),
                'to': r['end'].strftime('%H:%M') if r.get('end') else None,
            })
    return {'range': {'from': d_from.isoformat(), 'to': d_to.isoformat()},
            'days': [days[k] for k in sorted(days)]}


MODE_KO = {
    'IN_PASSENGER_VEHICLE': '차', 'IN_VEHICLE': '차', 'DRIVING': '차',
    'WALKING': '도보', 'ON_FOOT': '도보', 'RUNNING': '달리기',
    'IN_TRAIN': '기차', 'IN_SUBWAY': '지하철', 'IN_TRAM': '트램',
    'IN_BUS': '버스', 'FLYING': '비행기', 'IN_FERRY': '배',
    'CYCLING': '자전거', 'ON_BICYCLE': '자전거',
}


def render_text(summary):
    out = []
    for day in summary['days']:
        out.append('── %s' % day['date'])
        rows = []
        for v in day['visits']:
            label = v['name'] or v['address'] or (
                '%.5f, %.5f' % (v['lat'], v['lng']) if v['lat'] is not None else '(위치 미상)')
            dur = ' (%d분)' % v['minutes'] if v['minutes'] is not None else ''
            rows.append(('  %s~%s  머묾  %s%s' % (v['from'], v['to'] or '', label, dur), v['from']))
        for m in day['moves']:
            mode = MODE_KO.get(m['mode'], m['mode'] or '이동')
            km = ' %.1fkm' % m['km'] if m['km'] else ''
            rows.append(('  %s~%s  이동  %s%s' % (m['from'], m['to'] or '', mode, km), m['from']))
        for line, _ in sorted(rows, key=lambda x: x[1]):
            out.append(line)
        for t in day.get('track', []):
            out.append('  %s        좌표  %.5f, %.5f' % (t['at'], t['lat'], t['lng']))
        if not rows and not day.get('track'):
            out.append('  (기록 없음)')
        out.append('')
    return '\n'.join(out)


def gather_paths(target):
    if os.path.isfile(target):
        return [target]
    hits = []
    for root, _dirs, files in os.walk(target):
        for fn in files:
            if not fn.lower().endswith('.json'):
                continue
            if fn in ('Timeline.json', 'Records.json', 'location-history.json') \
               or re.match(r'^\d{4}_[A-Z]+\.json$', fn) \
               or 'timeline' in fn.lower() or 'location' in fn.lower():
                hits.append(os.path.join(root, fn))
    return sorted(hits)


def main():
    ap = argparse.ArgumentParser(description='구글 타임라인에서 특정 기간만 뽑아낸다.')
    ap.add_argument('target', help='Timeline.json / Records.json / 월별 json, 또는 Takeout 폴더')
    ap.add_argument('--from', dest='d_from', required=True, help='시작일 YYYY-MM-DD')
    ap.add_argument('--to', dest='d_to', required=True, help='종료일 YYYY-MM-DD (당일 포함)')
    ap.add_argument('--out', default='timeline-trip.json', help='결과 파일 (기본 timeline-trip.json)')
    ap.add_argument('--min-minutes', type=int, default=10,
                    help='이 시간보다 짧게 머문 곳은 뺀다 (기본 10분)')
    ap.add_argument('--point-every', type=int, default=30,
                    help='Records.json 처럼 원시 좌표만 있을 때 몇 분 간격으로 남길지 (기본 30분)')
    a = ap.parse_args()

    try:
        d_from = datetime.strptime(a.d_from, '%Y-%m-%d').date()
        d_to = datetime.strptime(a.d_to, '%Y-%m-%d').date()
    except ValueError:
        sys.exit('날짜는 2025-06-01 형식으로 넣어주세요.')
    if d_to < d_from:
        sys.exit('--to 가 --from 보다 앞섭니다.')

    paths = gather_paths(a.target)
    if not paths:
        sys.exit('타임라인 json 을 찾지 못했습니다: %s' % a.target)

    print('훑는 중… (%d개 파일)' % len(paths))
    recs, used = collect(paths, d_from, d_to, a.point_every)
    for p, kind, n in used:
        size = os.path.getsize(p) / (1024.0 * 1024.0)
        print('  %-58s %-8s %.1fMB → %d건' % (os.path.basename(p)[:58], kind, size, n))

    if not recs:
        print('\n그 기간에 기록이 없습니다. 날짜를 넓혀서 다시 해보세요.')
        return

    summary = summarize(recs, d_from, d_to, a.min_minutes)
    with io.open(a.out, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    text = render_text(summary)
    txt_out = os.path.splitext(a.out)[0] + '.txt'
    with io.open(txt_out, 'w', encoding='utf-8') as f:
        f.write(text)

    print('\n' + text)
    print('저장했습니다:')
    print('  %s  (%.1fKB)' % (a.out, os.path.getsize(a.out) / 1024.0))
    print('  %s  (%.1fKB)' % (txt_out, os.path.getsize(txt_out) / 1024.0))
    print('\n올리기 전에 파일을 한 번 열어보세요. 여행지와 무관한 장소가 있으면 지우면 됩니다.')


if __name__ == '__main__':
    main()
