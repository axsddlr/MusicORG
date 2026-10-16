# Plugin Security Model

Phase-1 plugin hosting is in-process. Plugins are treated as untrusted and guarded by policy checks.

Current protections:
- strict manifest validation and key whitelist
- plugin ID format restrictions
- capability declarations required for hook usage
- startup failures are isolated per plugin
- crash counting with auto-disable for repeatedly failing third-party plugins
- safe mode option to skip third-party plugins
- symlinked plugin directories/modules are rejected

Limitations (phase-1):
- plugins still run as Python code in the app process
- no OS-level sandboxing

Planned hardening:
- optional out-of-process host
- richer permission prompts
- tighter I/O/network mediation
