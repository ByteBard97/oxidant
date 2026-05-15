
if self.user_data.is_null() {
    String::from("null")
} else {
    self.user_data.to_string()
}