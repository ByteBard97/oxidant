
let dpi = 96.0;
let hit_distance = self.mouse_hit_distance.as_f64().unwrap_or(0.025);
let slack_in_points = dpi * hit_distance;
let current_scale = self._svg_creator.borrow_mut().get_scale();
slack_in_points / current_scale