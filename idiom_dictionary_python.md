# Python → Rust Idiom Dictionary

Injected into Phase B translation prompts when source_language is "python".
Section headers must match idiom tags from detect_idioms_python.py exactly.

## list_comprehension

Python list comprehensions translate to Rust iterator chains.

**Python:**
```python
result = [x * 2 for x in items if x > 0]
```

**Rust:**
```rust
let result: Vec<_> = items.iter()
    .filter(|&&x| x > 0)
    .map(|&x| x * 2)
    .collect();
```

For dict comprehensions: `.map(|(k, v)| ...).collect::<HashMap<_, _>>()`.
For set comprehensions: `.collect::<HashSet<_>>()`.

## optional_type

Python `Optional[T]` and `T | None` both map to Rust `Option<T>`.

**Python:**
```python
def find(items: list[str], key: str) -> Optional[str]:
    return None
```

**Rust:**
```rust
fn find(items: &[String], key: &str) -> Option<String> {
    None
}
```

Use `if let Some(x) = value { ... }` instead of `if value is not None`.

## generator_function

Python generators (`yield`) become Rust `impl Iterator` types.
For simple cases, collect into a `Vec` first and return that.

**Python:**
```python
def gen_pairs(items):
    for i, item in enumerate(items):
        yield (i, item)
```

**Rust (collect approach):**
```rust
fn gen_pairs(items: &[String]) -> Vec<(usize, String)> {
    items.iter().enumerate().map(|(i, s)| (i, s.clone())).collect()
}
```

## format_string

Python f-strings translate directly to Rust `format!()`.

**Python:** `f"Hello, {name}! Count: {count:.2f}"`

**Rust:** `format!("Hello, {}! Count: {:.2}", name, count)`

Format spec mapping: `{:.2f}` → `{:.2}`, `{:>10}` → `{:>10}`.

## none_check

Python `x is None` / `x is not None` → Rust `x.is_none()` / `x.is_some()`.

**Python:**
```python
if x is None:
    return default
return x
```

**Rust:**
```rust
x.unwrap_or(default)
// or:
match x {
    None => default,
    Some(v) => v,
}
```

## isinstance_check

Python `isinstance(x, SomeClass)` usually signals a type hierarchy that should
become a Rust `enum` with `match`.

**Python:**
```python
if isinstance(shape, Circle):
    draw_circle(shape)
elif isinstance(shape, Rect):
    draw_rect(shape)
```

**Rust:**
```rust
match shape {
    Shape::Circle(c) => draw_circle(c),
    Shape::Rect(r) => draw_rect(r),
}
```

## multiple_return

Python functions returning `tuple[T, U]` become Rust functions returning `(T, U)`.

**Python:** `def split(s: str) -> tuple[list[str], float]: ...`

**Rust:** `fn split(s: &str) -> (Vec<String>, f64) { ... }`

Destructure with `let (lines, size) = split(s);`.

## svgwrite_buffer

`svgwrite.Drawing` and similar DOM-like SVG builders → accumulate into a `String`.
Use `buf.push_str(...)` to append SVG tag strings.

**Python:**
```python
dwg = svgwrite.Drawing()
dwg.add(dwg.text("Hello", insert=(10, 20)))
return dwg.tostring()
```

**Rust:**
```rust
let mut buf = String::new();
buf.push_str(r#"<text x="10" y="20">Hello</text>"#);
buf
```

## shapely_geometry

Shapely geometry types and operations translate to the `geo` crate.

**Type mapping:**

| Shapely | Rust (`geo` crate) |
|---------|-------------------|
| `Polygon` | `geo::Polygon<f64>` |
| `LineString` | `geo::LineString<f64>` |
| `MultiLineString` | `geo::MultiLineString<f64>` |
| `Point` | `geo::Point<f64>` |

**Construction:**

```python
poly = Polygon([(x0,y0), (x1,y1), (x2,y2)])
line = LineString([(x0,y0), (x1,y1)])
pt   = Point(x, y)
```

