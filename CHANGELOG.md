# Changelog

## 0.1.0 - 2026-03-31

### Breaking Changes

- Renamed Scala package namespace from `isa.repl` to
  `io.github.luanxiaokun.isabellerepl`.
- Renamed protobuf package from `isa` to
  `io.github.luanxiaokun.isabellerepl.v1`.
- Renamed gRPC service from `IsabelleREPL` to `IsabelleReplService`.
- Renamed Scala server/service symbols:
  - file `IsaReplServer.scala` -> `IsabelleReplServer.scala`
  - class `IsaReplService` -> `IsabelleReplServiceImpl`
  - object `IsaReplServer` -> `IsabelleReplServer`
- Renamed Python client class from `IsaReplClient` to `IsabelleReplClient`
  (no compatibility alias retained).
