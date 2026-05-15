
let mut q = q;
if let serde_json::Value::Array(ref mut arr) = q {
    arr.push(serde_json::json!(i));
}