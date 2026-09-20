# Native CPU Agent integration

`model_reader/` is the reviewed read-only candidate. Its POSIX backend defaults
to ENOTSUP until the integrator verifies 64-bit offsets and a trusted ordinary
file mount, then explicitly enables MR_POSIX_TRUSTED_FILES. Model SHA checking
and llama allocator integration are not implemented by this component.

No model, task-understanding service, or credential processing is enabled here.
Integration provenance: `evidence/agent-prerequisites-20260910/integration.json`.

`cloud/` contains the bounded DNS and HTTPS transport core for the later MiMo
path. It is disabled by default and has no endpoint or key. Its initial status
command performs no network operation; board enablement remains gated on DHCP
DNS registration, trusted entropy, trusted wall time and CA verification.
