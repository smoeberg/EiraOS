use crate::{StateRecord, StateStore};
use std::cell::RefCell;
use std::ffi::{CStr, CString, c_char};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;

const EIRA_OK: i32 = 0;
const EIRA_INVALID_ARGUMENT: i32 = -1;
const EIRA_ENGINE_ERROR: i32 = -2;
const EIRA_PANIC: i32 = -3;

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(error: impl ToString) {
    LAST_ERROR.with(|slot| *slot.borrow_mut() = error.to_string());
}

unsafe fn read_input(input: *const c_char) -> Result<String, String> {
    if input.is_null() {
        return Err("input pointer is null".to_owned());
    }
    // SAFETY: the caller promises a live, NUL-terminated C string.
    unsafe { CStr::from_ptr(input) }
        .to_str()
        .map(str::to_owned)
        .map_err(|error| error.to_string())
}

unsafe fn store_from_handle<'a>(handle: *mut StateStore) -> Result<&'a StateStore, String> {
    // SAFETY: the caller owns a handle returned by eira_stated_open and keeps it
    // alive for this call.
    unsafe { handle.as_ref() }.ok_or_else(|| "state-store handle is null".to_owned())
}

fn owned_string(value: String) -> *mut c_char {
    CString::new(value).map_or(ptr::null_mut(), CString::into_raw)
}

/// Opens a pooled Rust state store. The returned handle must be closed once.
///
/// # Safety
/// `db_path` must point to a valid NUL-terminated UTF-8 string.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_open(db_path: *const c_char) -> *mut StateStore {
    match catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds the pointer contract.
        let path = unsafe { read_input(db_path) }?;
        StateStore::open(path).map_err(|error| error.to_string())
    })) {
        Ok(Ok(store)) => Box::into_raw(Box::new(store)),
        Ok(Err(error)) => {
            set_error(error);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic caught while opening Rust state store");
            ptr::null_mut()
        }
    }
}

/// Closes a state-store handle returned by `eira_stated_open`.
///
/// # Safety
/// `handle` must be null or a live handle that has not already been closed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_close(handle: *mut StateStore) {
    if !handle.is_null() {
        // SAFETY: this function's caller upholds the allocation contract.
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// Appends one canonical Eira state encoded as UTF-8 JSON.
///
/// # Safety
/// Both pointers must remain valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_append_json(
    handle: *mut StateStore,
    state_json: *const c_char,
) -> i32 {
    match catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds both pointer contracts.
        let store = unsafe { store_from_handle(handle) }?;
        // SAFETY: this function's caller upholds both pointer contracts.
        let input = unsafe { read_input(state_json) }?;
        let state: StateRecord = serde_json::from_str(&input).map_err(|error| error.to_string())?;
        store.append(&state).map_err(|error| error.to_string())
    })) {
        Ok(Ok(_)) => EIRA_OK,
        Ok(Err(error)) => {
            set_error(error);
            EIRA_ENGINE_ERROR
        }
        Err(_) => {
            set_error("panic caught while appending state");
            EIRA_PANIC
        }
    }
}

unsafe fn get_state_json(
    handle: *mut StateStore,
    key: *const c_char,
    by_hash: bool,
) -> *mut c_char {
    match catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: the outer FFI function's caller upholds both contracts.
        let store = unsafe { store_from_handle(handle) }?;
        // SAFETY: the outer FFI function's caller upholds both contracts.
        let key = unsafe { read_input(key) }?;
        let value = if by_hash {
            store.get_by_hash(&key)
        } else {
            store.get_by_id(&key)
        }
        .map_err(|error| error.to_string())?;
        serde_json::to_string(&value).map_err(|error| error.to_string())
    })) {
        Ok(Ok(value)) => owned_string(value),
        Ok(Err(error)) => {
            set_error(error);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic caught while reading state");
            ptr::null_mut()
        }
    }
}

/// Returns a JSON state or JSON `null` for an unknown id.
///
/// # Safety
/// Both pointers must remain valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_get_by_id_json(
    handle: *mut StateStore,
    state_id: *const c_char,
) -> *mut c_char {
    // SAFETY: this function's caller upholds both pointer contracts.
    unsafe { get_state_json(handle, state_id, false) }
}

/// Returns a JSON state or JSON `null` for an unknown hash.
///
/// # Safety
/// Both pointers must remain valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_get_by_hash_json(
    handle: *mut StateStore,
    state_hash: *const c_char,
) -> *mut c_char {
    // SAFETY: this function's caller upholds both pointer contracts.
    unsafe { get_state_json(handle, state_hash, true) }
}

/// Returns all states as an ordered JSON array.
///
/// # Safety
/// `handle` must remain valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_list_json(handle: *mut StateStore) -> *mut c_char {
    match catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds the pointer contract.
        let store = unsafe { store_from_handle(handle) }?;
        let states = store.list_states().map_err(|error| error.to_string())?;
        serde_json::to_string(&states).map_err(|error| error.to_string())
    })) {
        Ok(Ok(value)) => owned_string(value),
        Ok(Err(error)) => {
            set_error(error);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic caught while listing states");
            ptr::null_mut()
        }
    }
}

/// Returns the state count, or -1 on error.
///
/// # Safety
/// `handle` must remain valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_count(handle: *mut StateStore) -> i64 {
    match catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds the pointer contract.
        unsafe { store_from_handle(handle) }?.count().map_err(|error| error.to_string())
    })) {
        Ok(Ok(value)) => i64::try_from(value).unwrap_or(i64::MAX),
        Ok(Err(error)) => {
            set_error(error);
            -1
        }
        Err(_) => {
            set_error("panic caught while counting states");
            -1
        }
    }
}

/// Returns an allocated copy of the calling thread's last FFI error.
#[unsafe(no_mangle)]
pub extern "C" fn eira_stated_last_error() -> *mut c_char {
    LAST_ERROR.with(|slot| owned_string(slot.borrow().clone()))
}

/// Releases a string returned by an eira-stated FFI function.
///
/// # Safety
/// `pointer` must be null or a pointer returned exactly once by this library.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_free_string(pointer: *mut c_char) {
    if !pointer.is_null() {
        // SAFETY: this function's caller upholds the allocation contract.
        drop(unsafe { CString::from_raw(pointer) });
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn eira_stated_invalid_argument_code() -> i32 {
    EIRA_INVALID_ARGUMENT
}
