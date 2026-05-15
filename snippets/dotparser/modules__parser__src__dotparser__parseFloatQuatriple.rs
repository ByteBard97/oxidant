let s = str.as_str().unwrap_or("");
let p: Vec<&str> = s.split(',').collect();
let parse = |i: usize| -> f64 {
    p.get(i).and_then(|v| v.trim().parse::<f64>().ok()).unwrap_or(0.0)
};
serde_json::json!([parse(0), parse(1), parse(2), parse(3)])