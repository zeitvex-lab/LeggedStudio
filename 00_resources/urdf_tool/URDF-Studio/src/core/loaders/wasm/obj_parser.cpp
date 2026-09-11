#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

struct Vertex {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  float r = 1.0f;
  float g = 1.0f;
  float b = 1.0f;
  bool hasColor = false;
};

struct Vec2 {
  float x = 0.0f;
  float y = 0.0f;
};

struct Vec3 {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
};

struct FaceRef {
  int vertex = 0;
  int uv = 0;
  int normal = 0;
  bool hasUv = false;
  bool hasNormal = false;
};

struct Material {
  std::string name;
  bool flatShading = false;
  uint32_t runId = 0;
};

struct Group {
  uint32_t start = 0;
  uint32_t count = 0;
  uint32_t materialIndex = 0;
};

enum class ChildKind : uint8_t {
  Mesh = 0,
  LineSegments = 1,
  Points = 2,
};

struct Child {
  std::string name;
  ChildKind kind = ChildKind::Mesh;
  std::vector<float> positions;
  std::vector<float> normals;
  std::vector<float> uvs;
  std::vector<float> colors;
  bool hasAnyNormal = false;
  bool hasMissingNormal = false;
  bool hasAnyUv = false;
  bool hasMissingUv = false;
  bool hasAnyColor = false;
  std::vector<Material> materials;
  std::vector<Group> groups;
};

struct ParseState {
  std::vector<Vertex> vertices;
  std::vector<Vec2> uvs;
  std::vector<Vec3> normals;
  std::vector<std::string> materialLibraries;
  std::unordered_set<std::string> materialLibrarySet;
  std::vector<Child> children;
  Child current;
  std::string currentObjectName;
  std::string currentMaterialName;
  uint32_t currentMaterialRunId = 0;
  bool currentSmooth = true;
  bool currentMaterialActive = false;
  bool currentMaterialSmooth = true;
  bool currentObjectFromDeclaration = false;
};

std::string errorMessage;

struct BinaryWriter {
  uint8_t* data = nullptr;
  uint32_t size = 0;
  uint32_t capacity = 0;
  bool failed = false;

  explicit BinaryWriter(uint32_t initialCapacity = 0) {
    if (initialCapacity > 0) {
      reserve(initialCapacity);
    }
  }

  ~BinaryWriter() {
    if (data != nullptr) {
      std::free(data);
    }
  }

  bool reserve(uint32_t nextCapacity) {
    if (failed || nextCapacity <= capacity) {
      return !failed;
    }

    void* nextData = std::realloc(data, nextCapacity);
    if (nextData == nullptr) {
      failed = true;
      errorMessage = "Failed to allocate OBJ parser result buffer.";
      return false;
    }

    data = static_cast<uint8_t*>(nextData);
    capacity = nextCapacity;
    return true;
  }

  bool ensure(uint32_t extraBytes) {
    if (failed) {
      return false;
    }
    if (extraBytes > std::numeric_limits<uint32_t>::max() - size) {
      failed = true;
      errorMessage = "OBJ parser result buffer exceeds supported size.";
      return false;
    }

    const uint32_t required = size + extraBytes;
    if (required <= capacity) {
      return true;
    }

    uint32_t nextCapacity = capacity == 0 ? 4096u : capacity;
    while (nextCapacity < required) {
      if (nextCapacity > std::numeric_limits<uint32_t>::max() / 2u) {
        nextCapacity = required;
        break;
      }
      nextCapacity *= 2u;
    }
    return reserve(nextCapacity);
  }

  void append(const void* source, uint32_t byteLength) {
    if (!ensure(byteLength)) {
      return;
    }
    std::memcpy(data + size, source, byteLength);
    size += byteLength;
  }

  void align4() {
    while ((size & 3u) != 0u) {
      u8(0);
    }
  }

  void u8(uint8_t value) {
    append(&value, 1);
  }

  void u32(uint32_t value) {
    const uint8_t raw[4] = {
      static_cast<uint8_t>(value & 0xffu),
      static_cast<uint8_t>((value >> 8u) & 0xffu),
      static_cast<uint8_t>((value >> 16u) & 0xffu),
      static_cast<uint8_t>((value >> 24u) & 0xffu),
    };
    append(raw, sizeof(raw));
  }

