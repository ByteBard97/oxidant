{
    let mut label_svg_group = labelSvgGroup;
    if let Some(children) = label_svg_group.get_mut("children") {
        if let Some(obj) = children.as_object_mut() {
            obj.remove(&attachPromptId);
        } else if let Some(arr) = children.as_array_mut() {
            if let Some(pos) = arr.iter().position(|child| {
                child.get("id").and_then(|v| v.as_str()).map(|s| s == attachPromptId)
                    .or_else(|| child.get("name").and_then(|v| v.as_str()).map(|s| s == attachPromptId))
                    .unwrap_or(false)
            }) {
                arr.remove(pos);
            }
        }
    }
}