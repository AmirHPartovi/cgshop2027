#include "InstanceReader.h"
#include "Json.h"
#include "utils/Logger.h"
#include <cmath>
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
  const auto& x=v.at("x").array; const auto& y=v.at("y").array;
  if(x.size()!=y.size()) throw std::runtime_error("x/y lengths differ");
  std::vector<Point> r; for(size_t i=0;i<x.size();++i) {
    if(x[i].type!=json::Value::NUMBER||y[i].type!=json::Value::NUMBER||
       std::floor(x[i].number)!=x[i].number||std::floor(y[i].number)!=y[i].number)
      throw std::runtime_error("polygon coordinates must be integers");
    r.push_back({static_cast<int>(x[i].number),static_cast<int>(y[i].number)});
  } return r;
}
Point point(const json::Value& v) {
  const auto& x=v.type==json::Value::ARRAY?v.array.at(0):v.at("x");
  const auto& y=v.type==json::Value::ARRAY?v.array.at(1):v.at("y");
  if(x.type!=json::Value::NUMBER||y.type!=json::Value::NUMBER||
     std::floor(x.number)!=x.number||std::floor(y.number)!=y.number)
    throw std::runtime_error("cutter_center coordinates must be integers");
  return {static_cast<int>(x.number),static_cast<int>(y.number)};
}
}
std::unique_ptr<Problem> InstanceReader::readInstance(const std::string& f) {
  LogScope scope("reader", "read instance");
  const std::string resolved = resolveInputPath(f);
  Logger::instance().info("reader", "loading input=" + resolved);
  auto root = json::parseFile(resolved);
  auto p = std::make_unique<Problem>();
  p->contentType=root.at("content_type").string; p->instanceUid=root.at("instance_uid").string;
  const auto& region=root.at("region_to_cover"); p->outerBoundary=polygon(region.at("outer_boundary"));
  if(region.object.count("inner_boundaries")) for(const auto& h:region.at("inner_boundaries").array) p->innerBoundaries.push_back(polygon(h));
  p->cutter=polygon(root.at("cutter")); p->cutterCenter=point(root.at("cutter_center"));
  const auto& cutter_count = root.at("number_of_cutters");
  if (cutter_count.type != json::Value::NUMBER ||
      cutter_count.number < 1.0 ||
      std::floor(cutter_count.number) != cutter_count.number) {
    throw std::runtime_error("number_of_cutters must be a positive integer");
  }
  p->numberOfCutters=static_cast<int>(cutter_count.number);
  std::string error; if(!p->validate(&error)) throw std::runtime_error("invalid instance: "+error);
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