```rust
use geo::{Polygon, LineString, Point, coord};
let poly = Polygon::new(
    LineString::from(vec![(x0, y0), (x1, y1), (x2, y2)]),
    vec![],
);
let line = LineString::from(vec![(x0, y0), (x1, y1)]);
let pt   = Point::new(x, y);
```

**Bounds (replaces `.bounds` → `(min_x, min_y, max_x, max_y)`):**

```python
(min_x, min_y, max_x, max_y) = poly.bounds
```

```rust
use geo::BoundingRect;
let bbox = poly.bounding_rect().unwrap();
let (min_x, min_y) = (bbox.min().x, bbox.min().y);
let (max_x, max_y) = (bbox.max().x, bbox.max().y);
```

**Rotation (replaces `affinity.rotate(geom, angle_deg, origin)`):**

```python
rotated = affinity.rotate(poly, angle_deg, origin=(cx, cy))
```

```rust
use geo::{Rotate, Point};
let origin = Point::new(cx, cy);
let rotated = poly.rotate_around_point(-angle_deg, origin);
```

Note: shapely rotates counter-clockwise for positive angles; `geo::Rotate` also rotates counter-clockwise, so signs match directly.

**Intersection (replaces `.intersection(other)`):**

```python
intersection = line.intersection(poly)
if type(intersection) is MultiLineString:
    for geom in intersection.geoms:
        ...
else:
    ...  # LineString
```

```rust
use geo::algorithm::line_intersection::LineIntersection;
use geo::Intersects;
// For polygon-clip of a line, use geo::algorithm::clip::Clip:
use geo::Clip;
let clipped: geo::MultiLineString<f64> = line.clip(&poly, false);
for segment in clipped.0.iter() {
    // segment is a geo::LineString<f64>
}
```

**Checking intersection (replaces `.intersects(other)`):**

```python
if line.intersects(poly):
```

```rust
use geo::Intersects;
if line.intersects(&poly) {
```

**LineString coords iteration:**

```python
for coord in line.coords:
    x, y = coord
```

```rust
for coord in line.coords() {
    let (x, y) = (coord.x, coord.y);
}
```

**Minimum rotated rectangle (replaces `.minimum_rotated_rectangle`):**

```python
rect = poly.minimum_rotated_rectangle
rectx = rect.exterior.xy[0]
recty = rect.exterior.xy[1]
```

```rust
use geo::MinimumRotatedRect;
let rect: Option<geo::Polygon<f64>> = poly.minimum_rotated_rect();
if let Some(rect) = rect {
    let coords: Vec<_> = rect.exterior().coords().collect();
    // coords[i].x, coords[i].y
}
```

**Area:**

```python
area = poly.area
```

```rust
use geo::Area;
let area = poly.unsigned_area();
```

**Point buffer (replaces `Point(lon, lat).buffer(radius)`):**

Shapely's `.buffer()` has no direct single-call equivalent in `geo`. For the common pattern of creating a fake circular boundary around a point, use a manual approximation:

```rust
// approximate circle as N-sided polygon
fn point_buffer(lon: f64, lat: f64, radius: f64, n: usize) -> geo::Polygon<f64> {
    use std::f64::consts::TAU;
    let coords: Vec<_> = (0..=n).map(|i| {
        let angle = TAU * (i as f64) / (n as f64);
        geo::coord! { x: lon + radius * angle.cos(), y: lat + radius * angle.sin() }
    }).collect();
    geo::Polygon::new(geo::LineString::from(coords), vec![])
}
```

## drf_viewset

DRF `ModelViewSet` / `ViewSet` methods become standalone `async fn` Axum handlers.
The class itself disappears — each method becomes a free function registered on a router.

**Python:**
```python
class PlantViewSet(ModelViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer

    def list(self, request):
        qs = self.get_queryset()
        return Response(self.get_serializer(qs, many=True).data)
```

