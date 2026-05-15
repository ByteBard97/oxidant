let mut result = Vec::new();
let mut upper = start + 1.0;
let mut lower = upper;
while lower > min {
    lower -= 1.0;
    result.push(lower);
}
while upper < max {
    result.push(upper);
    upper += 1.0;
}
serde_json::json!(result)