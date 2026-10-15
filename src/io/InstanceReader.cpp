#include "InstanceReader.h"
#include "Json.h"
#include "utils/Logger.h"
#include <cmath>
#include <limits>
#include <filesystem>
#include <stdexcept>
#include <vector>

#ifndef CGSHOP_PROJECT_SOURCE_DIR
#define CGSHOP_PROJECT_SOURCE_DIR "."
#endif

namespace cgshop2027 {
namespace {
std::string resolveInputPath(const std::string& input) {
  if (input.empty()) {
    return input;
  }

  const std::filesystem::path provided(input);
  if (provided.is_absolute()) {
    return provided.string();
  }

  const std::filesystem::path projectRoot(CGSHOP_PROJECT_SOURCE_DIR);
  std::vector<std::filesystem::path> candidates;
  candidates.push_back(std::filesystem::current_path() / provided);
  candidates.push_back(projectRoot / provided);
  candidates.push_back(projectRoot / "data" / provided);
  candidates.push_back(projectRoot / "data" / "test" / provided);

  for (auto dir = std::filesystem::current_path(); ; dir = dir.parent_path()) {
    candidates.push_back(dir / provided);
    if (dir == dir.parent_path()) {
      break;
    }
  }

  for (const auto& candidate : candidates) {
    std::error_code ec;
    const auto resolved = std::filesystem::weakly_canonical(candidate, ec);
    if (!ec && std::filesystem::exists(resolved) &&
        std::filesystem::is_regular_file(resolved)) {
      return resolved.string();
    }
  }

  return input;
}

std::vector<Point> polygon(const json::Value& v) {
  const auto& xValue = v.at("x");
  const auto& yValue = v.at("y");
  if (xValue.type != json::Value::ARRAY || yValue.type != json::Value::ARRAY) {
    throw std::runtime_error("polygon coordinates must be arrays");
  }
  const auto& x = xValue.array;
  const auto& y = yValue.array;
  if (x.size() != y.size()) throw std::runtime_error("x/y lengths differ");
  std::vector<Point> result;
  result.reserve(x.size());
  for (size_t i = 0; i < x.size(); ++i) {
    result.push_back({json::integer(x[i], "polygon x coordinate"),
                      json::integer(y[i], "polygon y coordinate")});
  }
  return result;
}
Point point(const json::Value& v) {
  if (v.type != json::Value::ARRAY || v.array.size() != 2U) {
    throw std::runtime_error("cutter_center must be an array of exactly two coordinates");
  }
  return {json::integer(v.array[0], "cutter_center x coordinate"),
          json::integer(v.array[1], "cutter_center y coordinate")};
}
}
std::unique_ptr<Problem> InstanceReader::readInstance(const std::string& f) {
  LogScope scope("reader", "read instance");
  const std::string resolved = resolveInputPath(f);
  Logger::instance().info("reader", "loading input=" + resolved);
  auto root = json::parseFile(resolved);
  if (root.type != json::Value::OBJECT) {
    throw std::runtime_error("instance JSON root must be an object");
  }
  auto p = std::make_unique<Problem>();
  const auto& contentType = root.at("content_type");
  const auto& instanceUid = root.at("instance_uid");
  if (contentType.type != json::Value::STRING ||
      contentType.string != "CGSHOP2027_Instance") {
    throw std::runtime_error("unsupported instance content_type");
  }
  if (instanceUid.type != json::Value::STRING) {
    throw std::runtime_error("instance_uid must be a string");
  }
  p->contentType = contentType.string;
  p->instanceUid = instanceUid.string;
  const auto& region = root.at("region_to_cover");
  p->outerBoundary = polygon(region.at("outer_boundary"));
  const auto& holes = region.at("inner_boundaries");
  if (holes.type != json::Value::ARRAY) {
    throw std::runtime_error("inner_boundaries must be an array");
  }
  for (const auto& hole : holes.array) p->innerBoundaries.push_back(polygon(hole));
  p->cutter = polygon(root.at("cutter"));
  p->cutterCenter = point(root.at("cutter_center"));
  const auto& cutter_count = root.at("number_of_cutters");
  if (cutter_count.type != json::Value::NUMBER ||
      cutter_count.number < 1.0 ||
      cutter_count.number > static_cast<double>(std::numeric_limits<int>::max()) ||
      std::floor(cutter_count.number) != cutter_count.number) {
    throw std::runtime_error("number_of_cutters must be a positive integer");
  }
  p->numberOfCutters = json::integer(cutter_count, "number_of_cutters");
  std::string error;
  if (!p->validate(&error)) throw std::runtime_error("invalid instance: " + error);
  Logger::instance().info(
      "reader", "loaded uid=" + p->instanceUid +
                    " region_cells=" + std::to_string(p->regionArea()) +
                    " cutters=" + std::to_string(p->numberOfCutters));
  return p;
}
bool InstanceReader::validateFormat(const std::string& f) {
  try {
    readInstance(f);
    return true;
  } catch (const std::exception&) {
    return false;
  }
}
std::string InstanceReader::getFormatInfo(){return "CG:SHOP JSON instance: content_type, instance_uid, region_to_cover, cutter, cutter_center, number_of_cutters";}
}
