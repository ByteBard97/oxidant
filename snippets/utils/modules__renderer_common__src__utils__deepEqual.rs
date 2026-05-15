if a == b {
    return true;
}
if a.is_null() || b.is_null() {
    return false;
}
if let serde_json::Value::Array(a_arr) = &a {
    if let serde_json::Value::Array(b_arr) = &b {
        if a_arr.len() != b_arr.len() {
            return false;
        }
        for i in 0..a_arr.len() {
            if !deep_equal(a_arr[i].clone(), b_arr[i].clone()) {
                return false;
            }
        }
        return true;
    } else {
        return false;
    }
} else if b.is_array() {
    return false;
}
if let (serde_json::Value::Object(a_map), serde_json::Value::Object(b_map)) = (&a, &b) {
    let a_keys: Vec<&String> = a_map.keys().collect();
    let b_keys: Vec<&String> = b_map.keys().collect();
    if a_keys.len() != b_keys.len() {
        return false;
    }
    for key in &a_keys {
        if !b_map.contains_key(*key) {
            return false;
        }
        if !deep_equal(a_map[*key].clone(), b_map[*key].clone()) {
            return false;
        }
    }
    return true;
}
false