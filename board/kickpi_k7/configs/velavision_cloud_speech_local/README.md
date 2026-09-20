# Cloud speech compile-only profile

This profile is copied from `velavision_cloud_probe_local` and additionally
enables the reviewed MiMo v2.5 protocol and cloud speech orchestration sources.
It exists to verify the complete `k7cloud` CLI and link closure in an isolated
build directory. It does not store a token, CA bundle or endpoint, does not
auto-start networking, and is not a board-flashing profile.

Expected offline commands after a later RAM-only load are:

```text
k7cloud status
k7cloud mimo-profile token-plan-cn.xiaomimimo.com
k7cloud speech-status
```

Those commands only validate linked code and configuration. Live requests stay
blocked until Wi-Fi/IPv4, DNS, approved entropy, trusted time, CA, TCP and API
readiness all pass in the owning cloud task.
