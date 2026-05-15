
let mut arr = arr;
if let serde_json::Value::Array(ref mut arr_vec) = arr {
    if let Some(index) = arr_vec.iter().position(|item| item == &obj) {
        arr_vec.remove(index);
    }
}