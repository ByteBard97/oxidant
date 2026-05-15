let i_int = i as u64;
let s = format!("{:x}", i_int);
if s.len() == 1 {
    return format!("0{}", s);
}
let js_start = (s.len() as isize - 2).max(0) as usize;
let js_end = 2_usize;
let (start, end) = if js_start > js_end {
    (js_end, js_start.min(s.len()))
} else {
    (js_start, js_end.min(s.len()))
};
s[start..end].to_string()