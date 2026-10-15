#include "Problem.h"
#include <cmath>
#include <algorithm>

namespace cgshop2027 {
namespace {
bool closed(const std::vector<Point>& p) { return p.size() >= 4; }
bool aligned(const std::vector<Point>& p) {
  if (!closed(p)) return false;
 for (size_t i=0;i<p.size();++i) {
   const Point& a = p[i];
   const Point& b = p[(i + 1) % p.size()];
   if (a.x != b.x && a.y != b.y) return false;
 }
  return true;
}
bool inside(double x,double y,const std::vector<Point>& p) {
  bool in=false;
  for(size_t i=0,j=p.size()-1;i<p.size();j=i++) {
    const auto& a=p[i]; const auto& b=p[j];
    if (((a.y>y)!=(b.y>y)) && x < (b.x-a.x)*(y-a.y)/(double)(b.y-a.y)+a.x) in=!in;
  }
  return in;
}
bool onBoundary(double x, double y, const std::vector<Point>& p) {
    for (size_t i = 0; i < p.size(); ++i) {
      const Point& a = p[i];
      const Point& b = p[(i + 1) % p.size()];
      if (a.x == b.x && x == a.x && y >= std::min(a.y, b.y) &&
          y <= std::max(a.y, b.y)) return true;
      if (a.y == b.y && y == a.y && x >= std::min(a.x, b.x) &&
          x <= std::max(a.x, b.x)) return true;
    }
    return false;
}
double signedArea(const std::vector<Point>& p) {
    double area = 0.0;
    for (size_t i = 0; i < p.size(); ++i) {
      const Point& a = p[i];
      const Point& b = p[(i + 1) % p.size()];
      area += static_cast<double>(a.x) * b.y -
              static_cast<double>(b.x) * a.y;
    }
    return area / 2.0;
}
std::unordered_set<Point,PointHash> raster(const std::vector<Point>& outer,
 const std::vector<std::vector<Point>>& holes) {
  std::unordered_set<Point,PointHash> out;
  if (outer.empty()) return out;
  int minx=outer[0].x,maxx=minx,miny=outer[0].y,maxy=miny;
  for(auto p:outer){minx=std::min(minx,p.x);maxx=std::max(maxx,p.x);miny=std::min(miny,p.y);maxy=std::max(maxy,p.y);}
  for(int y=miny;y<maxy;++y) for(int x=minx;x<maxx;++x)
    if(inside(x+.5,y+.5,outer)) { bool hole=false; for(auto& h:holes) if(inside(x+.5,y+.5,h)) hole=true; if(!hole) out.insert({x,y}); }
  return out;
}
}
int Problem::regionArea() const { return static_cast<int>(regionCells().size()); }
std::unordered_set<Point,PointHash> Problem::regionCells() const { return raster(outerBoundary,innerBoundaries); }
std::unordered_set<Point,PointHash> Problem::cutterCells() const { return raster(cutter,{}); }
bool Problem::validate(std::string* error) const {
  auto fail=[&](const char* e){if(error)*error=e;return false;};
  if(contentType != "CGSHOP2027_Instance" &&
     contentType != "cgshop2027.instance") return fail("unsupported instance content_type");
  if(instanceUid.empty()) return fail("instance_uid must not be empty");
  if(!closed(outerBoundary)||!aligned(outerBoundary)) return fail("outer_boundary must be closed and axis-aligned");
  if(outerBoundary.size()<4) return fail("outer_boundary has too few points");
  if (signedArea(outerBoundary) <= 0.0) return fail("outer_boundary must be counter-clockwise");
  for(const auto& h:innerBoundaries) {
    if(!closed(h)||!aligned(h)) return fail("inner boundary must be closed and axis-aligned");
    if (signedArea(h) >= 0.0) return fail("inner boundary must be clockwise");
  }
  if(!closed(cutter)||!aligned(cutter)) return fail("cutter must be closed and axis-aligned");
  if (signedArea(cutter) <= 0.0) return fail("cutter must be counter-clockwise");
  if (!inside(cutterCenter.x, cutterCenter.y, cutter) &&
      !onBoundary(cutterCenter.x, cutterCenter.y, cutter)) {
    return fail("cutter_center must be within cutter");
  }
  if(cutterCells().empty()||regionCells().empty()) return fail("polygons must have positive rasterized area");
  if(numberOfCutters<=0) return fail("number_of_cutters must be positive");
  return true;
}
bool Problem::isCovered(const std::vector<Point>& centers) const {
  auto target=regionCells(); if(centers.size()!=static_cast<size_t>(numberOfCutters)) return false;
  auto shape=cutterCells(); std::unordered_set<Point,PointHash> covered;
  for(auto c:centers) for(auto p:shape) covered.insert({c.x+p.x-cutterCenter.x,c.y+p.y-cutterCenter.y});
  for(auto p:target) if(!covered.count(p)) return false;
  return true;
}
bool Problem::isCovered(const std::vector<std::vector<Point>>& tours) const {
  if(tours.size()!=static_cast<size_t>(numberOfCutters)) return false;
  auto target=regionCells(); auto shape=cutterCells(); std::unordered_set<Point,PointHash> covered;
  for(const auto& tour:tours) {
    if (tour.empty()) return false;
    const size_t edge_count = tour.size() == 1U ? 1U : tour.size();
    for (size_t i = 0; i < edge_count; ++i) {
      const Point start = tour[i];
      const Point end = tour.size() == 1U ? start : tour[(i + 1) % tour.size()];
      const int length = start.manhattanDistance(end);
      for (int step = 0; step <= length; ++step) {
        const Point center{start.x + (end.x - start.x) * step / (length == 0 ? 1 : length),
                           start.y + (end.y - start.y) * step / (length == 0 ? 1 : length)};
        for(auto p:shape) covered.insert({center.x+p.x-cutterCenter.x,
                                          center.y+p.y-cutterCenter.y});
      }
    }
  }
  for(auto p:target) if(!covered.count(p)) return false;
  return true;
}
}