  void string(const std::string& value) {
    u32(static_cast<uint32_t>(value.size()));
    append(value.data(), static_cast<uint32_t>(value.size()));
  }

  void floatArray(const std::vector<float>& values) {
    align4();
    const auto* raw = reinterpret_cast<const uint8_t*>(values.data());
    append(raw, static_cast<uint32_t>(values.size() * sizeof(float)));
  }

  uint8_t* release(uint32_t& releasedSize) {
    releasedSize = size;
    uint8_t* released = data;
    data = nullptr;
    size = 0;
    capacity = 0;
    return released;
  }
};

uint8_t* resultPtr = nullptr;
uint32_t resultSize = 0;

const char* skipWhitespace(const char* cursor, const char* end) {
  while (cursor < end && (*cursor == ' ' || *cursor == '\t')) {
    ++cursor;
  }
  return cursor;
}

const char* trimRight(const char* start, const char* end) {
  while (end > start && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r')) {
    --end;
  }
  return end;
}

bool isTokenBoundary(const char* cursor, const char* end) {
  return cursor >= end || *cursor == ' ' || *cursor == '\t' || *cursor == '\r';
}

bool lineToken(const char*& cursor, const char* end, const char* token) {
  const char* start = cursor;
  while (*token != '\0') {
    if (cursor >= end || *cursor != *token) {
      cursor = start;
      return false;
    }
    ++cursor;
    ++token;
  }
  if (!isTokenBoundary(cursor, end)) {
    cursor = start;
    return false;
  }
  cursor = skipWhitespace(cursor, end);
  return true;
}

std::string readRest(const char* cursor, const char* end) {
  cursor = skipWhitespace(cursor, end);
  end = trimRight(cursor, end);
  return cursor < end ? std::string(cursor, end) : std::string();
}

bool parseDouble(const char*& cursor, const char* end, double& out) {
  cursor = skipWhitespace(cursor, end);
  if (cursor >= end) {
    return false;
  }

  double sign = 1.0;
  if (*cursor == '+' || *cursor == '-') {
    if (*cursor == '-') {
      sign = -1.0;
    }
    ++cursor;
  }

  bool hasDigits = false;
  double value = 0.0;
  while (cursor < end && *cursor >= '0' && *cursor <= '9') {
    hasDigits = true;
    value = value * 10.0 + static_cast<double>(*cursor - '0');
    ++cursor;
  }

  if (cursor < end && *cursor == '.') {
    ++cursor;
    double scale = 0.1;
    while (cursor < end && *cursor >= '0' && *cursor <= '9') {
      hasDigits = true;
      value += static_cast<double>(*cursor - '0') * scale;
      scale *= 0.1;
      ++cursor;
    }
  }

  if (!hasDigits) {
    return false;
  }

  int exponent = 0;
  int exponentSign = 1;
  if (cursor < end && (*cursor == 'e' || *cursor == 'E')) {
    const char* exponentStart = cursor;
    ++cursor;
    if (cursor < end && (*cursor == '+' || *cursor == '-')) {
      if (*cursor == '-') {
        exponentSign = -1;
      }
      ++cursor;
    }

    bool hasExponentDigits = false;
    while (cursor < end && *cursor >= '0' && *cursor <= '9') {
      hasExponentDigits = true;
      exponent = exponent * 10 + (*cursor - '0');
      ++cursor;
    }

    if (!hasExponentDigits) {
      cursor = exponentStart;
    } else if (exponent != 0) {
      value *= std::pow(10.0, static_cast<double>(exponentSign * exponent));
    }
  }

  out = sign * value;
  return true;
}

bool parseFloat(const char*& cursor, const char* end, float& out) {
  double value = 0.0;
  if (!parseDouble(cursor, end, value)) {
    return false;
  }
  out = static_cast<float>(value);
  return true;
}

float srgbToLinear(float value) {
  if (!std::isfinite(value)) {
    return 0.0f;
  }
  value = std::max(0.0f, std::min(1.0f, value));
  if (value <= 0.04045f) {
    return value / 12.92f;
  }
  return std::pow((value + 0.055f) / 1.055f, 2.4f);
}

