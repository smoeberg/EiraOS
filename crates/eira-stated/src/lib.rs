#![deny(warnings)]
#![deny(unsafe_op_in_unsafe_fn)]

pub mod ffi;

use eira_core::compute_hash_from_value;
use r2d2::{Pool, PooledConnection};
use r2d2_sqlite::SqliteConnectionManager;
use r2d2_sqlite::rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::Path;
use std::time::{Duration, Instant};
use thiserror::Error;

type SqlitePool = Pool<SqliteConnectionManager>;
type SqliteConnection = PooledConnection<SqliteConnectionManager>;

#[derive(Debug, Error)]
pub enum StateEngineError {
    #[error("state JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("SQLite failure: {0}")]
    Sqlite(#[from] r2d2_sqlite::rusqlite::Error),
    #[error("SQLite pool failure: {0}")]
    Pool(#[from] r2d2::Error),
    #[error("state hash does not match canonical state content")]
    HashMismatch,
    #[error("previous state does not exist: {0}")]
    MissingPrevious(String),
    #[error("state hash computation failed: {0}")]
    Hash(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StateRecord {
    pub id: String,
    pub version: i64,
    pub timestamp_ns: i64,
    #[serde(rename = "type")]
    pub state_type: String,
    pub payload: Value,
    pub previous_state_id: Option<String>,
    pub hash: String,
}

impl StateRecord {
    pub fn compute_hash(&self) -> Result<String, StateEngineError> {
        let value = serde_json::to_value(self)?;
        compute_hash_from_value(&value).map_err(StateEngineError::Hash)
    }

    pub fn validate_hash(&self) -> Result<(), StateEngineError> {
        if self.compute_hash()? == self.hash {
            Ok(())
        } else {
            Err(StateEngineError::HashMismatch)
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AppendReceipt {
    pub state_id: String,
    pub hash: String,
    pub latency_ns: u64,
}

#[derive(Clone)]
pub struct StateStore {
    pool: SqlitePool,
}

fn configure_connection(connection: &mut Connection, in_memory: bool) -> Result<(), r2d2_sqlite::rusqlite::Error> {
    connection.busy_timeout(Duration::from_secs(5))?;
    connection.set_prepared_statement_cache_capacity(32);
    if in_memory {
        connection.execute_batch(
            "PRAGMA journal_mode=MEMORY;
             PRAGMA synchronous=OFF;
             PRAGMA foreign_keys=ON;
             PRAGMA temp_store=MEMORY;",
        )?;
    } else {
        connection.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA synchronous=NORMAL;
             PRAGMA foreign_keys=ON;
             PRAGMA temp_store=MEMORY;
             PRAGMA wal_autocheckpoint=1000;",
        )?;
    }
    Ok(())
}

impl StateStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StateEngineError> {
        let path = path.as_ref();
        let in_memory = path == Path::new(":memory:");
        let manager = if in_memory {
            SqliteConnectionManager::memory()
        } else {
            SqliteConnectionManager::file(path)
        }
        .with_init(move |connection| configure_connection(connection, in_memory));
        let pool = Pool::builder()
            .max_size(if in_memory { 1 } else { 4 })
            .min_idle(Some(1))
            .connection_timeout(Duration::from_secs(5))
            .build(manager)?;
        let store = Self { pool };
        store.initialize()?;
        Ok(store)
    }

    fn connection(&self) -> Result<SqliteConnection, StateEngineError> {
        Ok(self.pool.get()?)
    }

    fn initialize(&self) -> Result<(), StateEngineError> {
        self.connection()?.execute_batch(
            "CREATE TABLE IF NOT EXISTS states (
                id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                timestamp_ns INTEGER NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                previous_state_id TEXT,
                hash TEXT UNIQUE NOT NULL
             );
             CREATE INDEX IF NOT EXISTS idx_states_previous
                 ON states(previous_state_id);
             CREATE INDEX IF NOT EXISTS idx_states_timestamp
                 ON states(timestamp_ns, id);
             CREATE TRIGGER IF NOT EXISTS states_immutable_update
                 BEFORE UPDATE ON states
                 BEGIN SELECT RAISE(ABORT, 'states are immutable'); END;
             CREATE TRIGGER IF NOT EXISTS states_immutable_delete
                 BEFORE DELETE ON states
                 BEGIN SELECT RAISE(ABORT, 'states are immutable'); END;",
        )?;
        Ok(())
    }

    pub fn append(&self, state: &StateRecord) -> Result<AppendReceipt, StateEngineError> {
        let started = Instant::now();
        state.validate_hash()?;
        let connection = self.connection()?;
        if let Some(previous) = &state.previous_state_id {
            let exists: bool = connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM states WHERE id = ?1)",
                [previous],
                |row| row.get(0),
            )?;
            if !exists {
                return Err(StateEngineError::MissingPrevious(previous.clone()));
            }
        }
        let payload = serde_json::to_string(&state.payload)?;
        connection.prepare_cached(
            "INSERT INTO states
             (id, version, timestamp_ns, type, payload, previous_state_id, hash)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        )?.execute(params![
            state.id,
            state.version,
            state.timestamp_ns,
            state.state_type,
            payload,
            state.previous_state_id,
            state.hash,
        ])?;
        Ok(AppendReceipt {
            state_id: state.id.clone(),
            hash: state.hash.clone(),
            latency_ns: started.elapsed().as_nanos().min(u128::from(u64::MAX)) as u64,
        })
    }

    fn row_to_state(row: &r2d2_sqlite::rusqlite::Row<'_>) -> r2d2_sqlite::rusqlite::Result<StateRecord> {
        let payload: String = row.get("payload")?;
        let payload = serde_json::from_str(&payload).map_err(|error| {
            r2d2_sqlite::rusqlite::Error::FromSqlConversionFailure(
                payload.len(),
                r2d2_sqlite::rusqlite::types::Type::Text,
                Box::new(error),
            )
        })?;
        Ok(StateRecord {
            id: row.get("id")?,
            version: row.get("version")?,
            timestamp_ns: row.get("timestamp_ns")?,
            state_type: row.get("type")?,
            payload,
            previous_state_id: row.get("previous_state_id")?,
            hash: row.get("hash")?,
        })
    }

    pub fn get_by_id(&self, state_id: &str) -> Result<Option<StateRecord>, StateEngineError> {
        let connection = self.connection()?;
        Ok(connection
            .query_row("SELECT * FROM states WHERE id = ?1", [state_id], Self::row_to_state)
            .optional()?)
    }

    pub fn get_by_hash(&self, state_hash: &str) -> Result<Option<StateRecord>, StateEngineError> {
        let connection = self.connection()?;
        Ok(connection
            .query_row("SELECT * FROM states WHERE hash = ?1", [state_hash], Self::row_to_state)
            .optional()?)
    }

    pub fn list_states(&self) -> Result<Vec<StateRecord>, StateEngineError> {
        let connection = self.connection()?;
        let mut statement = connection.prepare_cached(
            "SELECT * FROM states ORDER BY timestamp_ns ASC, id ASC",
        )?;
        let states = statement
            .query_map([], Self::row_to_state)?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(states)
    }

    pub fn count(&self) -> Result<u64, StateEngineError> {
        let value: i64 = self
            .connection()?
            .query_row("SELECT COUNT(*) FROM states", [], |row| row.get(0))?;
        u64::try_from(value).map_err(|_| StateEngineError::Hash("negative state count".to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::{StateEngineError, StateRecord, StateStore};
    use eira_core::compute_hash_from_value;
    use serde_json::json;

    fn state(id: &str, previous: Option<&str>, version: i64) -> StateRecord {
        let mut value = json!({
            "id": id,
            "version": version,
            "timestamp_ns": version,
            "type": "DocumentState",
            "payload": {"title": "ærlig øvelse", "version": version},
            "previous_state_id": previous,
        });
        let hash = compute_hash_from_value(&value).unwrap();
        value["hash"] = json!(hash);
        serde_json::from_value(value).unwrap()
    }

    #[test]
    fn appends_and_reads_canonical_chain() {
        let store = StateStore::open(":memory:").unwrap();
        let first = state("00000000-0000-0000-0000-000000000001", None, 1);
        let second = state(
            "00000000-0000-0000-0000-000000000002",
            Some(&first.id),
            2,
        );
        store.append(&first).unwrap();
        store.append(&second).unwrap();
        assert_eq!(store.list_states().unwrap(), vec![first, second]);
    }

    #[test]
    fn rejects_tampering_before_sqlite_write() {
        let store = StateStore::open(":memory:").unwrap();
        let mut invalid = state("00000000-0000-0000-0000-000000000001", None, 1);
        invalid.payload = json!({"tampered": true});
        assert!(matches!(store.append(&invalid), Err(StateEngineError::HashMismatch)));
        assert_eq!(store.count().unwrap(), 0);
    }
}
