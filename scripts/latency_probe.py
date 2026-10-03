#!/usr/bin/env python3
"""사이트 응답 지연 실측: 직렬 vs 병렬(3)."""
import time, statistics
from concurrent.futures import ThreadPoolExecutor
from dkis.fetch import Fetcher

f = Fetcher("http://dkischool.org", encoding="euc-kr", rate_limit_s=0.0, timeout_s=30, retries=2)
urls = [f.view_url(47, b) for b in (729, 728, 727, 726, 725, 724, 723, 722, 721)]

t0 = time.time()
lat = []
for u in urls[:5]:
    t = time.time()
    f.get_text(u)
    lat.append(time.time() - t)
seq = time.time() - t0
print(f"직렬 5건: {seq:.2f}s (평균 {statistics.mean(lat):.2f}s, 최소 {min(lat):.2f}, 최대 {max(lat):.2f})")

f2 = Fetcher("http://dkischool.org", encoding="euc-kr", rate_limit_s=0.0, timeout_s=30, retries=2)
t0 = time.time()
with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(lambda u: f2.get_text(u), urls))
par = time.time() - t0
print(f"병렬3 9건: {par:.2f}s  → 처리량 {9/par:.2f} req/s")
print(f"(참고) 직렬 환산 9건 예상: {seq/5*9:.2f}s")
