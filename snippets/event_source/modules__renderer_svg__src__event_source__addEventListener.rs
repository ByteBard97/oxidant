let mut registry = registry;
if registry.get(&r#type).map_or(true, |v| v.is_null()) {
    registry[&r#type] = serde_json::Value::Array(vec![]);
}
let arr = registry[&r#type].as_array().unwrap();
if !arr.contains(&listener) {
    registry[&r#type].as_array_mut().unwrap().push(listener);
}