**Rust:**
```rust
pub async fn list_plants(
    State(db): State<DatabaseConnection>,
    Query(params): Query<ListParams>,
) -> Result<Json<Vec<PlantDto>>, AppError> {
    let plants = Plant::find().all(&db).await?;
    Ok(Json(plants.into_iter().map(PlantDto::from).collect()))
}
```

Router registration (one-time, outside this handler):
```rust
Router::new().route("/plants", get(list_plants).post(create_plant))
```

State is injected via `State(db): State<DatabaseConnection>` — never a global.
`AppError` is a project-level error type that implements `IntoResponse`.

## drf_action

DRF `@action(detail=True/False, methods=[...])` becomes a separate Axum handler
registered at an explicit path.

**Python:**
```python
@action(detail=True, methods=["get"])
def snapshot(self, request, pk=None):
    plant = self.get_object()
    return Response(SnapshotSerializer(plant).data)
```

**Rust:**
```rust
pub async fn plant_snapshot(
    State(db): State<DatabaseConnection>,
    Path(id): Path<i32>,
) -> Result<Json<SnapshotDto>, AppError> {
    let plant = Plant::find_by_id(id)
        .one(&db).await?
        .ok_or(AppError::NotFound)?;
    Ok(Json(SnapshotDto::from(plant)))
}
```

`detail=True` → `Path(id): Path<i32>` parameter.
`detail=False` → no path parameter; acts on the collection.

## drf_hook

DRF lifecycle hooks (`get_queryset`, `perform_create`, etc.) contain the real business
logic. Extract the body into a helper function; call it from the handler.

**Python:**
```python
def get_queryset(self):
    qs = Plant.objects.all()
    search = self.request.query_params.get("search")
    if search:
        qs = qs.filter(scientific_name__icontains=search)
    return qs

def perform_create(self, serializer):
    serializer.save(created_by=self.request.user)
```

**Rust:**
```rust
async fn build_plant_query(
    db: &DatabaseConnection,
    search: Option<&str>,
) -> Result<Vec<plant::Model>, DbErr> {
    let mut q = Plant::find();
    if let Some(s) = search {
        q = q.filter(plant::Column::ScientificName.contains(s));
    }
    q.all(db).await
}

// In the handler:
pub async fn list_plants(
    State(db): State<DatabaseConnection>,
    Query(params): Query<ListParams>,
) -> Result<Json<Vec<PlantDto>>, AppError> {
    let plants = build_plant_query(&db, params.search.as_deref()).await?;
    Ok(Json(plants.into_iter().map(PlantDto::from).collect()))
}
```

`get_object_or_404(Model, pk=pk)` →
```rust
Model::find_by_id(id).one(&db).await?.ok_or(AppError::NotFound)?
```

## drf_method_field

`SerializerMethodField` + `get_<field>` pairs and `validate_*` methods become
helper methods on the DTO struct or standalone validation functions.

**Python:**
```python
primary_image_url = serializers.SerializerMethodField()

def get_primary_image_url(self, obj):
    img = obj.images.filter(is_primary=True).first()
    return img.url if img else None

def validate_scientific_name(self, value):
    if Plant.objects.filter(scientific_name=value).exists():
        raise serializers.ValidationError("Name already taken.")
    return value
```

**Rust (computed field as method on the DTO):**
```rust
impl PlantDto {
    pub fn primary_image_url(plant: &plant::Model, images: &[image::Model]) -> Option<String> {
        images.iter().find(|i| i.is_primary).map(|i| i.url.clone())
    }
}

pub fn validate_scientific_name(name: &str) -> Result<(), AppError> {
    // called before insert; uniqueness enforced by DB constraint in practice
    Ok(())
}
```

Prefer DB-level constraints (UNIQUE index) over application-level uniqueness checks.

## django_orm_query

Django ORM queryset operations translate to SeaORM async query builder calls.
Every ORM call becomes `.await` — all handler functions must be `async fn`.

