//! EiraOS deterministic CBOR profile (Phase 0 §3.1).
//!
//! A deliberately small subset of RFC 8949 with core deterministic encoding:
//!
//! * integers, byte strings, text strings, arrays, maps, `true`, `false`, `null`;
//! * shortest-form heads, definite lengths only;
//! * map keys sorted bytewise by their encoded form, no duplicates;
//! * no floats, no tags, no `undefined`, no simple values beyond the three above.
//!
//! The decoder enforces the same profile: a message that is valid CBOR but not
//! in this exact canonical form is rejected. That makes "decode then re-encode"
//! the identity, which is what signatures and golden vectors rely on.

use std::fmt;

/// Maximum nesting depth accepted by the decoder.
pub const MAX_DEPTH: usize = 32;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Value {
    /// Integer in the CBOR range `-2^64 ..= 2^64 - 1`.
    Integer(i128),
    Bytes(Vec<u8>),
    Text(String),
    Array(Vec<Value>),
    /// Entries in any order; the encoder sorts them canonically.
    Map(Vec<(Value, Value)>),
    Bool(bool),
    Null,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CborError {
    UnexpectedEnd,
    TrailingBytes,
    IntegerOutOfRange,
    NonCanonicalHead,
    IndefiniteLength,
    UnsupportedMajorType(u8),
    UnsupportedSimpleValue(u8),
    InvalidUtf8,
    UnsortedMapKeys,
    DuplicateMapKey,
    TooDeep,
    LengthTooLarge,
}

impl fmt::Display for CborError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for CborError {}

const INT_MAX: i128 = u64::MAX as i128;
const INT_MIN: i128 = -(u64::MAX as i128) - 1;

/// Encode `value` in the EiraOS canonical form.
pub fn encode(value: &Value) -> Result<Vec<u8>, CborError> {
    let mut out = Vec::new();
    encode_into(value, &mut out, 0)?;
    Ok(out)
}

fn head(major: u8, arg: u64, out: &mut Vec<u8>) {
    let major = major << 5;
    if arg < 24 {
        out.push(major | arg as u8);
    } else if arg <= u8::MAX as u64 {
        out.push(major | 24);
        out.push(arg as u8);
    } else if arg <= u16::MAX as u64 {
        out.push(major | 25);
        out.extend_from_slice(&(arg as u16).to_be_bytes());
    } else if arg <= u32::MAX as u64 {
        out.push(major | 26);
        out.extend_from_slice(&(arg as u32).to_be_bytes());
    } else {
        out.push(major | 27);
        out.extend_from_slice(&arg.to_be_bytes());
    }
}

fn encode_into(value: &Value, out: &mut Vec<u8>, depth: usize) -> Result<(), CborError> {
    if depth > MAX_DEPTH {
        return Err(CborError::TooDeep);
    }
    match value {
        Value::Integer(n) => {
            if !(INT_MIN..=INT_MAX).contains(n) {
                return Err(CborError::IntegerOutOfRange);
            }
            if *n >= 0 {
                head(0, *n as u64, out);
            } else {
                head(1, (-1 - *n) as u64, out);
            }
        }
        Value::Bytes(bytes) => {
            head(2, bytes.len() as u64, out);
            out.extend_from_slice(bytes);
        }
        Value::Text(text) => {
            head(3, text.len() as u64, out);
            out.extend_from_slice(text.as_bytes());
        }
        Value::Array(items) => {
            head(4, items.len() as u64, out);
            for item in items {
                encode_into(item, out, depth + 1)?;
            }
        }
        Value::Map(entries) => {
            let mut encoded = Vec::with_capacity(entries.len());
            for (key, value) in entries {
                let mut k = Vec::new();
                encode_into(key, &mut k, depth + 1)?;
                let mut v = Vec::new();
                encode_into(value, &mut v, depth + 1)?;
                encoded.push((k, v));
            }
            encoded.sort_by(|a, b| a.0.cmp(&b.0));
            if encoded.windows(2).any(|pair| pair[0].0 == pair[1].0) {
                return Err(CborError::DuplicateMapKey);
            }
            head(5, encoded.len() as u64, out);
            for (k, v) in encoded {
                out.extend_from_slice(&k);
                out.extend_from_slice(&v);
            }
        }
        Value::Bool(false) => out.push(0xf4),
        Value::Bool(true) => out.push(0xf5),
        Value::Null => out.push(0xf6),
    }
    Ok(())
}

/// Decode exactly one canonical item; trailing bytes are an error.
pub fn decode(bytes: &[u8]) -> Result<Value, CborError> {
    let mut reader = Reader { bytes, pos: 0 };
    let value = reader.item(0)?;
    if reader.pos != bytes.len() {
        return Err(CborError::TrailingBytes);
    }
    Ok(value)
}

struct Reader<'a> {
    bytes: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], CborError> {
        let end = self.pos.checked_add(n).ok_or(CborError::LengthTooLarge)?;
        if end > self.bytes.len() {
            return Err(CborError::UnexpectedEnd);
        }
        let slice = &self.bytes[self.pos..end];
        self.pos = end;
        Ok(slice)
    }

    /// Read a head and enforce shortest-form encoding of its argument.
    fn head(&mut self) -> Result<(u8, u8, u64), CborError> {
        let initial = self.take(1)?[0];
        let major = initial >> 5;
        let info = initial & 0x1f;
        let arg = match info {
            0..=23 => info as u64,
            24 => {
                let v = self.take(1)?[0] as u64;
                if v < 24 {
                    return Err(CborError::NonCanonicalHead);
                }
                v
            }
            25 => {
                let v = u16::from_be_bytes(self.take(2)?.try_into().unwrap()) as u64;
                if v <= u8::MAX as u64 {
                    return Err(CborError::NonCanonicalHead);
                }
                v
            }
            26 => {
                let v = u32::from_be_bytes(self.take(4)?.try_into().unwrap()) as u64;
                if v <= u16::MAX as u64 {
                    return Err(CborError::NonCanonicalHead);
                }
                v
            }
            27 => {
                let v = u64::from_be_bytes(self.take(8)?.try_into().unwrap());
                if v <= u32::MAX as u64 {
                    return Err(CborError::NonCanonicalHead);
                }
                v
            }
            31 => return Err(CborError::IndefiniteLength),
            _ => return Err(CborError::NonCanonicalHead),
        };
        Ok((major, info, arg))
    }

    fn length(&self, arg: u64) -> Result<usize, CborError> {
        // Every element needs at least one byte, so a length larger than the
        // remaining input can never be valid; reject before allocating.
        let remaining = (self.bytes.len() - self.pos) as u64;
        if arg > remaining {
            return Err(CborError::UnexpectedEnd);
        }
        usize::try_from(arg).map_err(|_| CborError::LengthTooLarge)
    }

    fn item(&mut self, depth: usize) -> Result<Value, CborError> {
        if depth > MAX_DEPTH {
            return Err(CborError::TooDeep);
        }
        let start = self.pos;
        let (major, info, arg) = self.head()?;
        match major {
            0 => Ok(Value::Integer(arg as i128)),
            1 => Ok(Value::Integer(-1 - arg as i128)),
            2 => {
                let len = self.length(arg)?;
                Ok(Value::Bytes(self.take(len)?.to_vec()))
            }
            3 => {
                let len = self.length(arg)?;
                let raw = self.take(len)?;
                let text = std::str::from_utf8(raw).map_err(|_| CborError::InvalidUtf8)?;
                Ok(Value::Text(text.to_owned()))
            }
            4 => {
                let len = self.length(arg)?;
                let mut items = Vec::with_capacity(len);
                for _ in 0..len {
                    items.push(self.item(depth + 1)?);
                }
                Ok(Value::Array(items))
            }
            5 => {
                let len = self.length(arg)?;
                let mut entries = Vec::with_capacity(len);
                let mut previous_key: Option<&[u8]> = None;
                for _ in 0..len {
                    let key_start = self.pos;
                    let key = self.item(depth + 1)?;
                    let key_bytes = &self.bytes[key_start..self.pos];
                    if let Some(prev) = previous_key {
                        match prev.cmp(key_bytes) {
                            std::cmp::Ordering::Less => {}
                            std::cmp::Ordering::Equal => return Err(CborError::DuplicateMapKey),
                            std::cmp::Ordering::Greater => {
                                return Err(CborError::UnsortedMapKeys);
                            }
                        }
                    }
                    previous_key = Some(key_bytes);
                    let value = self.item(depth + 1)?;
                    entries.push((key, value));
                }
                Ok(Value::Map(entries))
            }
            6 => Err(CborError::UnsupportedMajorType(6)),
            7 => {
                // Only the one-byte simple values false/true/null are allowed;
                // floats (info 25..27) and everything else are rejected.
                if self.pos - start != 1 {
                    return Err(CborError::UnsupportedSimpleValue(info));
                }
                match info {
                    20 => Ok(Value::Bool(false)),
                    21 => Ok(Value::Bool(true)),
                    22 => Ok(Value::Null),
                    other => Err(CborError::UnsupportedSimpleValue(other)),
                }
            }
            _ => unreachable!("major type is three bits"),
        }
    }
}

