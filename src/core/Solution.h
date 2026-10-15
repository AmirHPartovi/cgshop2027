#pragma once
#include "Problem.h"
#include <cstdint>
#include <map>
namespace cgshop2027 {
struct Tour { std::vector<Point> points; };
struct Solution {
  std::string contentType, instanceUid;
  std::vector<Tour> tours;
  std::map<std::string,std::string> meta;
  std::map<std::string,std::string> rawMetaJson;
  bool validate(const Problem& problem, std::string* error=nullptr) const;
};
int64_t closedTourLength(const std::vector<Point>& points);
int64_t solutionMakespan(const Solution& solution);
}
