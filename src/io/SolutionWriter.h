#pragma once
#include "../core/Solution.h"
#include <string>
namespace cgshop2027 {
class SolutionWriter {
public: static void write(const Solution& solution,const std::string& filename);
};
}
