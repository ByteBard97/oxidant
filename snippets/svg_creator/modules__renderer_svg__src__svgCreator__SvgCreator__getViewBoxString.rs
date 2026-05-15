let width = bbox["width"].as_f64().unwrap_or(0.0);
let height = bbox["height"].as_f64().unwrap_or(0.0);
format!("0 0 {} {}", width, height)