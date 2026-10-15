#pragma once
#include "../core/Problem.h"
#include <memory>
namespace cgshop2027 {
class InstanceReader {
public:
 static std::unique_ptr<Problem> readInstance(const std::string& filename);
 static bool validateFormat(const std::string& filename);
 static std::string getFormatInfo();
};
}