bool parseInt(const char*& cursor, const char* end, int& out) {
  if (cursor >= end) {
    return false;
  }

  int sign = 1;
  if (*cursor == '+' || *cursor == '-') {
    if (*cursor == '-') {
      sign = -1;
    }
    ++cursor;
  }

  bool hasDigits = false;
  int value = 0;
  while (cursor < end && *cursor >= '0' && *cursor <= '9') {
    hasDigits = true;
    value = value * 10 + (*cursor - '0');
    ++cursor;
  }

  if (!hasDigits) {
    return false;
  }

  out = sign * value;
  return true;
}

int resolveIndex(int rawIndex, int count) {
  if (rawIndex > 0) {
    return rawIndex - 1;
  }
  if (rawIndex < 0) {
    return count + rawIndex;
  }
  return -1;
}

uint32_t currentVertexCount(const Child& child) {
  return static_cast<uint32_t>(child.positions.size() / 3);
}

bool currentFlatShading(const ParseState& state) {
  return !(state.currentMaterialActive ? state.currentMaterialSmooth : state.currentSmooth);
}

uint32_t ensureMaterial(Child& child, const std::string& name, bool flatShading, uint32_t runId) {
  const std::string materialName = name;

  if (!child.materials.empty()) {
    Material& lastMaterial = child.materials.back();
    if (lastMaterial.runId == runId) {
      lastMaterial.name = materialName;
      lastMaterial.flatShading = flatShading;
      return static_cast<uint32_t>(child.materials.size() - 1);
    }
  }

  const auto materialIndex = static_cast<uint32_t>(child.materials.size());
  child.materials.push_back({materialName, flatShading, runId});
  return materialIndex;
}

void ensureGroup(Child& child, uint32_t materialIndex) {
  if (!child.groups.empty() && child.groups.back().materialIndex == materialIndex) {
    return;
  }

  child.groups.push_back({
    currentVertexCount(child),
    0,
    materialIndex,
  });
}

bool appendFaceVertex(ParseState& state, Child& child, const FaceRef& ref, std::string& error) {
  const int vertexIndex = resolveIndex(ref.vertex, static_cast<int>(state.vertices.size()));
  if (vertexIndex < 0 || vertexIndex >= static_cast<int>(state.vertices.size())) {
    error = "OBJ face references a vertex outside the available vertex range.";
    return false;
  }

  const Vertex& vertex = state.vertices[static_cast<size_t>(vertexIndex)];
  child.positions.push_back(static_cast<float>(vertex.x));
  child.positions.push_back(static_cast<float>(vertex.y));
  child.positions.push_back(static_cast<float>(vertex.z));

  if (ref.hasNormal) {
    const int normalIndex = resolveIndex(ref.normal, static_cast<int>(state.normals.size()));
    if (normalIndex < 0 || normalIndex >= static_cast<int>(state.normals.size())) {
      error = "OBJ face references a normal outside the available normal range.";
      return false;
    }
    const Vec3& normal = state.normals[static_cast<size_t>(normalIndex)];
    child.normals.push_back(normal.x);
    child.normals.push_back(normal.y);
    child.normals.push_back(normal.z);
    child.hasAnyNormal = true;
  } else {
    child.normals.push_back(0.0f);
    child.normals.push_back(0.0f);
    child.normals.push_back(0.0f);
    child.hasMissingNormal = true;
  }

  if (ref.hasUv) {
    const int uvIndex = resolveIndex(ref.uv, static_cast<int>(state.uvs.size()));
    if (uvIndex < 0 || uvIndex >= static_cast<int>(state.uvs.size())) {
      error = "OBJ face references a texture coordinate outside the available UV range.";
      return false;
    }
    const Vec2& uv = state.uvs[static_cast<size_t>(uvIndex)];
    child.uvs.push_back(uv.x);
    child.uvs.push_back(uv.y);
    child.hasAnyUv = true;
  } else {
    child.uvs.push_back(0.0f);
    child.uvs.push_back(0.0f);
    child.hasMissingUv = true;
  }

  if (vertex.hasColor) {
    child.hasAnyColor = true;
  }
  child.colors.push_back(vertex.r);
  child.colors.push_back(vertex.g);
  child.colors.push_back(vertex.b);

  return true;
}