impl Value {
    pub fn text(s: &str) -> Value {
        Value::Text(s.to_owned())
    }

    pub fn as_map(&self) -> Option<&[(Value, Value)]> {
        match self {
            Value::Map(entries) => Some(entries),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hex(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }

    fn unhex(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }

    #[test]
    fn golden_vectors_from_rfc8949_appendix_a() {
        let cases: &[(Value, &str)] = &[
            (Value::Integer(0), "00"),
            (Value::Integer(23), "17"),
            (Value::Integer(24), "1818"),
            (Value::Integer(1000), "1903e8"),
            (Value::Integer(1_000_000), "1a000f4240"),
            (Value::Integer(1_000_000_000_000), "1b000000e8d4a51000"),
            (Value::Integer(u64::MAX as i128), "1bffffffffffffffff"),
            (Value::Integer(-1), "20"),
            (Value::Integer(-1000), "3903e7"),
            (Value::Integer(INT_MIN), "3bffffffffffffffff"),
            (Value::Bytes(vec![1, 2, 3, 4]), "4401020304"),
            (Value::text("IETF"), "6449455446"),
            (Value::text("ü"), "62c3bc"),
            (Value::Bool(false), "f4"),
            (Value::Bool(true), "f5"),
            (Value::Null, "f6"),
            (
                Value::Array(vec![
                    Value::Integer(1),
                    Value::Array(vec![Value::Integer(2), Value::Integer(3)]),
                ]),
                "8201820203",
            ),
            (
                Value::Map(vec![
                    (Value::text("b"), Value::Integer(2)),
                    (Value::text("a"), Value::Integer(1)),
                ]),
                "a2616101616202",
            ),
        ];
        for (value, expected) in cases {
            let encoded = encode(value).unwrap();
            assert_eq!(hex(&encoded), *expected, "encode {value:?}");
            let decoded = decode(&encoded).unwrap();
            assert_eq!(encode(&decoded).unwrap(), encoded, "round-trip {value:?}");
        }
    }

    #[test]
    fn map_keys_sort_by_encoded_bytes_not_by_text() {
        // Shorter encodings sort first: 10 (0x0a) < 100 (0x1864) < -1 (0x20).
        let value = Value::Map(vec![
            (Value::Integer(-1), Value::Null),
            (Value::Integer(100), Value::Null),
            (Value::Integer(10), Value::Null),
        ]);
        assert_eq!(hex(&encode(&value).unwrap()), "a30af61864f620f6");
    }

    #[test]
    fn decoder_rejects_everything_outside_the_profile() {
        let rejects: &[(&str, CborError)] = &[
            ("", CborError::UnexpectedEnd),
            ("0000", CborError::TrailingBytes),
            ("1817", CborError::NonCanonicalHead),
            ("190017", CborError::NonCanonicalHead),
            ("1a0000ffff", CborError::NonCanonicalHead),
            ("1b00000000ffffffff", CborError::NonCanonicalHead),
            ("1c", CborError::NonCanonicalHead),
            ("5f4101ff", CborError::IndefiniteLength),
            ("9f01ff", CborError::IndefiniteLength),
            ("c11a514b67b0", CborError::UnsupportedMajorType(6)),
            ("f93c00", CborError::UnsupportedSimpleValue(25)),
            ("fb3ff199999999999a", CborError::UnsupportedSimpleValue(27)),
            ("f7", CborError::UnsupportedSimpleValue(23)),
            ("f820", CborError::UnsupportedSimpleValue(24)),
            ("62c328", CborError::InvalidUtf8),
            ("a2616202616101", CborError::UnsortedMapKeys),
            ("a2616101616102", CborError::DuplicateMapKey),
            ("5a7fffffff", CborError::UnexpectedEnd),
            ("9bffffffffffffffff", CborError::UnexpectedEnd),
            ("4201", CborError::UnexpectedEnd),
        ];
        for (input, expected) in rejects {
            assert_eq!(
                decode(&unhex(input)),
                Err(expected.clone()),
                "input {input}"
            );
        }
    }

    #[test]
    fn depth_is_bounded_on_both_sides() {
        let mut deep = Value::Null;
        for _ in 0..=MAX_DEPTH {
            deep = Value::Array(vec![deep]);
        }
        assert_eq!(encode(&deep), Err(CborError::TooDeep));
        let mut bytes = vec![0x81; MAX_DEPTH + 1];
        bytes.push(0xf6);
        assert_eq!(decode(&bytes), Err(CborError::TooDeep));
    }

    #[test]
    fn duplicate_keys_cannot_be_encoded() {
        let value = Value::Map(vec![
            (Value::text("a"), Value::Integer(1)),
            (Value::text("a"), Value::Integer(2)),
        ]);
        assert_eq!(encode(&value), Err(CborError::DuplicateMapKey));
    }

    #[test]
    fn integers_outside_cbor_range_are_rejected() {
        assert_eq!(
            encode(&Value::Integer(INT_MAX + 1)),
            Err(CborError::IntegerOutOfRange)
        );
        assert_eq!(
            encode(&Value::Integer(INT_MIN - 1)),
            Err(CborError::IntegerOutOfRange)
        );
    }
}
