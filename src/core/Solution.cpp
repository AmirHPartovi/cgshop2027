#include "Solution.h"
#include "core/ExecutionControl.h"
#include <algorithm>
#include <cstdint>
#include <cstdlib>
namespace cgshop2027 {
bool Solution::validate(const Problem& p,std::string* error) const {
  auto fail=[&](const char* e){if(error)*error=e;return false;};
  if(!p.validate(error)) return false;
  if(contentType != "CGSHOP2027_Solution") return fail("unsupported solution content_type");
  if(instanceUid != p.instanceUid) return fail("instance_uid mismatch");
  if(tours.size()!=static_cast<size_t>(p.numberOfCutters)) return fail("wrong number of tours");
  std::vector<std::vector<Point>> paths;
  for(const auto& t:tours) {
    ExecutionControl::instance().checkpoint();
    if(t.points.empty()) return fail("empty tour");
    if(t.points.size() > 1U) {
      for (size_t i = 0; i < t.points.size(); ++i) {
        if ((i & 0x3ffU) == 0U)
          ExecutionControl::instance().checkpoint();
        const Point& a = t.points[i];
        const Point& b = t.points[(i + 1) % t.points.size()];
        if (a == b || (a.x != b.x && a.y != b.y)) {
          return fail("tour contains a non-rectilinear edge");
        }
      }
    }
    paths.push_back(t.points);
  }
  if(!p.isCovered(paths)) return fail("region is not covered");
  return true;
}

int64_t closedTourLength(const std::vector<Point>& points) {
  if (points.size() < 2U) return 0;
  int64_t length = 0;
  for (size_t i = 0; i < points.size(); ++i) {
    if ((i & 0x3ffU) == 0U)
      ExecutionControl::instance().checkpoint();
    const Point& a = points[i];
    const Point& b = points[(i + 1U) % points.size()];
    length += std::llabs(static_cast<int64_t>(a.x) - b.x) +
              std::llabs(static_cast<int64_t>(a.y) - b.y);
  }
  return length;
}

int64_t solutionMakespan(const Solution& solution) {
  int64_t result = 0;
  for (const Tour& tour : solution.tours) {
    ExecutionControl::instance().checkpoint();
    result = std::max(result, closedTourLength(tour.points));
  }
  return result;
}
}