bool resolveVertex(const ParseState& state, const FaceRef& ref, const Vertex*& vertex, std::string& error) {
  const int vertexIndex = resolveIndex(ref.vertex, static_cast<int>(state.vertices.size()));
  if (vertexIndex < 0 || vertexIndex >= static_cast<int>(state.vertices.size())) {
    error = "OBJ face references a vertex outside the available vertex range.";
    return false;
  }

  vertex = &state.vertices[static_cast<size_t>(vertexIndex)];
  return true;
}

Vec3 computeFaceNormal(const Vertex& a, const Vertex& b, const Vertex& c) {
  const double cbx = c.x - b.x;
  const double cby = c.y - b.y;
  const double cbz = c.z - b.z;
  const double abx = a.x - b.x;
  const double aby = a.y - b.y;
  const double abz = a.z - b.z;
  double nx = cby * abz - cbz * aby;
  double ny = cbz * abx - cbx * abz;
  double nz = cbx * aby - cby * abx;
  const double length = std::sqrt(nx * nx + ny * ny + nz * nz);
  Vec3 normal;
  if (length > 0.0) {
    normal.x = static_cast<float>(nx / length);
    normal.y = static_cast<float>(ny / length);
    normal.z = static_cast<float>(nz / length);
  } else {
    normal.x = 0.0f;
    normal.y = 0.0f;
    normal.z = 0.0f;
  }
  return normal;
}

bool appendFaceVertexWithNormal(
  ParseState& state,
  Child& child,
  const FaceRef& ref,
  const Vec3& generatedNormal,
  std::string& error
) {
  const Vertex* vertex = nullptr;
  if (!resolveVertex(state, ref, vertex, error)) {
    return false;
  }

  child.positions.push_back(static_cast<float>(vertex->x));
  child.positions.push_back(static_cast<float>(vertex->y));
  child.positions.push_back(static_cast<float>(vertex->z));
  child.normals.push_back(generatedNormal.x);
  child.normals.push_back(generatedNormal.y);
  child.normals.push_back(generatedNormal.z);
  child.hasAnyNormal = true;

  if (ref.hasUv) {
    const int uvIndex = resolveIndex(ref.uv, static_cast<int>(state.uvs.size()));
    if (uvIndex < 0 || uvIndex >= static_cast<int>(state.uvs.size())) {
      error = "OBJ face references a texture coordinate outside the available UV range.";
      return false;
    }
    const Vec2& uv = state.uvs[static_cast<size_t>(uvIndex)];
    child.uvs.push_back(uv.x);
    child.uvs.push_back(uv.y);
    child.hasAnyUv = true;
  } else {
    child.uvs.push_back(0.0f);
    child.uvs.push_back(0.0f);
    child.hasMissingUv = true;
  }

  if (vertex->hasColor) {
    child.hasAnyColor = true;
  }
  child.colors.push_back(vertex->r);
  child.colors.push_back(vertex->g);
  child.colors.push_back(vertex->b);

  return true;
}

bool appendPositionVertex(ParseState& state, Child& child, const FaceRef& ref, bool includeUv, std::string& error) {
  const int vertexIndex = resolveIndex(ref.vertex, static_cast<int>(state.vertices.size()));
  if (vertexIndex < 0 || vertexIndex >= static_cast<int>(state.vertices.size())) {
    error = "OBJ primitive references a vertex outside the available vertex range.";
    return false;
  }

  const Vertex& vertex = state.vertices[static_cast<size_t>(vertexIndex)];
  child.positions.push_back(static_cast<float>(vertex.x));
  child.positions.push_back(static_cast<float>(vertex.y));
  child.positions.push_back(static_cast<float>(vertex.z));

  if (includeUv) {
    if (ref.hasUv) {
      const int uvIndex = resolveIndex(ref.uv, static_cast<int>(state.uvs.size()));
      if (uvIndex < 0 || uvIndex >= static_cast<int>(state.uvs.size())) {
        error = "OBJ primitive references a texture coordinate outside the available UV range.";
        return false;
      }
      const Vec2& uv = state.uvs[static_cast<size_t>(uvIndex)];
      child.uvs.push_back(uv.x);
      child.uvs.push_back(uv.y);
      child.hasAnyUv = true;
    } else {
      child.uvs.push_back(0.0f);
      child.uvs.push_back(0.0f);
      child.hasMissingUv = true;
    }
  }

  if (vertex.hasColor) {
    child.hasAnyColor = true;
  }
  child.colors.push_back(vertex.r);
  child.colors.push_back(vertex.g);
  child.colors.push_back(vertex.b);

  return true;
}

