//! Event envelope (Phase 0 §3.1).
//!
//! Wire form is a canonical CBOR map with text keys. Unknown keys, wrong
//! types and unsupported versions are rejected on decode (fail closed).

use super::cbor::{self, CborError, Value};
use super::signature::{Signature, SignatureAlgorithm};
use std::fmt;

/// Envelope versions this build understands.
pub const ENVELOPE_VERSION: u16 = 1;
pub const MAX_EVENT_TYPE_LEN: usize = 128;

/// Nanoseconds since the Unix epoch, carried as a CBOR integer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct UnixTimestampNs(pub i64);

/// 128-bit identifier (UUIDv7 or random), carried as a 16-byte CBOR byte string.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Id128(pub [u8; 16]);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EventEnvelope {
    pub envelope_version: u16,
    pub event_id: Id128,
    /// Dotted lowercase name, e.g. `conversation.utterance`.
    pub event_type: String,
    pub schema_version: u16,
    pub producer_id: Id128,
    /// Per-producer sequence; starts at 1, no global ordering.
    pub sequence: u64,
    pub timestamp: UnixTimestampNs,
    pub correlation_id: Option<Id128>,
    pub payload: Value,
    pub signature: Option<Signature>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EnvelopeError {
    Cbor(CborError),
    NotAMap,
    UnknownField(String),
    MissingField(&'static str),
    WrongType(&'static str),
    UnsupportedEnvelopeVersion(u16),
    InvalidSchemaVersion,
    InvalidEventType,
    InvalidSequence,
}

impl fmt::Display for EnvelopeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for EnvelopeError {}

impl From<CborError> for EnvelopeError {
    fn from(error: CborError) -> Self {
        EnvelopeError::Cbor(error)
    }
}

const FIELDS: [&str; 10] = [
    "envelope_version",
    "event_id",
    "event_type",
    "schema_version",
    "producer_id",
    "sequence",
    "timestamp_ns",
    "correlation_id",
    "payload",
    "signature",
];

fn valid_event_type(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= MAX_EVENT_TYPE_LEN
        && !name.starts_with('.')
        && !name.ends_with('.')
        && !name.contains("..")
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || matches!(b, b'.' | b'_'))
}

impl EventEnvelope {
    /// Structural checks shared by encode and decode.
    pub fn validate(&self) -> Result<(), EnvelopeError> {
        if self.envelope_version != ENVELOPE_VERSION {
            return Err(EnvelopeError::UnsupportedEnvelopeVersion(
                self.envelope_version,
            ));
        }
        if self.schema_version == 0 {
            return Err(EnvelopeError::InvalidSchemaVersion);
        }
        if !valid_event_type(&self.event_type) {
            return Err(EnvelopeError::InvalidEventType);
        }
        if self.sequence == 0 {
            return Err(EnvelopeError::InvalidSequence);
        }
        Ok(())
    }

    fn to_value(&self, include_signature: bool) -> Value {
        let mut entries = vec![
            (
                Value::text("envelope_version"),
                Value::Integer(self.envelope_version.into()),
            ),
            (
                Value::text("event_id"),
                Value::Bytes(self.event_id.0.to_vec()),
            ),
            (Value::text("event_type"), Value::text(&self.event_type)),
            (
                Value::text("schema_version"),
                Value::Integer(self.schema_version.into()),
            ),
            (
                Value::text("producer_id"),
                Value::Bytes(self.producer_id.0.to_vec()),
            ),
            (
                Value::text("sequence"),
                Value::Integer(self.sequence.into()),
            ),
            (
                Value::text("timestamp_ns"),
                Value::Integer(self.timestamp.0.into()),
            ),
            (
                Value::text("correlation_id"),
                match self.correlation_id {
                    Some(id) => Value::Bytes(id.0.to_vec()),
                    None => Value::Null,
                },
            ),
            (Value::text("payload"), self.payload.clone()),
        ];
        if include_signature {
            if let Some(sig) = &self.signature {
                entries.push((
                    Value::text("signature"),
                    Value::Map(vec![
                        (Value::text("algorithm"), Value::text(sig.algorithm.name())),
                        (Value::text("key_id"), Value::Bytes(sig.key_id.0.to_vec())),
                        (Value::text("signature"), Value::Bytes(sig.bytes.to_vec())),
                    ]),
                ));
            }
        }
        Value::Map(entries)
    }

    /// Canonical CBOR of the complete envelope (what goes on the wire).
    pub fn to_cbor(&self) -> Result<Vec<u8>, EnvelopeError> {
        self.validate()?;
        Ok(cbor::encode(&self.to_value(true))?)
    }

    /// Canonical CBOR of the envelope without its signature: the signed body.
    pub fn to_unsigned_cbor(&self) -> Result<Vec<u8>, EnvelopeError> {
        self.validate()?;
        Ok(cbor::encode(&self.to_value(false))?)
    }

    pub fn from_cbor(bytes: &[u8]) -> Result<Self, EnvelopeError> {
        let value = cbor::decode(bytes)?;
        let entries = value.as_map().ok_or(EnvelopeError::NotAMap)?;
        let mut fields: [Option<&Value>; 10] = Default::default();
        for (key, value) in entries {
            let Value::Text(name) = key else {
                return Err(EnvelopeError::UnknownField(format!("{key:?}")));
            };
            let index = FIELDS
                .iter()
                .position(|f| f == name)
                .ok_or_else(|| EnvelopeError::UnknownField(name.clone()))?;
            fields[index] = Some(value);
        }
        let get = |i: usize| fields[i].ok_or(EnvelopeError::MissingField(FIELDS[i]));

        let envelope = EventEnvelope {
            envelope_version: u16_field(get(0)?, FIELDS[0])?,
            event_id: id_field(get(1)?, FIELDS[1])?,
            event_type: match get(2)? {
                Value::Text(t) => t.clone(),
                _ => return Err(EnvelopeError::WrongType(FIELDS[2])),
            },
            schema_version: u16_field(get(3)?, FIELDS[3])?,
            producer_id: id_field(get(4)?, FIELDS[4])?,
            sequence: match get(5)? {
                Value::Integer(n) => {
                    u64::try_from(*n).map_err(|_| EnvelopeError::WrongType(FIELDS[5]))?
                }
                _ => return Err(EnvelopeError::WrongType(FIELDS[5])),
            },
            timestamp: match get(6)? {
                Value::Integer(n) => UnixTimestampNs(
                    i64::try_from(*n).map_err(|_| EnvelopeError::WrongType(FIELDS[6]))?,
                ),
                _ => return Err(EnvelopeError::WrongType(FIELDS[6])),
            },
            correlation_id: match get(7)? {
                Value::Null => None,
                other => Some(id_field(other, FIELDS[7])?),
            },
            payload: get(8)?.clone(),
            signature: match fields[9] {
                None => None,
                Some(value) => Some(signature_field(value)?),
            },
        };
        envelope.validate()?;
        Ok(envelope)
    }
}

fn u16_field(value: &Value, name: &'static str) -> Result<u16, EnvelopeError> {
    match value {
        Value::Integer(n) => u16::try_from(*n).map_err(|_| EnvelopeError::WrongType(name)),
        _ => Err(EnvelopeError::WrongType(name)),
    }
}

fn bytes_field<const N: usize>(
    value: &Value,
    name: &'static str,
) -> Result<[u8; N], EnvelopeError> {
    match value {
        Value::Bytes(b) => b
            .as_slice()
            .try_into()
            .map_err(|_| EnvelopeError::WrongType(name)),
        _ => Err(EnvelopeError::WrongType(name)),
    }
}

fn id_field(value: &Value, name: &'static str) -> Result<Id128, EnvelopeError> {
    bytes_field::<16>(value, name).map(Id128)
}

fn signature_field(value: &Value) -> Result<Signature, EnvelopeError> {
    const NAME: &str = "signature";
    let entries = value.as_map().ok_or(EnvelopeError::WrongType(NAME))?;
    if entries.len() != 3 {
        return Err(EnvelopeError::WrongType(NAME));
    }
    let find = |key: &str| {
        entries
            .iter()
            .find(|(k, _)| matches!(k, Value::Text(t) if t == key))
            .map(|(_, v)| v)
            .ok_or(EnvelopeError::WrongType(NAME))
    };
    let algorithm = match find("algorithm")? {
        Value::Text(t) => SignatureAlgorithm::from_name(t).ok_or(EnvelopeError::WrongType(NAME))?,
        _ => return Err(EnvelopeError::WrongType(NAME)),
    };
    Ok(Signature {
        algorithm,
        key_id: id_field(find("key_id")?, NAME)?,
        bytes: bytes_field::<64>(find("signature")?, NAME)?,
    })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub(crate) fn sample() -> EventEnvelope {
        EventEnvelope {
            envelope_version: ENVELOPE_VERSION,
            event_id: Id128([0x11; 16]),
            event_type: "conversation.utterance".into(),
            schema_version: 1,
            producer_id: Id128([0x22; 16]),
            sequence: 7,
            timestamp: UnixTimestampNs(1_762_466_400_000_000_000),
            correlation_id: Some(Id128([0x33; 16])),
            // Listed in canonical order (shorter encoded key first), which is
            // the order a decoder returns map entries in.
            payload: Value::Map(vec![
                (Value::text("text"), Value::text("Kan vi mødes torsdag?")),
                (Value::text("conversation_id"), Value::text("obj:sag:42")),
            ]),
            signature: None,
        }
    }

    #[test]
    fn round_trips_and_is_deterministic() {
        let env = sample();
        let bytes = env.to_cbor().unwrap();
        assert_eq!(EventEnvelope::from_cbor(&bytes).unwrap(), env);
        assert_eq!(env.clone().to_cbor().unwrap(), bytes);
        // The timestamp is a plain CBOR integer (1b = uint64 head), never a string.
        let ts_key = cbor::encode(&Value::text("timestamp_ns")).unwrap();
        let at = bytes
            .windows(ts_key.len())
            .position(|w| w == ts_key.as_slice())
            .unwrap();
        assert_eq!(bytes[at + ts_key.len()], 0x1b);
    }

    #[test]
    fn rejects_unknown_missing_and_mistyped_fields() {
        let env = sample();
        let Value::Map(mut entries) = env.to_value(true) else {
            unreachable!()
        };
        let mut extra = entries.clone();
        extra.push((Value::text("admin"), Value::Bool(true)));
        assert_eq!(
            EventEnvelope::from_cbor(&cbor::encode(&Value::Map(extra)).unwrap()),
            Err(EnvelopeError::UnknownField("admin".into()))
        );

        entries.retain(|(k, _)| k != &Value::text("sequence"));
        assert_eq!(
            EventEnvelope::from_cbor(&cbor::encode(&Value::Map(entries)).unwrap()),
            Err(EnvelopeError::MissingField("sequence"))
        );

        let Value::Map(mut wrong) = env.to_value(true) else {
            unreachable!()
        };
        for (k, v) in &mut wrong {
            if k == &Value::text("event_id") {
                *v = Value::Bytes(vec![0; 15]);
            }
        }
        assert_eq!(
            EventEnvelope::from_cbor(&cbor::encode(&Value::Map(wrong)).unwrap()),
            Err(EnvelopeError::WrongType("event_id"))
        );
        assert_eq!(
            EventEnvelope::from_cbor(&cbor::encode(&Value::Integer(1)).unwrap()),
            Err(EnvelopeError::NotAMap)
        );
    }

    #[test]
    fn versions_and_names_are_validated() {
        let mut env = sample();
        env.envelope_version = 2;
        assert_eq!(
            env.to_cbor(),
            Err(EnvelopeError::UnsupportedEnvelopeVersion(2))
        );

        let mut env = sample();
        env.schema_version = 0;
        assert_eq!(env.to_cbor(), Err(EnvelopeError::InvalidSchemaVersion));

        let mut env = sample();
        env.sequence = 0;
        assert_eq!(env.to_cbor(), Err(EnvelopeError::InvalidSequence));

        for bad in ["", "Conversation", "a..b", ".a", "a.", "a b", "a-b"] {
            let mut env = sample();
            env.event_type = bad.into();
            assert_eq!(
                env.to_cbor(),
                Err(EnvelopeError::InvalidEventType),
                "{bad:?}"
            );
        }
    }

    #[test]
    fn a_received_envelope_with_an_unsupported_version_is_rejected() {
        let mut env = sample();
        env.envelope_version = 2;
        let bytes = cbor::encode(&env.to_value(true)).unwrap();
        assert_eq!(
            EventEnvelope::from_cbor(&bytes),
            Err(EnvelopeError::UnsupportedEnvelopeVersion(2))
        );
    }
}
