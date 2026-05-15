let mut registry = registry;
if let Some(arr) = registry
    .get_mut(&r#type)
    .and_then(|v| v.as_array_mut())
{
    if let Some(index) = arr.iter().position(|item| item == &listener) {
        arr.remove(index);
    }
}