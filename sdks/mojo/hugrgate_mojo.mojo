# Mojo bindings for the HugrGate C ABI — slice 434.
#
# Design: Mojo talks to the stable C ABI (sdks/c/include/hugrgate.h)
# through `sys.ffi.external_call`.  The C client is built as a shared
# library (`libhugrgate_client.so`) and linked with `-L`/`-l`; Mojo
# owns the lifetime mapping (owned pointers <-> hg_*_free) and turns
# hg_status_t failures into Mojo `Error`s.
#
# Build (with the Mojo SDK installed):
#   gcc -std=c99 -O2 -fPIC -shared -Isdks/c/include \
#       sdks/c/src/hugrgate.c -o libhugrgate_client.so
#   mojo build sdks/mojo/hugrgate_mojo.mojo \
#       -L . -lhugrgate_client -o hugrgate_mojo
#
# NOTE: the Mojo toolchain is not installed in this environment, so
# this module is design-complete but not compile-verified here.
# tests/test_deveco_434_mojo.py checks that every FFI symbol named
# below exists in the C header it binds to.

from sys.ffi import external_call
from memory import UnsafePointer
from utils import StringRef

# --- ABI mirror -------------------------------------------------------
# These aliases must track sdks/c/include/hugrgate.h exactly.

alias hg_status_t = Int32

alias HG_OK: Int32 = 0
alias HG_ERR_INVALID_ARG: Int32 = 1
alias HG_ERR_NOMEM: Int32 = 2
alias HG_ERR_TRANSPORT: Int32 = 3
alias HG_ERR_TIMEOUT: Int32 = 4
alias HG_ERR_PROTOCOL: Int32 = 5
alias HG_ERR_SPEC: Int32 = 6
alias HG_ERR_POLICY: Int32 = 7
alias HG_ERR_BACKEND: Int32 = 8
alias HG_ERR_UNAVAILABLE: Int32 = 9
alias HG_ERR_ABSTAINED: Int32 = 10
alias HG_ERR_BAD_RESPONSE: Int32 = 11

alias HG_PROTOCOL_VERSION = "1.0"


fn _c_str(s: String) -> UnsafePointer[UInt8]:
    """Borrow a NUL-terminated view of a Mojo String's bytes."""
    return s.as_string_slice().unsafe_ptr()


fn _mojo_str(ptr: UnsafePointer[UInt8]) -> String:
    """Copy a NUL-terminated C string into an owned Mojo String."""
    return String(StringRef(ptr))


# --- raw FFI declarations (one per C ABI function) --------------------


fn hg_client_new(
    url: UnsafePointer[UInt8],
    timeout_ms: Int64,
    client_out: UnsafePointer[UnsafePointer[UInt8]],
    err_out: UnsafePointer[UnsafePointer[UInt8]],
) -> Int32:
    return external_call["hg_client_new", Int32](
        url, timeout_ms, client_out, err_out
    )


fn hg_client_free(client: UnsafePointer[UInt8]):
    external_call["hg_client_free", NoneType](client)


fn hg_client_decide(
    client: UnsafePointer[UInt8],
    spec_json: UnsafePointer[UInt8],
    state_json: UnsafePointer[UInt8],
    policy_json: UnsafePointer[UInt8],  # NULL-able: pass null_ptr()
    backend_name: UnsafePointer[UInt8],  # NULL-able: pass null_ptr()
    decision_out: UnsafePointer[UnsafePointer[UInt8]],
    err_out: UnsafePointer[UnsafePointer[UInt8]],
) -> Int32:
    return external_call["hg_client_decide", Int32](
        client, spec_json, state_json, policy_json, backend_name,
        decision_out, err_out,
    )


fn hg_decision_free(decision: UnsafePointer[UInt8]):
    external_call["hg_decision_free", NoneType](decision)


fn hg_client_protocol(
    client: UnsafePointer[UInt8],
    json_out: UnsafePointer[UnsafePointer[UInt8]],
    err_out: UnsafePointer[UnsafePointer[UInt8]],
) -> Int32:
    return external_call["hg_client_protocol", Int32](
        client, json_out, err_out
    )


fn hg_status_message(status: Int32) -> UnsafePointer[UInt8]:
    return external_call["hg_status_message", UnsafePointer[UInt8]](status)


fn hg_status_recoverable(status: Int32) -> Int32:
    return external_call["hg_status_recoverable", Int32](status)


fn hg_error_free(err: UnsafePointer[UInt8]):
    external_call["hg_error_free", NoneType](err)


fn hg_free_string(s: UnsafePointer[UInt8]):
    external_call["hg_free_string", NoneType](s)


# --- struct field accessors -------------------------------------------
# hg_error_t / hg_decision_t are plain C structs; Mojo reads them
# through UnsafePointer offsets matching the header layout.
#
#   struct hg_error    { int32 code; char *message;
#                        int32 recoverable; char *service_code; }
#   struct hg_decision { char *value_json; double probability;
#                        char *distribution_json; double uncertainty;
#                        int32 accepted; char *backend; char *model;
#                        double latency_ms; char *calibration_profile;
#                        int32 fallback_used; char *metadata_json; }
#
# Offsets below assume LP64 (8-byte pointers, 4-byte int32, 8-byte
# double); they are asserted against the header in the design doc.

alias _ERR_CODE_OFF: Int = 0
alias _ERR_MSG_OFF: Int = 8
alias _ERR_RECOV_OFF: Int = 16
alias _ERR_SVC_OFF: Int = 24

