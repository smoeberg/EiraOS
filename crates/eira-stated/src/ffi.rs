use crate::{StateRecord, StateStore};
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::ffi::{CStr, CString, c_char};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

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

static HANDLES: OnceLock<Mutex<HashMap<usize, Arc<StateStore>>>> = OnceLock::new();
static NEXT_HANDLE: AtomicUsize = AtomicUsize::new(1);
static STRINGS: OnceLock<Mutex<HashSet<usize>>> = OnceLock::new();

fn handles() -> &'static Mutex<HashMap<usize, Arc<StateStore>>> {
    HANDLES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn strings() -> &'static Mutex<HashSet<usize>> {
    STRINGS.get_or_init(|| Mutex::new(HashSet::new()))
}

fn register_store(store: StateStore) -> *mut StateStore {
    // Integer tokens are never dereferenced, and monotonically increasing IDs
    // prevent a closed handle from becoming valid again through allocator reuse.
    let token = NEXT_HANDLE.fetch_add(1, Ordering::Relaxed);
    if token == 0 {
        return ptr::null_mut();
    }
    handles()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .insert(token, Arc::new(store));
    token as *mut StateStore
}

fn store_from_handle(handle: *mut StateStore) -> Result<Arc<StateStore>, String> {
    if handle.is_null() {
        return Err("state-store handle is null".to_owned());
    }
    handles()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .get(&(handle as usize))
        .cloned()
        .ok_or_else(|| "state-store handle is invalid or closed".to_owned())
}

fn owned_string(value: String) -> *mut c_char {
    let Ok(value) = CString::new(value) else {
        return ptr::null_mut();
    };
    let pointer = value.into_raw();
    strings()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .insert(pointer as usize);
    pointer
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
        Ok(Ok(store)) => register_store(store),
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
    // Never allow a Rust panic to unwind across the C ABI, including drop.
    let _ = catch_unwind(AssertUnwindSafe(|| {
        if handle.is_null() {
            return;
        }
        handles()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .remove(&(handle as usize));
    }));
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
        let store = store_from_handle(handle)?;
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
        let store = store_from_handle(handle)?;
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
        let store = store_from_handle(handle)?;
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
        store_from_handle(handle)?
            .count()
            .map_err(|error| error.to_string())
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
    match catch_unwind(AssertUnwindSafe(|| {
        LAST_ERROR.with(|slot| owned_string(slot.borrow().clone()))
    })) {
        Ok(pointer) => pointer,
        Err(_) => ptr::null_mut(),
    }
}

/// Releases a string returned by an eira-stated FFI function.
///
/// # Safety
/// `pointer` must be null or a pointer returned exactly once by this library.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_stated_free_string(pointer: *mut c_char) {
    // The pointer must still be null or allocated by this library; catch_unwind
    // cannot make an arbitrary or already-freed pointer safe to dereference.
    let _ = catch_unwind(AssertUnwindSafe(|| {
        if pointer.is_null() {
            return;
        }
        let registered = strings()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .remove(&(pointer as usize));
        if registered {
            // Only pointers allocated by owned_string reach CString::from_raw.
            drop(unsafe { CString::from_raw(pointer) });
        }
    }));
}

#[unsafe(no_mangle)]
pub extern "C" fn eira_stated_invalid_argument_code() -> i32 {
    EIRA_INVALID_ARGUMENT
}


#[cfg(test)]
mod ffi_tests {
    use super::{
        eira_stated_close, eira_stated_count, eira_stated_free_string, eira_stated_last_error,
        eira_stated_open, StateStore,
    };
    use std::ffi::CString;
    use std::ptr;

    #[test]
    fn rejects_unregistered_handles_without_dereferencing() {
        let invalid = 1_usize as *mut StateStore;
        // SAFETY: unregistered tokens are checked in the registry before use.
        assert_eq!(unsafe { eira_stated_count(invalid) }, -1);
        // SAFETY: close/free ignore tokens not allocated by this library.
        unsafe {
            eira_stated_close(invalid);
            eira_stated_free_string(1_usize as *mut std::ffi::c_char);
        }
    }

    #[test]
    fn close_is_idempotent_and_stale_handles_are_rejected() {
        let path = CString::new(":memory:").unwrap();
        // SAFETY: path is a live, NUL-terminated C string for this call.
        let handle = unsafe { eira_stated_open(path.as_ptr()) };
        assert!(!handle.is_null());
        // SAFETY: handle was returned by eira_stated_open and remains open.
        assert_eq!(unsafe { eira_stated_count(handle) }, 0);
        // SAFETY: close accepts a live handle; repeated close is contained.
        unsafe {
            eira_stated_close(handle);
            eira_stated_close(handle);
        }
        // SAFETY: stale handles are rejected by the registry before access.
        assert_eq!(unsafe { eira_stated_count(handle) }, -1);
    }

    #[test]
    fn null_pointers_and_repeated_string_free_are_contained() {
        // SAFETY: null is explicitly supported by the FFI contract.
        unsafe {
            eira_stated_close(ptr::null_mut());
            eira_stated_free_string(ptr::null_mut());
        }
        let error = eira_stated_last_error();
        assert!(!error.is_null());
        // SAFETY: error is library-allocated; the second free must be ignored.
        unsafe {
            eira_stated_free_string(error);
            eira_stated_free_string(error);
        }
    }
}
