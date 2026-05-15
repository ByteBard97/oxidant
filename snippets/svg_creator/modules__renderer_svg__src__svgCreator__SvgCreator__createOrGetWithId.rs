let mut group = group;

if let Some(children) = group.get("children") {
    if let Some(array) = children.as_array() {
        for child in array {
            if child.get("id").and_then(|v| v.as_str()) == Some(id.as_str()) {
                return child.clone();
            }
        }
    }
}

let new_elem = serde_json::json!({
    "tag": tag,
    "id": id
});

if let Some(children) = group.get_mut("children") {
    if let Some(array) = children.as_array_mut() {
        array.push(new_elem.clone());
    }
} else {
    group["children"] = serde_json::json!([new_elem.clone()]);
}

new_elem