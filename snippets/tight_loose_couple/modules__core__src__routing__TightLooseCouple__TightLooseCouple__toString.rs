
let tight_str = format!("{:?}", self.tight_poly.borrow()).chars().take(5).collect::<String>();
let loose_str = format!("{:?}", self.loose_shape.borrow()).chars().take(5).collect::<String>();
format!("{},{}", tight_str, loose_str)