void finalizeCurrentChild(ParseState& state) {
  if (state.current.positions.empty()) {
    state.current.name = state.currentObjectName;
    return;
  }

  if (state.current.materials.empty()) {
    ensureMaterial(state.current, "", currentFlatShading(state), state.currentMaterialRunId);
  }
  state.children.push_back(std::move(state.current));
  state.current = Child();
  state.current.name = state.currentObjectName;
}

void ensureCurrentChildKind(ParseState& state, ChildKind kind) {
  if (state.current.positions.empty()) {
    state.current.name = state.currentObjectName;
    state.current.kind = kind;
    return;
  }

  if (state.current.kind == kind) {
    return;
  }

  finalizeCurrentChild(state);
  state.current.name = state.currentObjectName;
  state.current.kind = kind;
}

bool appendTriangle(ParseState& state, const FaceRef& a, const FaceRef& b, const FaceRef& c) {
  ensureCurrentChildKind(state, ChildKind::Mesh);
  Child& child = state.current;
  std::string error;
  const uint32_t materialIndex = ensureMaterial(
    child,
    state.currentMaterialName,
    currentFlatShading(state),
    state.currentMaterialRunId
  );
  ensureGroup(child, materialIndex);

  if (a.hasNormal && b.hasNormal && c.hasNormal) {
    if (!appendFaceVertex(state, child, a, error) ||
        !appendFaceVertex(state, child, b, error) ||
        !appendFaceVertex(state, child, c, error)) {
      errorMessage = error;
      return false;
    }
  } else {
    const Vertex* vertexA = nullptr;
    const Vertex* vertexB = nullptr;
    const Vertex* vertexC = nullptr;
    if (!resolveVertex(state, a, vertexA, error) ||
        !resolveVertex(state, b, vertexB, error) ||
        !resolveVertex(state, c, vertexC, error)) {
      errorMessage = error;
      return false;
    }

    const Vec3 generatedNormal = computeFaceNormal(*vertexA, *vertexB, *vertexC);
    if (!appendFaceVertexWithNormal(state, child, a, generatedNormal, error) ||
        !appendFaceVertexWithNormal(state, child, b, generatedNormal, error) ||
        !appendFaceVertexWithNormal(state, child, c, generatedNormal, error)) {
      errorMessage = error;
      return false;
    }
  }

  child.groups.back().count += 3;
  return true;
}

bool appendPointPrimitive(ParseState& state, const std::vector<FaceRef>& refs) {
  ensureCurrentChildKind(state, ChildKind::Points);
  Child& child = state.current;
  std::string error;
  const uint32_t materialIndex = ensureMaterial(
    child,
    state.currentMaterialName,
    currentFlatShading(state),
    state.currentMaterialRunId
  );
  ensureGroup(child, materialIndex);
  for (const FaceRef& ref : refs) {
    if (!appendPositionVertex(state, child, ref, false, error)) {
      errorMessage = error;
      return false;
    }
  }
  child.groups.back().count += static_cast<uint32_t>(refs.size());
  return true;
}

bool appendLineVertex(ParseState& state, const FaceRef& ref) {
  ensureCurrentChildKind(state, ChildKind::LineSegments);
  Child& child = state.current;
  std::string error;
  const uint32_t materialIndex = ensureMaterial(
    child,
    state.currentMaterialName,
    currentFlatShading(state),
    state.currentMaterialRunId
  );
  ensureGroup(child, materialIndex);
  if (!appendPositionVertex(state, child, ref, true, error)) {
    errorMessage = error;
    return false;
  }
  child.groups.back().count += 1;
  return true;
}

void appendVertexOnlyPointCloud(ParseState& state) {
  if (!state.children.empty() || !state.current.positions.empty() || state.vertices.empty()) {
    return;
  }

  Child child;
  child.name = state.currentObjectName;
  child.kind = ChildKind::Points;
  ensureMaterial(
    child,
    state.currentMaterialActive ? state.currentMaterialName : "",
    currentFlatShading(state),
    state.currentMaterialRunId
  );
  child.groups.push_back({0, static_cast<uint32_t>(state.vertices.size()), 0});
  for (const Vertex& vertex : state.vertices) {
    child.positions.push_back(static_cast<float>(vertex.x));
    child.positions.push_back(static_cast<float>(vertex.y));
    child.positions.push_back(static_cast<float>(vertex.z));
    if (vertex.hasColor) {
      child.hasAnyColor = true;
    }
    child.colors.push_back(vertex.r);
    child.colors.push_back(vertex.g);
    child.colors.push_back(vertex.b);
  }

  state.children.push_back(std::move(child));
}

