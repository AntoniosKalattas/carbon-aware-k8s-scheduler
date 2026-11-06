# Validation performed

- Go 1.27.3 on Linux amd64; Kubernetes dependencies pinned to 1.37.0.
- `go mod tidy` completed.
- `go test ./...` passed: model and plugin tests passed, command package compiled.
- Startup shell script passed `bash -n`.
- Generated JSON checked: energy and carbon profiles; only Score overridden.
- No kind cluster is available in this workspace. Runtime startup, Mac compilation,
  placement and resource-feasibility integration must still be verified on the Mac.
- Executable build passed with `go build -buildvcs=false` on Linux amd64.
