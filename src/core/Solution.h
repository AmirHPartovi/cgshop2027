#pragma once
#include "Problem.h"
#include <map>
namespace cgshop2027 {
struct Tour { std::vector<Point> points; };
struct Solution {
  std::string contentType, instanceUid;
  std::vector<Tour> tours;
  std::map<std::string,std::string> meta;
  bool validate(const Problem& problem, std::string* error=nullptr) const;
};
}
