let mut ret = std::collections::HashMap::new();
for (i, obj) in objects.into_iter().enumerate() {
    ret.insert(obj, i as f64);
}
ret