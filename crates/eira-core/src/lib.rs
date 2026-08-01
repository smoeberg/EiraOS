#![deny(warnings)]

pub mod ffi;

use serde_json::{Map, Value};
use sha3::{Digest, Sha3_256};
use std::collections::HashSet;

const STATE_FIELDS: [&str; 6] = [
    "id",
    "version",
    "timestamp_ns",
    "type",
    "payload",
    "previous_state_id",
];

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Null => "null".to_owned(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => serde_json::to_string(value).expect("string serialization"),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(canonical_json)
                .collect::<Vec<_>>()
                .join(",")
        ),
        Value::Object(values) => {
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort_unstable();
            let entries = keys
                .into_iter()
                .map(|key| {
                    format!(
                        "{}:{}",
                        serde_json::to_string(key).expect("object key serialization"),
                        canonical_json(&values[key])
                    )
                })
                .collect::<Vec<_>>()
                .join(",");
            format!("{{{entries}}}")
        }
    }
}

fn state_body(value: &Value) -> Result<Value, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "state must be a JSON object".to_owned())?;
    let mut body = Map::new();
    for field in STATE_FIELDS {
        match object.get(field) {
            Some(value) => {
                body.insert(field.to_owned(), value.clone());
            }
            None if field == "previous_state_id" => {
                body.insert(field.to_owned(), Value::Null);
            }
            None => return Err(format!("state field is missing: {field}")),
        }
    }
    Ok(Value::Object(body))
}

pub fn compute_hash_from_value(value: &Value) -> Result<String, String> {
    let body = state_body(value)?;
    let mut hasher = Sha3_256::new();
    hasher.update(canonical_json(&body).as_bytes());
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn compute_hash_from_json(input: &str) -> Result<String, String> {
    let state: Value = serde_json::from_str(input).map_err(|error| error.to_string())?;
    compute_hash_from_value(&state)
}

pub fn validate_chain_from_json(input: &str) -> Result<bool, String> {
    let states: Vec<Value> = serde_json::from_str(input).map_err(|error| error.to_string())?;
    let mut seen_ids = HashSet::new();
    for state in states {
        let object = state
            .as_object()
            .ok_or_else(|| "chain entries must be JSON objects".to_owned())?;
        let id = object
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| "state id must be a string".to_owned())?;
        if !seen_ids.insert(id.to_owned()) {
            return Ok(false);
        }
        if let Some(previous_id) = object.get("previous_state_id").and_then(Value::as_str) {
            if !seen_ids.contains(previous_id) {
                return Ok(false);
            }
        }
        let expected = object
            .get("hash")
            .and_then(Value::as_str)
            .ok_or_else(|| "state hash must be a string".to_owned())?;
        if compute_hash_from_value(&state)? != expected {
            return Ok(false);
        }
    }
    Ok(true)
}

#[cfg(target_arch = "wasm32")]
mod wasm {
    use super::{compute_hash_from_json, validate_chain_from_json};
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub fn eira_state_compute_hash_wasm(json_payload: &str) -> Result<String, JsValue> {
        compute_hash_from_json(json_payload).map_err(|error| JsValue::from_str(&error))
    }

    #[wasm_bindgen]
    pub fn eira_state_validate_chain_wasm(states_json: &str) -> Result<bool, JsValue> {
        validate_chain_from_json(states_json).map_err(|error| JsValue::from_str(&error))
    }
}

#[cfg(test)]
mod tests {
    use super::{compute_hash_from_json, validate_chain_from_json};

    #[test]
    fn hashes_canonical_state_json() {
        let state = r#"{"type":"DocumentState","timestamp_ns":1,"payload":{"æ":"ø","a":1},"previous_state_id":null,"version":1,"id":"00000000-0000-0000-0000-000000000001"}"#;
        assert_eq!(compute_hash_from_json(state).unwrap().len(), 64);
    }

    #[test]
    fn rejects_tampered_chain() {
        let state = r#"{"id":"00000000-0000-0000-0000-000000000001","version":1,"timestamp_ns":1,"type":"DocumentState","payload":{},"previous_state_id":null,"hash":"invalid"}"#;
        assert!(!validate_chain_from_json(&format!("[{state}]")).unwrap());
    }
}
