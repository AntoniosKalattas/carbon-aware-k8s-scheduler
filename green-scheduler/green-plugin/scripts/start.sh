#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
context="${1:-kind-green}"
if (( $# > 0 )); then
  shift
fi
if [[ "$context" != "kind-green" && "$context" != "kind-green-six" ]]; then
  echo 'Use kind-green or kind-green-six.' >&2
  exit 1
fi
if [[ "$(kubectl config current-context)" != "$context" ]]; then
  echo "Select the $context context before starting." >&2
  exit 1
fi
mkdir -p .runtime
chmod 700 .runtime
umask 077
# Contains local cluster credentials. Keep private and never commit.
kubectl config view --minify --flatten --raw > .runtime/kubeconfig
python3 scripts/configure.py "$@"
exec ./bin/green-scheduler --config .runtime/scheduler.json \
  --bind-address=127.0.0.1 --secure-port=10269 --cert-dir=.runtime/certs \
  --authentication-kubeconfig=.runtime/kubeconfig \
  --authorization-kubeconfig=.runtime/kubeconfig --v=4
