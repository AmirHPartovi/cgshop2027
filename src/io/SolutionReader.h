#pragma once

#include "../core/Solution.h"
#include <string>

namespace cgshop2027 {

class SolutionReader {
public:
    static Solution readSolution(const std::string& filename,
                                 const Problem& problem);
};

}  // namespace cgshop2027