**Field lookups:**
```python
Plant.objects.filter(scientific_name__icontains=search)
Plant.objects.filter(growth_rate="slow", is_native=True)
Plant.objects.exclude(workflow_status="archived")
```
```rust
Plant::find()
    .filter(plant::Column::ScientificName.contains(search))
    .filter(plant::Column::GrowthRate.eq("slow"))
    .filter(plant::Column::IsNative.eq(true))
    .filter(plant::Column::WorkflowStatus.ne("archived"))
    .all(&db).await?
```

**Single object:**
```python
Plant.objects.get(pk=pk)          # raises if missing
Plant.objects.filter(...).first() # None if missing
```
```rust
Plant::find_by_id(id).one(&db).await?.ok_or(AppError::NotFound)?
Plant::find().filter(...).one(&db).await?   // returns Option<Model>
```

**Create / update / delete:**
```python
plant = Plant.objects.create(**data)
plant.scientific_name = "New name"; plant.save()
plant.delete()
```
```rust
let plant = plant::ActiveModel { ..data.into_active_model() }.insert(&db).await?;
let mut active: plant::ActiveModel = plant.into();
active.scientific_name = Set("New name".to_string());
active.update(&db).await?;
plant.delete(&db).await?;
```

**Relations:**
```python
Plant.objects.select_related("images")
Plant.objects.prefetch_related("distributions")
```
```rust
// Load related in a second query (SeaORM pattern):
let images = PlantImage::find()
    .filter(plant_image::Column::PlantId.eq(plant.id))
    .all(&db).await?;
```

**Counts / existence:**
```python
Plant.objects.filter(...).count()
Plant.objects.filter(...).exists()
```
```rust
Plant::find().filter(...).count(&db).await?
Plant::find().filter(...).one(&db).await?.is_some()
```

## django_choices

Django `CHOICES` constants become Rust enums with `serde` and `strum` derives.
The `(value, display)` tuple becomes the variant name (snake_case → PascalCase).

**Python:**
```python
GROWTH_RATE_CHOICES = [
    ("slow", "Slow"),
    ("moderate", "Moderate"),
    ("fast", "Fast"),
]
growth_rate = models.CharField(max_length=20, choices=GROWTH_RATE_CHOICES, blank=True)
```

**Rust:**
```rust
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize,
         strum::Display, strum::EnumString, strum::AsRefStr)]
#[serde(rename_all = "snake_case")]
#[strum(serialize_all = "snake_case")]
pub enum GrowthRate {
    Slow,
    Moderate,
    Fast,
}
```

Stored as `String` in the DB (SeaORM maps `VARCHAR` → `String`). Convert at the DTO boundary:
```rust
let rate: GrowthRate = model.growth_rate.parse().unwrap_or_default();
```

For `blank=True` / optional fields: wrap in `Option<GrowthRate>`.

## django_property

Django model `@property` methods become inherent methods on the SeaORM `Model` struct
via an `impl` block. They take `&self` and are synchronous (no DB access).

**Python:**
```python
@property
def display_name(self) -> str:
    return f"{self.common_name} ({self.scientific_name})"

@property
def is_published(self) -> bool:
    return self.workflow_status == "approved"
```

**Rust:**
```rust
impl plant::Model {
    pub fn display_name(&self) -> String {
        format!("{} ({})", self.common_name, self.scientific_name)
    }

    pub fn is_published(&self) -> bool {
        self.workflow_status.as_deref() == Some("approved")
    }
}
```

Place these in a separate `impl plant::Model` block in `src/entities/plant_ext.rs`
rather than inside the SeaORM-generated entity file (which should not be edited).

## typed_dict

Python `TypedDict` becomes a Rust `struct` (not a `HashMap`).

**Python:**
```python
class TitleBlockParams(TypedDict):
    width: float
    height: float
    title: str
```

**Rust:**
```rust
#[derive(Debug, Clone)]
struct TitleBlockParams {
    pub width: f64,
    pub height: f64,
    pub title: String,
}
```
