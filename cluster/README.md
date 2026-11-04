# Start the cluster

```
kind create cluster --config kind-config.yaml
```

# Verify

```
kubectl get nodes --show-labels
```

# Quick Sanity Test

```
kubectl apply -f ../workloads/test-job.yaml
kubectl wait --for=condition=complete job/hello --timeout=90s
kubectl get pods -o wide
kubectl logs job/hello
kubectl delete job hello

```

you should see `hi from hello-xxxxx (the pod name)`.
