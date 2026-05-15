let p: Vec<&str> = str.split(',').collect();
let x = p[0].trim().parse::<f64>().unwrap_or(f64::NAN);
let y = p[1].trim().parse::<f64>().unwrap_or(f64::NAN);
serde_json::json!([x, y])