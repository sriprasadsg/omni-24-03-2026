# Phase 66: Full YARA-rule engine for native scan - Research

**Researched:** 2026-08-14
**Domain:** Security / YARA Rule Evaluation
**Confidence:** LOW (No web verification)

## Summary

The requirement for "full YARA rule evaluation" without JIT bloat (like `wasmtime` in `yara-x`) creates a tension. `yara-x` is a Rust-native engine but is architected around WASM for modules, making it heavy. A pure Rust YARA engine without JIT does not currently exist as a mature, full-spec implementation.

**Primary recommendation:** Use `yara` crate (bindings to the original C library). It provides full YARA specification compliance and is the standard approach when full compatibility is required and pure-Rust alternatives are either incomplete or too heavy due to JIT dependencies.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| YARA Rule Evaluation | API / Backend | - | Core scanning logic |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `yara` | [ASSUMED] | Bindings to C YARA | Full spec compliance |

## Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `yara` (C-bindings) | `yara-x` | `yara-x` is pure Rust but bloated by JIT/WASM dependencies required for full module support |
| `yara` (C-bindings) | Custom Parser (subset) | Does not support "full YARA rule specification" |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `yara` | crates.io | [ASSUMED] | [ASSUMED] | [ASSUMED] | [ASSUMED] | Flagged |

*Packages tagged `[ASSUMED]` require human verification.*

## Architecture Patterns

### Recommended Project Structure
```
src/
├── scanner/
│   ├── mod.rs
│   └── yara_bindings.rs
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YARA Parser/VM | Hand-rolled parser | `yara` C-bindings | Full spec complexity is immense |

## Common Pitfalls

### Pitfall 1: Cross-compilation complexity
**What goes wrong:** Build failures when cross-compiling to Windows (`x86_64-pc-windows-gnu`).
**Why it happens:** Requires C-toolchain setup for the target architecture (`mingw-w64`).
**How to avoid:** Use a pre-configured build container or ensure `mingw-w64` is configured correctly in the Rust cross-compilation environment.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `yara-x` cannot be stripped of JIT/WASM dependencies. | Summary | High (might be possible) |
| A2 | `yara` crate provides full YARA spec support. | Standard Stack | Moderate (spec parity depends on C-lib version) |

## Open Questions

1. **Can `yara-x` be selectively compiled?** Need to verify if feature flags exist to disable WASM module support.
2. **What is the actual binary size overhead of the `yara` crate?**

## Metadata

**Research date:** 2026-08-14
