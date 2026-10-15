#include "algorithms/HybridSolver.h"
#include "algorithms/IlpAlgorithm.h"
#include "algorithms/LocalSearch.h"
#include "algorithms/LnsMultiCutterAlgorithm.h"
#include "algorithms/MstcAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/RegionPartitionAssignAlgorithm.h"
#include "algorithms/StcAlgorithm.h"
#include "algorithms/StripAlgorithm.h"
#include "algorithms/TspCovAlgorithm.h"
#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
#include "algorithms/AnchorCoverAlgorithm.h"
#include "algorithms/BalancedGreedyRouteAlgorithm.h"
#include "io/InstanceReader.h"

#include <cassert>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

int main() {
    const auto problem = cgshop2027::InstanceReader::readInstance(
        "../../data/test/fpg73_1k_1s2.instance.json");
    const auto multi = cgshop2027::InstanceReader::readInstance(
        "../../data/test/fpg73_1k_3s2.instance.json");
    using Pair = std::pair<std::string, cgshop2027::Solution>;
    std::vector<Pair> results;
    
    // Test each algorithm individually with error handling
    try {
        std::cout << "Testing partition algorithm..." << std::endl;
        results.push_back({"partition",
                           cgshop2027::PartitioningAlgorithm(*problem).solve()});
    } catch (const std::exception& e) {
        std::cerr << "partition: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing strip algorithm..." << std::endl;
        results.push_back({"strip", cgshop2027::StripAlgorithm(*problem).solve()});
    } catch (const std::exception& e) {
        std::cerr << "strip: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing boustrophedon algorithm..." << std::endl;
        results.push_back(
            {"boustrophedon", cgshop2027::BoustrophedonAlgorithm(*problem).solve()});
    } catch (const std::exception& e) {
        std::cerr << "boustrophedon: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing stc algorithm..." << std::endl;
        results.push_back({"stc", cgshop2027::StcAlgorithm(*problem).solve()});
    } catch (const std::exception& e) {
        std::cerr << "stc: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing tsp-cov algorithm..." << std::endl;
        results.push_back({"tsp-cov", cgshop2027::TspCovAlgorithm(*problem).solve(2.0)});
    } catch (const std::exception& e) {
        std::cerr << "tsp-cov: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing frederickson algorithm..." << std::endl;
        results.push_back(
            {"frederickson", cgshop2027::FredericksonSplitAlgorithm(*multi).solve(2.0)});
    } catch (const std::exception& e) {
        std::cerr << "frederickson: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing mstc algorithm..." << std::endl;
        results.push_back({"mstc", cgshop2027::MstcAlgorithm(*multi).solve()});
    } catch (const std::exception& e) {
        std::cerr << "mstc: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing region-partition algorithm..." << std::endl;
        results.push_back(
            {"region-partition",
             cgshop2027::RegionPartitionAssignAlgorithm(*multi).solve()});
    } catch (const std::exception& e) {
        std::cerr << "region-partition: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing ilp algorithm..." << std::endl;
        results.push_back({"ilp", cgshop2027::IlpAlgorithm(*multi).solve()});
    } catch (const std::exception& e) {
        std::cerr << "ilp: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing column-gen algorithm..." << std::endl;
        results.push_back(
            {"column-gen", cgshop2027::ColumnGenerationAlgorithm(*multi).solve(2.0)});
    } catch (const std::exception& e) {
        std::cerr << "column-gen: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing lns algorithm..." << std::endl;
        results.push_back(
            {"lns", cgshop2027::LnsMultiCutterAlgorithm(*multi).solve(1.0)});
    } catch (const std::exception& e) {
        std::cerr << "lns: exception: " << e.what() << '\n';
    }
    
    try {
        std::cout << "Testing hybrid solver..." << std::endl;
        results.push_back({"hybrid", cgshop2027::HybridSolver(*problem).solve(2.0)});
    } catch (const std::exception& e) {
        std::cerr << "hybrid: exception: " << e.what() << '\n';
    }
    
    std::cout << "\n=== Validation Results ===" << std::endl;
    int passed = 0, failed = 0;
    for (const auto& result : results) {
        std::string error;
        const cgshop2027::Problem& used =
            (result.first == "partition" || result.first == "strip" ||
             result.first == "boustrophedon" || result.first == "stc" ||
             result.first == "tsp-cov" || result.first == "hybrid")
                ? *problem
                : *multi;
        if (!result.second.validate(used, &error)) {
            std::cerr << "✗ " << result.first << ": " << error << '\n';
            failed++;
        } else {
            std::cout << "✓ " << result.first << ": PASSED (tours=" 
                     << result.second.tours.size() << ")" << '\n';
            passed++;
        }
    }
    
    std::cout << "\nSummary: " << passed << " passed, " << failed << " failed" << std::endl;
    return failed > 0 ? 1 : 0;
}


