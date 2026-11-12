//! One consent, start to end (EIRA-CONSENT-AGENT §5.4). The app sends only
//! an action id. Everything shown and signed comes from identityd and the
//! gate; the key never leaves this process.

use crate::proof::{consent_proof, decode_hex, plain_hash, rendering_hash};
use serde_json::{Value, json};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Approve,
    Decline,
    /// The window was closed or lost: nothing is decided.
    Closed,
}

/// The daemons, behind a seam so the flow can be tested without sockets.
pub trait Daemons {
    fn claim_key(&mut self) -> Result<Value, String>;
    fn gate(&mut self, method: &str, params: Value) -> Result<Value, String>;
    fn delegation(&mut self, method: &str, params: Value) -> Result<Value, String>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// A gate action the user proposed.
    Action,
    /// A gate action the model proposed on the user's behalf.
    ModelAction,
    /// Letting the model prepare on the user's behalf (EIRA Delegation v1.1).
    Delegation,
}

pub trait Screen {
    /// Shows the text and returns the user's decision (R-6.3 lives here).
    fn ask(&mut self, text: &str, kind: Kind) -> Decision;
}

/// Holds the key only for the length of one decision and wipes it after.
struct Key(Vec<u8>);

impl Drop for Key {
    fn drop(&mut self) {
        for byte in self.0.iter_mut() {
            // SAFETY: writing through a valid &mut u8; volatile so the
            // compiler does not drop the wipe.
            unsafe { std::ptr::write_volatile(byte, 0) };
        }
    }
}

fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("missing {name}"))
}

fn rendering(
    daemons: &mut dyn Daemons,
    action_id: &str,
    session_id: &str,
) -> Result<Value, String> {
    let shown = daemons.gate(
        "gate.rendering",
        json!({"action_id": action_id, "session_id": session_id}),
    )?;
    let r = &shown["rendering"];
    let (text, hash) = (field(r, "text")?, field(r, "hash")?);
    // Never show or sign a text whose hash we did not compute ourselves.
    if rendering_hash(text, field(r, "lang")?, field(r, "version")?) != hash {
        return Err("rendering hash does not match its text".into());
    }
    Ok(shown)
}

pub fn show(
    action_id: &str,
    uid: u32,
    daemons: &mut dyn Daemons,
    screen: &mut dyn Screen,
) -> Value {
    match run(action_id, uid, daemons, screen) {
        Ok(result) => result,
        Err(error) => json!({"status": "error", "error": error}),
    }
}

fn run(
    action_id: &str,
    uid: u32,
    daemons: &mut dyn Daemons,
    screen: &mut dyn Screen,
) -> Result<Value, String> {
    if action_id.is_empty() || action_id.len() > 200 {
        return Err("action_id".into());
    }
    let claim = daemons.claim_key()?;
    let session_id = field(&claim, "session_id")?.to_string();
    let key = Key(decode_hex(field(&claim, "consent_key")?).ok_or("bad key")?);
    drop(claim);

    let shown = rendering(daemons, action_id, &session_id)?;
    let text = field(&shown["rendering"], "text")?.to_string();
    let kind = if shown["origin"] == "model" {
        Kind::ModelAction
    } else {
        Kind::Action
    };
    match screen.ask(&text, kind) {
        Decision::Approve => {}
        Decision::Decline => return Ok(json!({"status": "declined"})),
        Decision::Closed => return Ok(json!({"status": "closed"})),
    }

    // One decision by the user covers what is due: consent, then the
    // confirmation that executes. Each step re-reads the gate's state.
    let mut steps = Vec::new();
    for _ in 0..2 {
        let current = rendering(daemons, action_id, &session_id)?;
        let verb = field(&current, "next")?.to_string();
        let content_hash = field(&current, "content_hash")?.to_string();
        let rhash = field(&current["rendering"], "hash")?.to_string();
        // The text must still be the one the user just approved.
        if field(&current["rendering"], "text")? != text {
            return Err("the text changed after it was shown".into());
        }
        let proof = consent_proof(
            &key.0,
            &verb,
            uid,
            &session_id,
            action_id,
            &content_hash,
            &rhash,
        )
        .ok_or("cannot sign")?;
        let result = daemons.gate(
            &format!("gate.{verb}"),
            json!({"action_id": action_id, "content_hash": content_hash, "rendering_hash": rhash,
                   "session_id": session_id, "proof": proof}),
        )?;
        let done = verb == "confirm";
        steps.push(json!({"step": verb, "result": result}));
        if done || result["error"].is_string() {
            break;
        }
    }
    Ok(json!({"status": "decided", "steps": steps}))
}

