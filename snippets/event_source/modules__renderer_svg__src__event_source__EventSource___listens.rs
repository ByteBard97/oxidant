let listeners_has_entry = self._listeners
    .get(&r#type)
    .and_then(|v| v.as_array())
    .map_or(false, |arr| !arr.is_empty());

let once_listeners_has_entry = self._once_listeners
    .get(&r#type)
    .and_then(|v| v.as_array())
    .map_or(false, |arr| !arr.is_empty());

listeners_has_entry || once_listeners_has_entry
