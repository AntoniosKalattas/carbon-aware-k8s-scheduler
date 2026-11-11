"""Fixed-work, single-process CPU benchmark; emits one JSON result."""
import argparse
import json
import math
import os
import time


def count_primes(limit):
    count = 0
    for n in range(2, limit + 1):
        prime = True
        for divisor in range(2, math.isqrt(n) + 1):
            if n % divisor == 0:
                prime = False
                break
        count += prime
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=300000)
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--input-region', choices=('cyprus', 'greece', 'italy'))
    args = parser.parse_args()
    if args.limit < 2 or args.repeats < 1:
        parser.error('limit must be >= 2 and repeats >= 1')
    latency = {}
    if args.input_region:
        node_regions = json.loads(os.environ.get('BENCHMARK_NODE_REGIONS', '{}'))
        worker_region = node_regions.get(os.environ.get('BENCHMARK_NODE_NAME'))
        if worker_region not in ('cyprus', 'greece', 'italy'):
            parser.error('latency experiment requires a known worker region')
        requests = 20
        rtt_ms = 5 if worker_region == args.input_region else 50
        modeled_wait = requests * rtt_ms / 1000
        wait_start = time.perf_counter()
        time.sleep(modeled_wait)
        latency = dict(input_region=args.input_region, worker_region=worker_region,
                       requests=requests, rtt_ms=rtt_ms,
                       modeled_wait_seconds=modeled_wait,
                       observed_wait_seconds=time.perf_counter() - wait_start)
    wall, cpu = time.perf_counter(), time.process_time()
    checksum = sum(count_primes(args.limit) for _ in range(args.repeats))
    print(json.dumps(dict(limit=args.limit, repeats=args.repeats,
                         checksum=checksum, wall_seconds=time.perf_counter()-wall,
                         cpu_seconds=time.process_time()-cpu, **latency)), flush=True)


if __name__ == '__main__':
    main()