/// A delegation (EIRA Delegation v1.1), decided here like a consent: the
/// text comes from delegationd, the proof never leaves this process.
pub fn show_delegation(
    proposal_id: &str,
    uid: u32,
    daemons: &mut dyn Daemons,
    screen: &mut dyn Screen,
) -> Value {
    match run_delegation(proposal_id, uid, daemons, screen) {
        Ok(result) => result,
        Err(error) => json!({"status": "error", "error": error}),
    }
}

fn run_delegation(
    proposal_id: &str,
    uid: u32,
    daemons: &mut dyn Daemons,
    screen: &mut dyn Screen,
) -> Result<Value, String> {
    if proposal_id.is_empty() || proposal_id.len() > 200 {
        return Err("proposal_id".into());
    }
    let claim = daemons.claim_key()?;
    let session_id = field(&claim, "session_id")?.to_string();
    let key = Key(decode_hex(field(&claim, "consent_key")?).ok_or("bad key")?);
    drop(claim);
    let shown = daemons.delegation(
        "delegation.proposal",
        json!({"proposal_id": proposal_id, "session_id": session_id}),
    )?;
    let (text, rhash) = (
        field(&shown["rendering"], "text")?,
        field(&shown["rendering"], "hash")?,
    );
    if plain_hash(text) != rhash {
        return Err("rendering hash does not match its text".into());
    }
    match screen.ask(text, Kind::Delegation) {
        Decision::Approve => {}
        Decision::Decline => return Ok(json!({"status": "declined"})),
        Decision::Closed => return Ok(json!({"status": "closed"})),
    }
    let content_hash = field(&shown, "content_hash")?;
    let proof = consent_proof(
        &key.0,
        "delegate",
        uid,
        &session_id,
        proposal_id,
        content_hash,
        rhash,
    )
    .ok_or("cannot sign")?;
    let result = daemons.delegation(
        "delegation.create",
        json!({"proposal_id": proposal_id, "content_hash": content_hash, "rendering_hash": rhash,
               "session_id": session_id, "proof": proof}),
    )?;
    Ok(json!({"status": "decided", "result": result}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proof::consent_proof;

    const KEY: &str = "1111111111111111111111111111111111111111111111111111111111111111";

    struct FakeGate {
        consented: bool,
        text: String,
        calls: Vec<(String, Value)>,
        tamper: bool,
    }

    impl Daemons for FakeGate {
        fn claim_key(&mut self) -> Result<Value, String> {
            Ok(json!({"session_id": "s-1", "consent_key": KEY}))
        }
        fn gate(&mut self, method: &str, params: Value) -> Result<Value, String> {
            self.calls.push((method.to_string(), params.clone()));
            match method {
                "gate.rendering" => {
                    let hash = if self.tamper {
                        "sha256:00".to_string()
                    } else {
                        rendering_hash(&self.text, "da", "1")
                    };
                    Ok(json!({"content_hash": "sha256:c", "origin": "model",
                              "next": if self.consented {"confirm"} else {"consent"},
                              "rendering": {"text": self.text, "hash": hash, "lang": "da", "version": "1"}}))
                }
                "gate.consent" => {
                    self.consented = true;
                    Ok(json!({"detail": "consent recorded"}))
                }
                "gate.confirm" => Ok(json!({"decision": "PASS"})),
                _ => Err("unknown".into()),
            }
        }
        fn delegation(&mut self, method: &str, params: Value) -> Result<Value, String> {
            self.calls.push((method.to_string(), params.clone()));
            match method {
                "delegation.proposal" => Ok(json!({"content_hash": "sha256:d",
                    "rendering": {"text": self.text, "hash": if self.tamper {"sha256:0".into()} else {plain_hash(&self.text)}}})),
                "delegation.create" => Ok(json!({"status": "created"})),
                _ => Err("unknown".into()),
            }
        }
    }

    struct Answer(Decision, Vec<(String, Kind)>);
    impl Screen for Answer {
        fn ask(&mut self, text: &str, kind: Kind) -> Decision {
            self.1.push((text.to_string(), kind));
            self.0
        }
    }

    fn gate() -> FakeGate {
        FakeGate {
            consented: false,
            text: "Send «hej» til Bo".into(),
            calls: vec![],
            tamper: false,
        }
    }

    #[test]
    fn approve_consents_then_confirms_with_valid_proofs() {
        let (mut g, mut s) = (gate(), Answer(Decision::Approve, vec![]));
        let out = show("dlg-1", 1000, &mut g, &mut s);
        assert_eq!(out["status"], "decided");
        assert_eq!(
            s.1,
            vec![("Send «hej» til Bo".to_string(), Kind::ModelAction)]
        );
        let decided: Vec<_> = g
            .calls
            .iter()
            .filter(|(m, _)| m != "gate.rendering")
            .collect();
        assert_eq!(decided.len(), 2);
        let rhash = rendering_hash("Send «hej» til Bo", "da", "1");
        for ((method, params), verb) in decided.iter().zip(["consent", "confirm"]) {
            assert_eq!(method, &format!("gate.{verb}"));
            let key = decode_hex(KEY).unwrap();
            let expected =
                consent_proof(&key, verb, 1000, "s-1", "dlg-1", "sha256:c", &rhash).unwrap();
            assert_eq!(params["proof"], expected);
        }
    }

    #[test]
    fn decline_or_close_decides_nothing() {
        for decision in [Decision::Decline, Decision::Closed] {
            let (mut g, mut s) = (gate(), Answer(decision, vec![]));
            show("dlg-1", 1000, &mut g, &mut s);
            assert!(g.calls.iter().all(|(m, _)| m == "gate.rendering"));
        }
    }

    #[test]
    fn a_text_whose_hash_does_not_match_is_never_shown() {
        let (mut g, mut s) = (gate(), Answer(Decision::Approve, vec![]));
        g.tamper = true;
        let out = show("dlg-1", 1000, &mut g, &mut s);
        assert_eq!(out["status"], "error");
        assert!(s.1.is_empty());
    }

    #[test]
    fn a_delegation_is_signed_with_the_delegate_verb_after_approval() {
        let (mut g, mut s) = (gate(), Answer(Decision::Approve, vec![]));
        let out = show_delegation("dlgp-1", 1000, &mut g, &mut s);
        assert_eq!(out["status"], "decided");
        assert_eq!(s.1[0].1, Kind::Delegation);
        let (_, params) = g
            .calls
            .iter()
            .find(|(m, _)| m == "delegation.create")
            .unwrap();
        let key = decode_hex(KEY).unwrap();
        let rhash = plain_hash("Send «hej» til Bo");
        let expected =
            consent_proof(&key, "delegate", 1000, "s-1", "dlgp-1", "sha256:d", &rhash).unwrap();
        assert_eq!(params["proof"], expected);
        // Declined or tampered: nothing is created.
        for (decision, tamper) in [(Decision::Decline, false), (Decision::Approve, true)] {
            let (mut g, mut s) = (gate(), Answer(decision, vec![]));
            g.tamper = tamper;
            show_delegation("dlgp-1", 1000, &mut g, &mut s);
            assert!(g.calls.iter().all(|(m, _)| m != "delegation.create"));
        }
    }

    #[test]
    fn the_app_gives_only_an_action_id() {
        let (mut g, mut s) = (gate(), Answer(Decision::Approve, vec![]));
        assert_eq!(show("", 1000, &mut g, &mut s)["status"], "error");
        assert_eq!(
            show(&"x".repeat(201), 1000, &mut g, &mut s)["status"],
            "error"
        );
    }
}