bool parseFaceRef(const char*& cursor, const char* end, FaceRef& ref) {
  cursor = skipWhitespace(cursor, end);
  if (cursor >= end) {
    return false;
  }

  if (!parseInt(cursor, end, ref.vertex)) {
    return false;
  }

  if (cursor >= end || *cursor != '/') {
    return true;
  }

  ++cursor;
  if (cursor < end && *cursor != '/') {
    ref.hasUv = true;
    if (!parseInt(cursor, end, ref.uv)) {
      return false;
    }
  }

  if (cursor >= end || *cursor != '/') {
    return true;
  }

  ++cursor;
  if (cursor < end && *cursor != ' ' && *cursor != '\t' && *cursor != '\r') {
    ref.hasNormal = true;
    if (!parseInt(cursor, end, ref.normal)) {
      return false;
    }
  }

  return true;
}

void setCurrentObjectName(ParseState& state, const std::string& name) {
  if (name.empty()) {
    return;
  }

  if (!state.currentObjectFromDeclaration) {
    state.currentObjectFromDeclaration = true;
    state.currentObjectName = name;
    state.current.name = name;
    return;
  }

  const bool shouldInheritMaterial = state.currentMaterialActive && !state.currentMaterialName.empty();
  const std::string inheritedMaterialName = shouldInheritMaterial ? state.currentMaterialName : std::string();
  const bool inheritedMaterialSmooth = shouldInheritMaterial ? state.currentMaterialSmooth : true;

  finalizeCurrentChild(state);
  state.currentObjectName = name;
  state.current.name = name;
  state.currentSmooth = true;
  state.currentMaterialName = inheritedMaterialName;
  state.currentMaterialSmooth = inheritedMaterialSmooth;
  state.currentMaterialActive = shouldInheritMaterial;
}

void addMaterialLibrary(ParseState& state, const std::string& value) {
  const char* cursor = value.data();
  const char* end = value.data() + value.size();
  while (cursor < end) {
    cursor = skipWhitespace(cursor, end);
    const char* start = cursor;
    while (cursor < end && *cursor != ' ' && *cursor != '\t' && *cursor != '\r') {
      ++cursor;
    }
    if (start < cursor) {
      std::string name(start, cursor);
      if (state.materialLibrarySet.insert(name).second) {
        state.materialLibraries.push_back(std::move(name));
      }
    }
  }
}

