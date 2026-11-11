//! Phase 0 — IPC & Event Bus contract.
//!
//! Normative text: `docs/specs/PHASE-0-IPC-EVENT-BUS.md`. The tests in these
//! modules are the executable form of that contract; a change that breaks a
//! test is a contract change and needs a spec amendment.
//!
//! | Area                         | Module         |
//! |------------------------------|----------------|
//! | Deterministic CBOR           | [`cbor`]       |
//! | Event envelope               | [`envelope`]   |
//! | Stream framing               | [`frame`]      |
//! | Sequence + explicit commit   | [`sequence`]   |
//! | Scoped file access (openat2) | [`path`]       |
//! | systemd FD ownership         | [`activation`] |
//! | Ed25519 signatures           | [`signature`]  |
//! | Subscriber queues / drops    | [`queue`]      |

pub mod activation;
pub mod cbor;
pub mod envelope;
pub mod frame;
pub mod path;
pub mod queue;
pub mod sequence;
pub mod signature;