alias _DEC_VALUE_OFF: Int = 0
alias _DEC_PROB_OFF: Int = 8
alias _DEC_DIST_OFF: Int = 16
alias _DEC_UNCERT_OFF: Int = 24
alias _DEC_ACCEPT_OFF: Int = 32
alias _DEC_BACKEND_OFF: Int = 40
alias _DEC_MODEL_OFF: Int = 48
alias _DEC_LAT_OFF: Int = 56
alias _DEC_CALIB_OFF: Int = 64
alias _DEC_FALLBACK_OFF: Int = 72
alias _DEC_META_OFF: Int = 80


fn _load_ptr(base: UnsafePointer[UInt8], off: Int) -> UnsafePointer[UInt8]:
    return (base + off).bitcast[UnsafePointer[UInt8]]()[]


fn _load_i32(base: UnsafePointer[UInt8], off: Int) -> Int32:
    return (base + off).bitcast[Int32]()[]


fn _load_f64(base: UnsafePointer[UInt8], off: Int) -> Float64:
    return (base + off).bitcast[Float64]()[]


fn _raise_for_status(
    status: Int32, err_ptr: UnsafePointer[UInt8]
) raises -> None:
    """Turn a failed ABI call into a Mojo Error and free the error."""
    if err_ptr:
        var code = _load_i32(err_ptr, _ERR_CODE_OFF)
        var msg_ptr = _load_ptr(err_ptr, _ERR_MSG_OFF)
        var msg = _mojo_str(msg_ptr)
        var recov = _load_i32(err_ptr, _ERR_RECOV_OFF) != 0
        hg_error_free(err_ptr)
        # Abstention is a domain signal, not a crash: surface it as
        # an Error whose message carries the reason; callers that
        # treat abstention as control flow match on the code.
        raise Error(
            "[hg:" + String(code) + ("] " if recov else ":fatal] ") + msg
        )
    else:
        var c_msg = hg_status_message(status)
        raise Error("[hg:" + String(status) + "] " + _mojo_str(c_msg))


# --- owned wrappers ----------------------------------------------------


struct Decision(Movable):
    """Owned hg_decision_t snapshot (frees on destruction)."""

    var _ptr: UnsafePointer[UInt8]

    fn __init__(out self, ptr: UnsafePointer[UInt8]):
        self._ptr = ptr

    fn __del__(owned self):
        if self._ptr:
            hg_decision_free(self._ptr)

    fn value_json(self) -> String:
        return _mojo_str(_load_ptr(self._ptr, _DEC_VALUE_OFF))

    fn probability(self) -> Float64:
        return _load_f64(self._ptr, _DEC_PROB_OFF)

    fn distribution_json(self) -> String:
        return _mojo_str(_load_ptr(self._ptr, _DEC_DIST_OFF))

    fn backend(self) -> String:
        return _mojo_str(_load_ptr(self._ptr, _DEC_BACKEND_OFF))

    fn model(self) -> String:
        return _mojo_str(_load_ptr(self._ptr, _DEC_MODEL_OFF))

    fn metadata_json(self) -> String:
        return _mojo_str(_load_ptr(self._ptr, _DEC_META_OFF))


struct Client(Movable):
    """Owned hg_client_t handle (frees on destruction)."""

    var _ptr: UnsafePointer[UInt8]

    fn __init__(out self, url: String, timeout_ms: Int64 = 10000) raises:
        var client_ptr = UnsafePointer[UInt8]()
        var err_ptr = UnsafePointer[UInt8]()
        var client_slot = UnsafePointer.address_of(client_ptr)
        var err_slot = UnsafePointer.address_of(err_ptr)
        var st = hg_client_new(
            _c_str(url), timeout_ms, client_slot, err_slot
        )
        if st != HG_OK:
            _raise_for_status(st, err_ptr)
        self._ptr = client_ptr

    fn __del__(owned self):
        if self._ptr:
            hg_client_free(self._ptr)

    fn decide(
        self,
        spec_json: String,
        state_json: String,
        policy_json: Optional[String] = None,
        backend_name: Optional[String] = None,
    ) raises -> Decision:
        var decision_ptr = UnsafePointer[UInt8]()
        var err_ptr = UnsafePointer[UInt8]()
        var policy_c = UnsafePointer[UInt8]()
        var backend_c = UnsafePointer[UInt8]()
        # Optional values: keep owned Strings alive for the call.
        var policy_owned = policy_json.or_else("")
        var backend_owned = backend_name.or_else("")
        if policy_json:
            policy_c = _c_str(policy_owned)
        if backend_name:
            backend_c = _c_str(backend_owned)
        var st = hg_client_decide(
            self._ptr,
            _c_str(spec_json),
            _c_str(state_json),
            policy_c,
            backend_c,
            UnsafePointer.address_of(decision_ptr),
            UnsafePointer.address_of(err_ptr),
        )
        if st != HG_OK:
            _raise_for_status(st, err_ptr)
        return Decision(decision_ptr)

    fn protocol(self) raises -> String:
        var json_ptr = UnsafePointer[UInt8]()
        var err_ptr = UnsafePointer[UInt8]()
        var st = hg_client_protocol(
            self._ptr,
            UnsafePointer.address_of(json_ptr),
            UnsafePointer.address_of(err_ptr),
        )
        if st != HG_OK:
            _raise_for_status(st, err_ptr)
        var out = _mojo_str(json_ptr)
        hg_free_string(json_ptr)
        return out


fn main() raises:
    var client = Client("http://127.0.0.1:8377")
    print("protocol:", client.protocol())
    var d = client.decide(
        '{"type":"categorical","options":["a","b"]}', '{"signal":0.7}'
    )
    print("value:", d.value_json(), "p=", d.probability())
