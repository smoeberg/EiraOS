//! Event signatures (Phase 0 §3.6).
//!
//! Signed input (all lengths fixed or prefixed, so it is unambiguous):
//!
//! ```text
//! u8   len(DOMAIN)            = 15
//! [u8] DOMAIN                 = "EIRAOS-EVENT-V1"
//! u16  envelope_version (BE)  from the envelope
//! u16  schema_version   (BE)  from the envelope
//! u8   algorithm id           1 = Ed25519
//! [16] key_id
//! [..] canonical CBOR of the envelope without its `signature` field
//! ```
//!
//! The algorithm and key id are bound into the signature, so neither can be
//! swapped after signing. Versions are read from the envelope, never hardcoded.

use super::envelope::{EnvelopeError, EventEnvelope, Id128};
use ed25519_dalek::{Signer, SigningKey, VerifyingKey};
use std::fmt;

pub const DOMAIN_SEPARATOR: &[u8] = b"EIRAOS-EVENT-V1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SignatureAlgorithm {
    Ed25519,
}

impl SignatureAlgorithm {
    pub fn name(self) -> &'static str {
        match self {
            SignatureAlgorithm::Ed25519 => "ed25519",
        }
    }

    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "ed25519" => Some(SignatureAlgorithm::Ed25519),
            _ => None,
        }
    }

    fn wire_id(self) -> u8 {
        match self {
            SignatureAlgorithm::Ed25519 => 1,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Signature {
    pub algorithm: SignatureAlgorithm,
    pub key_id: Id128,
    pub bytes: [u8; 64],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SignatureError {
    Envelope(EnvelopeError),
    Missing,
    UnknownKey(Id128),
    Invalid,
}

impl fmt::Display for SignatureError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for SignatureError {}

impl From<EnvelopeError> for SignatureError {
    fn from(error: EnvelopeError) -> Self {
        SignatureError::Envelope(error)
    }
}

/// Build the exact bytes that are signed for `envelope`.
pub fn signing_input(
    envelope: &EventEnvelope,
    algorithm: SignatureAlgorithm,
    key_id: Id128,
) -> Result<Vec<u8>, EnvelopeError> {
    let body = envelope.to_unsigned_cbor()?;
    let mut input = Vec::with_capacity(1 + DOMAIN_SEPARATOR.len() + 21 + body.len());
    input.push(DOMAIN_SEPARATOR.len() as u8);
    input.extend_from_slice(DOMAIN_SEPARATOR);
    input.extend_from_slice(&envelope.envelope_version.to_be_bytes());
    input.extend_from_slice(&envelope.schema_version.to_be_bytes());
    input.push(algorithm.wire_id());
    input.extend_from_slice(&key_id.0);
    input.extend_from_slice(&body);
    Ok(input)
}

/// Sign `envelope` in place, replacing any previous signature.
pub fn sign(
    envelope: &mut EventEnvelope,
    key: &SigningKey,
    key_id: Id128,
) -> Result<(), SignatureError> {
    let input = signing_input(envelope, SignatureAlgorithm::Ed25519, key_id)?;
    envelope.signature = Some(Signature {
        algorithm: SignatureAlgorithm::Ed25519,
        key_id,
        bytes: key.sign(&input).to_bytes(),
    });
    Ok(())
}

/// Verify a signed envelope. Keys are looked up by `key_id`; an unknown key,
/// a missing signature or any mismatch fails closed.
pub fn verify(
    envelope: &EventEnvelope,
    keys: impl Fn(Id128) -> Option<VerifyingKey>,
) -> Result<(), SignatureError> {
    let sig = envelope.signature.as_ref().ok_or(SignatureError::Missing)?;
    let key = keys(sig.key_id).ok_or(SignatureError::UnknownKey(sig.key_id))?;
    let input = signing_input(envelope, sig.algorithm, sig.key_id)?;
    let signature = ed25519_dalek::Signature::from_bytes(&sig.bytes);
    key.verify_strict(&input, &signature)
        .map_err(|_| SignatureError::Invalid)
}

/// Policy hook: where signing is required, an unsigned envelope is rejected.
pub fn verify_if_required(
    envelope: &EventEnvelope,
    required: bool,
    keys: impl Fn(Id128) -> Option<VerifyingKey>,
) -> Result<(), SignatureError> {
    match (&envelope.signature, required) {
        (None, false) => Ok(()),
        _ => verify(envelope, keys),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::cbor::Value;
    use crate::ipc::envelope::tests::sample;

    const KEY_ID: Id128 = Id128([0x44; 16]);

    fn key() -> SigningKey {
        SigningKey::from_bytes(&[7u8; 32])
    }

    fn keys(id: Id128) -> Option<VerifyingKey> {
        (id == KEY_ID).then(|| key().verifying_key())
    }

    fn hex(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }

    #[test]
    fn domain_separator_is_exactly_the_contract_bytes() {
        assert_eq!(DOMAIN_SEPARATOR, b"EIRAOS-EVENT-V1");
        assert_eq!(DOMAIN_SEPARATOR.len(), 15);
        let input = signing_input(&sample(), SignatureAlgorithm::Ed25519, KEY_ID).unwrap();
        assert_eq!(&input[..16], b"\x0fEIRAOS-EVENT-V1");
        assert_eq!(&input[16..20], &[0, 1, 0, 1]);
        assert_eq!(input[20], 1);
        assert_eq!(&input[21..37], &KEY_ID.0);
    }

    #[test]
    fn golden_vector() {
        // Pinned: any change to the envelope encoding or the signed input
        // layout changes these bytes and must be a deliberate contract change.
        let mut env = sample();
        sign(&mut env, &key(), KEY_ID).unwrap();
        let sig = env.signature.as_ref().unwrap();
        assert_eq!(hex(&sig.bytes), GOLDEN_SIGNATURE);
        assert_eq!(hex(&env.to_cbor().unwrap()), GOLDEN_SIGNED_ENVELOPE);
        verify(&env, keys).unwrap();
        let decoded = EventEnvelope::from_cbor(&env.to_cbor().unwrap()).unwrap();
        verify(&decoded, keys).unwrap();
    }

    #[test]
    fn tampering_is_detected() {
        let mut env = sample();
        sign(&mut env, &key(), KEY_ID).unwrap();

        let mut payload = env.clone();
        payload.payload = Value::Map(vec![(
            Value::text("text"),
            Value::text("Kan vi mødes fredag?"),
        )]);
        assert_eq!(verify(&payload, keys), Err(SignatureError::Invalid));

        let mut schema = env.clone();
        schema.schema_version = 2;
        assert_eq!(verify(&schema, keys), Err(SignatureError::Invalid));

        let mut seq = env.clone();
        seq.sequence += 1;
        assert_eq!(verify(&seq, keys), Err(SignatureError::Invalid));

        let mut bit = env.clone();
        bit.signature.as_mut().unwrap().bytes[0] ^= 1;
        assert_eq!(verify(&bit, keys), Err(SignatureError::Invalid));
    }

    #[test]
    fn key_id_is_bound_to_the_signature() {
        let mut env = sample();
        sign(&mut env, &key(), KEY_ID).unwrap();
        // Same key registered under a second id: swapping the id must fail.
        let other = Id128([0x55; 16]);
        env.signature.as_mut().unwrap().key_id = other;
        let both = |id: Id128| (id == KEY_ID || id == other).then(|| key().verifying_key());
        assert_eq!(verify(&env, both), Err(SignatureError::Invalid));
    }

    #[test]
    fn wrong_domain_separator_is_rejected() {
        let env = sample();
        let mut input = signing_input(&env, SignatureAlgorithm::Ed25519, KEY_ID).unwrap();
        input[1..16].copy_from_slice(b"EIRAOS-EVENT-V2");
        let mut forged = env.clone();
        forged.signature = Some(Signature {
            algorithm: SignatureAlgorithm::Ed25519,
            key_id: KEY_ID,
            bytes: key().sign(&input).to_bytes(),
        });
        assert_eq!(verify(&forged, keys), Err(SignatureError::Invalid));
    }

    #[test]
    fn missing_or_unknown_keys_fail_closed() {
        let env = sample();
        assert_eq!(verify(&env, keys), Err(SignatureError::Missing));
        assert_eq!(
            verify_if_required(&env, true, keys),
            Err(SignatureError::Missing)
        );
        assert_eq!(verify_if_required(&env, false, keys), Ok(()));

        let mut signed = sample();
        sign(&mut signed, &key(), KEY_ID).unwrap();
        assert_eq!(
            verify(&signed, |_| None),
            Err(SignatureError::UnknownKey(KEY_ID))
        );
        // A present signature is always checked, even when not required.
        signed.payload = Value::Null;
        assert_eq!(
            verify_if_required(&signed, false, keys),
            Err(SignatureError::Invalid)
        );
    }

    const GOLDEN_SIGNATURE: &str = "b61c1543588e284172387ee1a46597e23c6a536943e0b55159a504d6ac47ca1d15e3d95cc86452dd269c4188a2d3c7357ba97077b8339a5d1829704fb97d8b0a";
    const GOLDEN_SIGNED_ENVELOPE: &str = concat!(
        "aa677061796c6f6164a26474657874764b616e207669206dc3b864657320746f",
        "72736461673f6f636f6e766572736174696f6e5f69646a6f626a3a7361673a34",
        "32686576656e745f696450111111111111111111111111111111116873657175",
        "656e636507697369676e6174757265a3666b65795f6964504444444444444444",
        "444444444444444469616c676f726974686d6765643235353139697369676e61",
        "747572655840b61c1543588e284172387ee1a46597e23c6a536943e0b55159a5",
        "04d6ac47ca1d15e3d95cc86452dd269c4188a2d3c7357ba97077b8339a5d1829",
        "704fb97d8b0a6a6576656e745f7479706576636f6e766572736174696f6e2e75",
        "74746572616e63656b70726f64756365725f6964502222222222222222222222",
        "22222222226c74696d657374616d705f6e731b187589da548fc0006e636f7272",
        "656c6174696f6e5f696450333333333333333333333333333333336e73636865",
        "6d615f76657273696f6e0170656e76656c6f70655f76657273696f6e01",
    );
}