bool parseLine(ParseState& state, const char* start, const char* end) {
  const char* cursor = skipWhitespace(start, end);
  if (cursor >= end || *cursor == '#') {
    return true;
  }

  const char* tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "v")) {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    if (!parseDouble(tokenCursor, end, x) ||
        !parseDouble(tokenCursor, end, y) ||
        !parseDouble(tokenCursor, end, z)) {
      errorMessage = "OBJ vertex line is missing xyz coordinates.";
      return false;
    }

    Vertex vertex;
    vertex.x = x;
    vertex.y = y;
    vertex.z = z;

    float r = 1.0f;
    float g = 1.0f;
    float b = 1.0f;
    const char* colorCursor = tokenCursor;
    if (parseFloat(colorCursor, end, r) &&
        parseFloat(colorCursor, end, g) &&
        parseFloat(colorCursor, end, b)) {
      vertex.r = srgbToLinear(r);
      vertex.g = srgbToLinear(g);
      vertex.b = srgbToLinear(b);
      vertex.hasColor = true;
    }

    state.vertices.push_back(vertex);
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "vn")) {
    Vec3 normal;
    if (!parseFloat(tokenCursor, end, normal.x) ||
        !parseFloat(tokenCursor, end, normal.y) ||
        !parseFloat(tokenCursor, end, normal.z)) {
      errorMessage = "OBJ normal line is missing xyz coordinates.";
      return false;
    }
    state.normals.push_back(normal);
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "vt")) {
    Vec2 uv;
    if (!parseFloat(tokenCursor, end, uv.x)) {
      errorMessage = "OBJ texture coordinate line is missing u coordinate.";
      return false;
    }
    if (!parseFloat(tokenCursor, end, uv.y)) {
      uv.y = 0.0f;
    }
    state.uvs.push_back(uv);
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "f")) {
    std::vector<FaceRef> refs;
    while (tokenCursor < end) {
      FaceRef ref;
      const char* before = tokenCursor;
      if (!parseFaceRef(tokenCursor, end, ref)) {
        if (skipWhitespace(before, end) >= end) {
          break;
        }
        errorMessage = "OBJ face line contains an invalid vertex reference.";
        return false;
      }
      refs.push_back(ref);
      tokenCursor = skipWhitespace(tokenCursor, end);
    }

    if (refs.size() < 3) {
      errorMessage = "OBJ face line must contain at least three vertices.";
      return false;
    }

    for (size_t index = 1; index + 1 < refs.size(); ++index) {
      if (!appendTriangle(state, refs[0], refs[index], refs[index + 1])) {
        return false;
      }
    }
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "l")) {
    std::vector<FaceRef> refs;
    while (tokenCursor < end) {
      FaceRef ref;
      const char* before = tokenCursor;
      if (!parseFaceRef(tokenCursor, end, ref)) {
        if (skipWhitespace(before, end) >= end) {
          break;
        }
        errorMessage = "OBJ line primitive contains an invalid vertex reference.";
        return false;
      }
      refs.push_back(ref);
      tokenCursor = skipWhitespace(tokenCursor, end);
    }

    if (refs.size() < 2) {
      errorMessage = "OBJ line primitive must contain at least two vertices.";
      return false;
    }

    for (const FaceRef& ref : refs) {
      if (!appendLineVertex(state, ref)) {
        return false;
      }
    }
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "p")) {
    std::vector<FaceRef> refs;
    while (tokenCursor < end) {
      FaceRef ref;
      const char* before = tokenCursor;
      if (!parseFaceRef(tokenCursor, end, ref)) {
        if (skipWhitespace(before, end) >= end) {
          break;
        }
        errorMessage = "OBJ point primitive contains an invalid vertex reference.";
        return false;
      }
      refs.push_back(ref);
      tokenCursor = skipWhitespace(tokenCursor, end);
    }

    if (refs.empty()) {
      errorMessage = "OBJ point primitive must contain at least one vertex.";
      return false;
    }

    return appendPointPrimitive(state, refs);
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "usemtl")) {
    const std::string materialName = readRest(tokenCursor, end);
    const bool materialSmooth = state.currentMaterialActive ? state.currentMaterialSmooth : state.currentSmooth;
    state.currentMaterialName = materialName;
    state.currentMaterialSmooth = materialSmooth;
    state.currentMaterialActive = true;
    state.currentMaterialRunId += 1;
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "mtllib")) {
    addMaterialLibrary(state, readRest(tokenCursor, end));
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "o") || lineToken(tokenCursor, end, "g")) {
    setCurrentObjectName(state, readRest(tokenCursor, end));
    return true;
  }

  tokenCursor = cursor;
  if (lineToken(tokenCursor, end, "s")) {
    const std::string value = readRest(tokenCursor, end);
    if (value.empty()) {
      state.currentSmooth = true;
    } else {
      std::string lowerValue;
      lowerValue.reserve(value.size());
      for (char ch : value) {
        lowerValue.push_back(static_cast<char>(ch >= 'A' && ch <= 'Z' ? ch + ('a' - 'A') : ch));
      }
      state.currentSmooth = lowerValue != "0" && lowerValue != "off";
    }
    if (state.currentMaterialActive) {
      state.currentMaterialSmooth = state.currentSmooth;
    }
    if (!state.current.materials.empty() &&
        state.current.materials.back().runId == state.currentMaterialRunId) {
      state.current.materials.back().flatShading = currentFlatShading(state);
    }
    return true;
  }

  return true;
}

