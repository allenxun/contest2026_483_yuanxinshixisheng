# Native strptime integration gate

The actual Abseil time_zone_format.cc:651 compile failure is explained by three matching target gates: frozen NuttX time.h has strptime under CONFIG_ALLOW_MIT_COMPONENTS; libc/time/CMakeLists.txt:47–51 includes lib_strptime.c only with that setting; Make.defs:37–38 has the same condition. Kconfig:59–67 defaults it off. Merely adding a declaration or a compiler -D to Abseil would not rebuild libc and is insufficient.

## Minimal candidate

config.fragment contains only CONFIG_ALLOW_MIT_COMPONENTS=y. Apply to root's NEW isolated target build configuration using its existing configuration workflow, regenerate the actual NuttX config headers, then rebuild libc and every consumer against that same configuration. Do not modify the existing running image/config or hand-edit generated config.h. Preserve full config diff and inspect any other sources enabled by this broad license option: it is not a strptime-only selector. No source patch is necessary for the existing CMake/Make time build lists. Do not separately link a second copy when libc already supplies it.

Real acceptance sequence: verify generated config and compile command; see lib_strptime.c compiled into target libc; recompile absl_time_zone/time_zone_format.cc with matching target headers; inspect target nm/map for exactly one real strptime definition and resolution of its dependencies; finish actual ELF link; only then run the attached small probe when root schedules it. A declaration, successful object/archive build, or a host libc test cannot substitute for these gates.

## Implementation and license

Frozen lib_strptime.c:4–25 carries the standard MIT permission notice, copyright Rich Felker et al. (musl), including notice-retention and warranty disclaimer. Preserve the notice in source and applicable distribution notices. The Kconfig says to check each enabled component's license against the project. This is a concrete license gate, not a reason to infer that every newly enabled component has already been reviewed; no broad legal compatibility conclusion is made here. Header/build machinery retains its own upstream notices.

The parser has no malloc, thread creation, file or device access. Basic numeric/literal directives use ctype facilities and recursive strptime calls for compound formats. Includes at32–38 require stdlib/langinfo/time/ctype/stddef/string/strings headers. With CONFIG_LIBC_LOCALE enabled, :486–599 adds nl_langinfo, strlen, strncasecmp and locale directives a/A/b/B/h/c/p/r/x/X. With CONFIG_LIBC_LOCALTIME enabled, :384–410 adds tzname, strlen/strncmp for Z. Do not enable either extra config just to expose the declaration. Verify their actual linked definitions if already enabled. The frozen input set does not contain their implementations, so full closure is a final-link gate.

Semantic limits: locale-disabled builds do not provide the locale-gated directives; numeric date parsing is not a complete calendar-validity validator. %s consumes a number with unspecified tm effect (:254–273), whereas Abseil explicitly handles its own %s internally. Unsupported formats and full CCTZ compatibility need tests. Abseil :684–695 handles common RFC3339 fields and z internally but still links the strptime fallback; that comment does not eliminate the symbol dependency.

## Tests and remaining blockers

strptime_probe.c is a real-API target probe candidate, not executed here. It checks numeric leap-day field extraction, remaining-input pointer, invalid month and nonnumeric year. Compile/link using the same target config/libc, then invoke k7_strptime_probe and require0; do not claim this proves complete date validation or locale semantics. Add CCTZ parse tests for a numeric RFC3339 timestamp and one locale fallback format under the actual chosen locale configuration; record expected unsupported cases rather than silently accepting wrong output. Check null/malformed/trailing inputs independently when broadening parser use.

Actual completed here: frozen source/config/build linkage review and SHA256 capture. Still pending: root's isolated config regeneration, full libc rebuild, dependent native rebuild, final target symbol/link validation, actual runtime probe and CCTZ semantic tests. No SDK/device/config operation was performed by this agent.

Optional upstream fallback exists: Abseil time_zone_format.cc:60–68 uses std::get_time when HAS_STRPTIME=0. That is not a fabricated implementation, but adds C++ stream/locale dependencies and remains unvalidated on this target; this delivery does not enable it or use it to hide the libc gate.
