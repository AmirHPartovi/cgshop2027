#include "io/InstanceReader.h"
#include "io/SolutionWriter.h"
#include "algorithms/PartitioningAlgorithm.h"
#include <cassert>
#include <fstream>
#include <iostream>
int main() {
  auto p = cgshop2027::InstanceReader::readInstance(
      "../../data/test/fpg73_1k_1s2.instance.json");
  assert(p->regionArea() > 0);
  cgshop2027::Solution s =
      cgshop2027::PartitioningAlgorithm(*p).solve();
  std::string error;
  if (!s.validate(*p, &error)) {
    std::cerr << error << '\n';
    return 1;
  }
  cgshop2027::SolutionWriter::write(s,"io_test_solution.json");
  std::ifstream f("io_test_solution.json"); assert(f.good());
}
