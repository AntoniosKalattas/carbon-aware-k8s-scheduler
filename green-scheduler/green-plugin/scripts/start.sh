#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(kubectl config current-context)" != "kind-green" ]]; then
  echo 'Select the kind-green context before starting.' >&2
  exit 1
fi
mkdir -p .runtime
chmod 700 .runtime
umask 077
# Contains local cluster credentials. Keep private and never commit.
kubectl config view --minify --flatten --raw > .runtime/kubeconfig
python3 scripts/configure.py
exec ./bin/green-scheduler --config .runtime/scheduler.json \
  --bind-address=127.0.0.1 --secure-port=10269 --cert-dir=.runtime/certs \
  --authentication-kubeconfig=.runtime/kubeconfig \
  --authorization-kubeconfig=.runtime/kubeconfig --v=4
