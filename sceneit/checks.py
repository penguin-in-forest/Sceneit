"""프리셋 규칙 검사. 컷 목록과 자막 JSON만 보고 판단하는 순수 함수라 따로 테스트할 수 있다.

장면 전환은 2026-11 로블록스 릴스 조사와 같은 방식으로 센다: 이어지지 않는 컷 경계 + 컷 안에서 원본 화면이 크게 바뀌는 시각.
"""
import re

EDGE = 0.3  # 컷 경계에 붙은 원본 장면 전환은 컷 경계와 같은 것으로 본다


def parse_length(text):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(text or ""))]
    if not nums:
        return None
    return (nums[0], nums[-1]) if len(nums) > 1 else (nums[0] * 0.8, nums[0] * 1.2)


def contiguous(a, b):
    return int(a["src"]) == int(b["src"]) and abs(float(b["t0"]) - float(a["t1"])) < 0.15


def transitions(cuts, scenes):
    """완성본 타임라인의 장면 전환 시각 목록과 총 길이."""
    t, out, prev = 0.0, [], None
    for c in cuts:
        t0, t1 = float(c["t0"]), float(c["t1"])
        if prev is not None and not contiguous(prev, c):
            out.append(t)
        for s in scenes.get(int(c["src"]), ()):
            if t0 + EDGE < s < t1 - EDGE:
                out.append(t + s - t0)
        t += t1 - t0
        prev = c
    return sorted(round(x, 2) for x in out), round(t, 2)


def rhythm(trans, total):
    pts = [0.0] + list(trans) + [total]
    longest = max(zip(pts, pts[1:]), key=lambda g: g[1] - g[0])
    busiest = (0, 0.0)
    for i, x in enumerate(trans):
        n = sum(1 for y in trans[i:] if y < x + 10)
        if n > busiest[0]:
            busiest = (n, x)
    return {
        "transitions": len(trans),
        "per10s": round(len(trans) / total * 10, 2) if total else 0.0,
        "longest": [round(longest[0], 1), round(longest[1], 1)],
        "busiest": [busiest[0], round(busiest[1], 1)],
    }


def check_cuts(cuts, scenes, length, rules):
    trans, total = transitions(cuts, scenes)
    m = {"total": total, **rhythm(trans, total)}
    problems = []
    rng = parse_length(length)
    if rules.get("length") and rng:
        lo, hi = rng
        tol = max(2.0, 0.1 * hi)
        if total < lo - tol or total > hi + tol:
            problems.append(f"완성본 길이가 {total:.1f}초예요. 컷을 조정해서 {lo:g}~{hi:g}초에 맞추세요.")
    r = rules.get("rhythm")
    if r:
        if m["transitions"] < r.get("min_transitions", 1):
            problems.append("장면이 한 번도 바뀌지 않아요(원테이크). 하이라이트 구간을 나눠 골라 10~20초마다 한 번 장면이 바뀌게 하세요.")
        a, b = m["longest"]
        if b - a > r.get("max_gap", 20):
            problems.append(
                f"완성본 {a:.1f}~{b:.1f}초가 {b - a:.1f}초 동안 장면 변화 없이 이어져요. "
                f"{r.get('max_gap', 20):g}초를 넘지 않게 중간을 덜어내거나 다른 장면을 끼우세요."
            )
        n, x = m["busiest"]
        if n > r.get("max_in_10s", 3):
            problems.append(f"완성본 {x:.1f}~{x + 10:.1f}초 사이에 장면이 {n}번 바뀌어요. 10초에 {r.get('max_in_10s', 3)}번 이하로 줄이세요.")
    return problems, m


def roles(subs, duration):
    """자막마다 title / body / reaction / label. role이 없으면 위치·길이·크기로 짐작한다."""
    out = []
    for s in subs:
        r = s.get("role")
        if r in ("title", "body", "reaction", "label"):
            out.append(r)
            continue
        t0, t1 = float(s["t0"]), float(s["t1"])
        if t0 <= 0.5 and t1 - t0 >= 0.8 * duration:
            out.append("title")
        else:
            out.append("body" if float(s.get("size", 1)) >= 0.85 else "reaction")
    return out


def union(intervals):
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def body_spans(subs, duration):
    rs = roles(subs, duration)
    return union(
        (max(0.0, float(s["t0"])), min(duration, float(s["t1"])))
        for s, r in zip(subs, rs)
        if r == "body" and float(s["t1"]) > float(s["t0"])
    )


def uncovered(spans, duration):
    holes, t = [], 0.0
    for a, b in spans:
        if a > t:
            holes.append((t, a))
        t = max(t, b)
    if duration > t:
        holes.append((t, duration))
    return holes


def close_gaps(subs, duration, limit):
    """본문 자막 사이 빈틈이 limit초 이하면 앞 자막을 다음 자막까지 늘린다. 끝에 남은 짧은 빈틈도 채운다. 바꾼 개수를 돌려준다."""
    rs = roles(subs, duration)
    body = sorted((s for s, r in zip(subs, rs) if r == "body"), key=lambda s: float(s["t0"]))
    changed = 0
    for cur, nxt in zip(body, body[1:]):
        gap = float(nxt["t0"]) - float(cur["t1"])
        if 0 < gap <= limit:
            cur["t1"] = round(float(nxt["t0"]), 2)
            changed += 1
    if body:
        rest = duration - float(body[-1]["t1"])
        if 0 < rest <= limit:
            body[-1]["t1"] = round(duration, 2)
            changed += 1
    return changed


def check_subs(data, duration, rules):
    subs = data.get("subs") or []
    rs = roles(subs, duration)
    problems, m = [], {}
    if rules.get("title_check"):
        if "title" not in rs:
            problems.append("상단 고정 제목이 없어요. 첫 자막을 0초부터 끝까지 떠 있는 제목(role \"title\")으로 만드세요.")
        tc = data.get("title_check") or {}
        if not all(str(tc.get(k, "")).strip() for k in ("대상", "상황", "이유")):
            problems.append("title_check의 대상·상황·이유를 모두 채우세요. 하나라도 채울 수 없으면 제목을 다시 쓰세요.")
    r = rules.get("subs")
    if r and not data.get("showcase") and duration > 0:
        spans = body_spans(subs, duration)
        cov = sum(b - a for a, b in spans) / duration
        holes = [(a, b) for a, b in uncovered(spans, duration) if b - a > r.get("max_gap", 3.0)]
        m.update(coverage=round(cov, 3), holes=[[round(a, 1), round(b, 1)] for a, b in holes])
        if cov < r.get("min_coverage", 0.75):
            problems.append(
                f"본문 자막(제목 제외)이 영상의 {cov:.0%}에만 떠 있어요. {r.get('min_coverage', 0.75):.0%} 이상이 되게 자막을 늘리거나 추가하세요."
            )
        if holes:
            problems.append(
                f"본문 자막이 없는 구간이 {r.get('max_gap', 3.0):g}초를 넘어요: "
                + ", ".join(f"{a:.1f}~{b:.1f}초" for a, b in holes)
                + ". 이 구간에 자막을 넣으세요."
            )
    return problems, m
