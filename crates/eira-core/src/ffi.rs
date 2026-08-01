use crate::{compute_hash_from_json, validate_chain_from_json};
use std::ffi::{CStr, CString, c_char};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;

unsafe fn read_input(input: *const c_char) -> Result<String, String> {
    if input.is_null() {
        return Err("input pointer is null".to_owned());
    }
    // SAFETY: the caller promises a live, NUL-terminated C string.
    let value = unsafe { CStr::from_ptr(input) };
    value
        .to_str()
        .map(str::to_owned)
        .map_err(|error| error.to_string())
}

/// Computes the Eira SHA3-256 state hash for a UTF-8 JSON state.
///
/// # Safety
/// `json_payload` must point to a valid NUL-terminated string for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_state_compute_hash(
    json_payload: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds the pointer contract.
        let input = unsafe { read_input(json_payload) }?;
        compute_hash_from_json(&input)
    }));
    match result {
        Ok(Ok(hash)) => CString::new(hash).map_or(ptr::null_mut(), CString::into_raw),
        Ok(Err(_)) | Err(_) => ptr::null_mut(),
    }
}

/// Validates an ordered JSON array of Eira states.
///
/// Returns 1 for a valid chain, 0 for a tampered/broken chain, and -1 for
/// invalid input or a panic caught at the FFI boundary.
///
/// # Safety
/// `states_json` must point to a valid NUL-terminated string for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_state_validate_chain(states_json: *const c_char) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: this function's caller upholds the pointer contract.
        let input = unsafe { read_input(states_json) }?;
        validate_chain_from_json(&input)
    }));
    match result {
        Ok(Ok(true)) => 1,
        Ok(Ok(false)) => 0,
        Ok(Err(_)) | Err(_) => -1,
    }
}

/// Releases a string returned by `eira_state_compute_hash`.
///
/// # Safety
/// `pointer` must be null or a pointer returned exactly once by this library.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn eira_free_string(pointer: *mut c_char) {
    if !pointer.is_null() {
        // SAFETY: this function's caller upholds the allocation contract.
        drop(unsafe { CString::from_raw(pointer) });
    }
}
