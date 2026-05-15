
if self._graph.is_none() {
    return "no graph".to_string();
}
let json_obj = crate::dotparser::graph_to_json(self._graph.as_ref().unwrap().clone());
serde_json::to_string_pretty(&json_obj).unwrap_or_else(|_| "error serializing".to_string())