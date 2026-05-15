let graph_ref = self.graph.borrow();
let geom_graph_ref = crate::geom_graph::GeomGraph::new(self.graph.clone());
let rrect_ref = geom_graph_ref.rrect.borrow();
let bb_ref = rrect_ref.bounding_box_.borrow();

let left = bb_ref.left_;
let top = bb_ref.top_;
let width = bb_ref.right_ - bb_ref.left_;
let height = bb_ref.top_ - bb_ref.bottom_;

serde_json::json!({
    "left": left,
    "top": -top,
    "width": width,
    "height": height,
    "right": left + width,
    "bottom": -top + height,
    "x": left,
    "y": -top
})