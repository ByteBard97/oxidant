if let Some(index) = self.events.iter().position(|e| e == &event) {
    self.events = self.events.splice(index..index+1, vec![]).collect();
}