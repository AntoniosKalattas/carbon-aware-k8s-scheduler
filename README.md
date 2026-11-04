# carbon-aware-k8s-scheduler

# Current State

We use `kind` (Kubernetes in Docker) to set up locally a small cluster and `kubectl` to talk to the cluster.

## Set up `kind`:
```
brew install kind
```

verify that it worked:
```
kind version
```

## Setup kubernetes
```
brew install kubectl
```


# Current Limits
All the “nodes” share your laptop’s CPU, RAM and hardware. They aren’t physically different machines.
That means you can’t measure real per-node energy differences between them.
It’s meant for testing and development, not production.