void writeSerializedResult(const ParseState& state, BinaryWriter& writer) {
  writer.u32(0x3357504fu); // OPW3: OPW2 plus material flatShading flags.
  writer.u32(static_cast<uint32_t>(state.materialLibraries.size()));
  for (const std::string& materialLibrary : state.materialLibraries) {
    writer.string(materialLibrary);
  }

  writer.u32(static_cast<uint32_t>(state.children.size()));
  for (const Child& child : state.children) {
    writer.u8(static_cast<uint8_t>(child.kind));
    writer.string(child.name);

    writer.u32(static_cast<uint32_t>(child.materials.size()));
    for (const Material& material : child.materials) {
      writer.string(material.name);
      writer.u32(0xffffffu);
      writer.u8(0);
      writer.u8(material.flatShading ? 1 : 0);
    }

    const uint32_t vertexCount = static_cast<uint32_t>(child.positions.size() / 3);
    writer.u32(vertexCount);
    writer.floatArray(child.positions);

    const bool emitNormals = child.hasAnyNormal && !child.hasMissingNormal;
    writer.u8(emitNormals ? 1 : 0);
    if (emitNormals) {
      writer.floatArray(child.normals);
    }

    const bool emitUvs = child.hasAnyUv;
    writer.u8(emitUvs ? 1 : 0);
    if (emitUvs) {
      writer.floatArray(child.uvs);
    }

    writer.u8(child.hasAnyColor ? 1 : 0);
    if (child.hasAnyColor) {
      writer.floatArray(child.colors);
    }

    writer.u32(static_cast<uint32_t>(child.groups.size()));
    for (const Group& group : child.groups) {
      writer.u32(group.start);
      writer.u32(group.count);
      writer.u32(group.materialIndex);
    }
  }
}

} // namespace

extern "C" {

int parse_obj(const uint8_t* data, uint32_t length) {
  if (resultPtr != nullptr) {
    std::free(resultPtr);
    resultPtr = nullptr;
    resultSize = 0;
  }
  errorMessage.clear();

  ParseState state;
  const char* cursor = reinterpret_cast<const char*>(data);
  const char* end = cursor + length;
  std::string continuedLine;

  while (cursor < end) {
    const char* lineStart = cursor;
    while (cursor < end && *cursor != '\n') {
      ++cursor;
    }
    const char* lineEnd = trimRight(lineStart, cursor);
    const bool hasContinuation = lineEnd > lineStart && lineEnd[-1] == '\\';
    const char* segmentEnd = hasContinuation ? lineEnd - 1 : lineEnd;

    if (!continuedLine.empty() || hasContinuation) {
      continuedLine.append(lineStart, segmentEnd);
    }

    if (hasContinuation) {
      if (cursor < end && *cursor == '\n') {
        ++cursor;
      }
      continue;
    }

    const char* logicalLineStart = continuedLine.empty() ? lineStart : continuedLine.data();
    const char* logicalLineEnd = continuedLine.empty()
      ? lineEnd
      : continuedLine.data() + continuedLine.size();
    if (!parseLine(state, logicalLineStart, logicalLineEnd)) {
      return 0;
    }
    continuedLine.clear();
    if (cursor < end && *cursor == '\n') {
      ++cursor;
    }
  }

  if (!continuedLine.empty()) {
    if (!parseLine(state, continuedLine.data(), continuedLine.data() + continuedLine.size())) {
      return 0;
    }
  }

  finalizeCurrentChild(state);
  appendVertexOnlyPointCloud(state);

  BinaryWriter writer(length);
  writeSerializedResult(state, writer);
  if (writer.failed) {
    resultSize = 0;
    return 0;
  }
  resultPtr = writer.release(resultSize);
  if (resultPtr == nullptr || resultSize == 0) {
    errorMessage = "OBJ parser returned an empty result buffer.";
    resultPtr = nullptr;
    resultSize = 0;
    return 0;
  }
  return 1;
}

uintptr_t obj_parser_get_result_ptr() {
  return reinterpret_cast<uintptr_t>(resultPtr);
}

uint32_t obj_parser_get_result_size() {
  return resultSize;
}

uintptr_t obj_parser_get_error_ptr() {
  return reinterpret_cast<uintptr_t>(errorMessage.data());
}

uint32_t obj_parser_get_error_size() {
  return static_cast<uint32_t>(errorMessage.size());
}

void obj_parser_free_result() {
  if (resultPtr != nullptr) {
    std::free(resultPtr);
    resultPtr = nullptr;
    resultSize = 0;
  }
}

}
