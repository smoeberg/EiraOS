//! The consent proof and the rendering hash, byte for byte as the gate
//! computes them (app/gate/consent_proof.py, app/gate/render.py). Shared
//! test vectors: tests/vectors/consent-proof.json.

use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};

const CONSENT_DOMAIN: &str = "EIRA-CONSENT-V1";

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 {
        return None;
    }
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(value.get(i..i + 2)?, 16).ok())
        .collect()
}

pub fn consent_proof(
    key: &[u8],
    verb: &str,
    uid: u32,
    session_id: &str,
    action_id: &str,
    content_hash: &str,
    rendering_hash: &str,
) -> Option<String> {
    if verb != "consent" && verb != "confirm" && verb != "delegate" {
        return None; // the user's decisions, nothing else
    }
    let uid = uid.to_string();
    let parts = [
        CONSENT_DOMAIN,
        verb,
        &uid,
        session_id,
        action_id,
        content_hash,
        rendering_hash,
    ];
    if parts.iter().any(|part| part.contains('\0')) {
        return None;
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(key).ok()?;
    mac.update(parts.join("\0").as_bytes());
    Some(hex(&mac.finalize().into_bytes()))
}

/// A delegation proposal's text hash (app/auth/delegation.py: sha256 of the text).
pub fn plain_hash(text: &str) -> String {
    format!("sha256:{}", hex(&Sha256::digest(text.as_bytes())))
}

/// The agent recomputes the hash of the text it is about to show: what the
/// user sees is exactly what the consent covers.
pub fn rendering_hash(text: &str, lang: &str, version: &str) -> String {
    let material = format!("eira-render\0{version}\0{lang}\0{text}");
    format!("sha256:{}", hex(&Sha256::digest(material.as_bytes())))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn proofs_match_the_python_gate() {
        let vectors: Value =
            serde_json::from_str(include_str!("../../../tests/vectors/consent-proof.json"))
                .unwrap();
        let mut checked = 0;
        for case in vectors["cases"].as_array().unwrap() {
            let verb = case["verb"].as_str().unwrap();
            let proof = consent_proof(
                &decode_hex(case["key"].as_str().unwrap()).unwrap(),
                verb,
                case["uid"].as_u64().unwrap() as u32,
                case["session_id"].as_str().unwrap(),
                case["action_id"].as_str().unwrap(),
                case["content_hash"].as_str().unwrap(),
                case["rendering_hash"].as_str().unwrap(),
            );
            assert_eq!(proof.as_deref(), case["proof"].as_str());
            checked += 1;
        }
        assert!(checked >= 3);
    }

    #[test]
    fn only_consent_and_confirm() {
        assert!(consent_proof(b"k", "execute", 1, "s", "a", "c", "r").is_none());
        assert!(consent_proof(b"k", "consent", 1, "s\0", "a", "c", "r").is_none());
    }

    #[test]
    fn rendering_hash_matches_render_py() {
        // python3 -c 'from app.gate.render import rendering_hash as h; print(h("Send til Bo", "da", "1"))'
        assert_eq!(
            rendering_hash("Send til Bo", "da", "1"),
            "sha256:".to_string()
                + &hex(&Sha256::digest(
                    "eira-render\x001\x00da\x00Send til Bo".as_bytes()
                ))
        );
    }
}
