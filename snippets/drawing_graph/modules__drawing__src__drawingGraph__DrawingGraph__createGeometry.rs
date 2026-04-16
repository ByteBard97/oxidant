let geom_graph = Rc::new(RefCell::new(crate::geom_graph::GeomGraph::new(self.graph.clone())));
self.text_measure = textMeasure.clone();
let opts = serde_json::json!({
    "fontFamily": self.fontname,
    "fontSize": self.fontsize,
    "fontStyle": "normal"
});
if let Some(ref label_text) = self.label_text {
    if !label_text.is_empty() {
        let size = crate::size::Size::new((label_text.len() as f64) * 8.0 + 8.0, 20.0);
        geom_graph.borrow_mut().label_size = Some(size);
    }
}
for n in self.graph.borrow().nodes_breadth_first() {
    self.create_node_geometry(&n);
}
for e in self.graph.borrow().deep_edges() {
    self.create_edge_geometry(&e);
}
if let Some(ref rankdir) = self.rankdir {
    let ss = Rc::new(RefCell::new(crate::layout_settings::SugiyamaLayoutSettings::new()));
    ss.borrow_mut().layer_direction = rankdir.clone();
    geom_graph.borrow_mut().layout_settings = Some(ss);
}
geom_graph