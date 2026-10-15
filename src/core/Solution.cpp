#include "Solution.h"
namespace cgshop2027 {
bool Solution::validate(const Problem& p,std::string* error) const {
  auto fail=[&](const char* e){if(error)*error=e;return false;};
  if(!p.validate(error)) return false;
  if(!instanceUid.empty()&&!p.instanceUid.empty()&&instanceUid!=p.instanceUid) return fail("instance_uid mismatch");
  if(tours.size()!=static_cast<size_t>(p.numberOfCutters)) return fail("wrong number of tours");
  std::vector<std::vector<Point>> paths;
  for(const auto& t:tours) {
    if(t.points.empty()) return fail("empty tour");
    if(t.points.size() > 1U) {
      for (size_t i = 0; i < t.points.size(); ++i) {
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
}
