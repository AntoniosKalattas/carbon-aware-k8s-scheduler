"""Fixed-work, single-process CPU benchmark; emits one JSON result."""
import argparse
import json
import math
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
    args = parser.parse_args()
    if args.limit < 2 or args.repeats < 1:
        parser.error('limit must be >= 2 and repeats >= 1')
    wall, cpu = time.perf_counter(), time.process_time()
    checksum = sum(count_primes(args.limit) for _ in range(args.repeats))
    print(json.dumps(dict(limit=args.limit, repeats=args.repeats,
                         checksum=checksum, wall_seconds=time.perf_counter()-wall,
                         cpu_seconds=time.process_time()-cpu)), flush=True)


if __name__ == '__main__':
    main()
