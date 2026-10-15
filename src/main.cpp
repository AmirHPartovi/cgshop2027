#include "algorithms/AnchorCoverAlgorithm.h"
#include "algorithms/BalancedGreedyRouteAlgorithm.h"
#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/FredericksonSplitAlgorithm.h"
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
#include "io/InstanceReader.h"
#include "io/SolutionWriter.h"
#include "utils/Logger.h"

#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

struct Options {
    std::string input;
    std::string output;
    std::string algorithm{"hybrid"};
    double timeout{-1.0};
};

const char kUsage[] =
    "usage: solver -i INSTANCE -o OUTPUT "
    "[-a strip|partition|local|anchor-cover|balanced-greedy|"
    "boustrophedon|stc|tsp-cov|frederickson|mstc|region-partition|"
    "ilp|column-gen|lns|hybrid] [-t SECONDS]";

Options parseOptions(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string argument(argv[i]);
        if (argument == "-i" || argument == "--input") {
            if (++i >= argc) throw std::runtime_error("missing input path");
            options.input = argv[i];
        } else if (argument == "-o" || argument == "--output") {
            if (++i >= argc) throw std::runtime_error("missing output path");
            options.output = argv[i];
        } else if (argument == "-a" || argument == "--algo") {
            if (++i >= argc) throw std::runtime_error("missing algorithm name");
            options.algorithm = argv[i];
        } else if (argument == "-t" || argument == "--timeout") {
            if (++i >= argc) throw std::runtime_error("missing timeout");
            options.timeout = std::stod(argv[i]);
        } else {
            throw std::runtime_error("unknown option: " + argument);
        }
    }
    if (options.input.empty() || options.output.empty()) {
        throw std::runtime_error(kUsage);
    }
    return options;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        cgshop2027::LogScope scope("solver", "run");
        const Options options = parseOptions(argc, argv);
        cgshop2027::Logger::instance().info(
            "solver", "algorithm=" + options.algorithm +
                          " timeout=" + std::to_string(options.timeout) + "s");
        auto problem = cgshop2027::InstanceReader::readInstance(options.input);
        std::unique_ptr<cgshop2027::BaseAlgorithm> algorithm;
        if (options.algorithm == "anchor-cover" || options.algorithm == "anchor") {
            algorithm = std::make_unique<cgshop2027::AnchorCoverAlgorithm>(*problem);
        } else if (options.algorithm == "balanced-greedy" ||
                   options.algorithm == "greedy") {
            algorithm =
                std::make_unique<cgshop2027::BalancedGreedyRouteAlgorithm>(*problem);
        } else if (options.algorithm == "strip") {
            algorithm = std::make_unique<cgshop2027::StripAlgorithm>(*problem);
        } else if (options.algorithm == "partition") {
            algorithm =
                std::make_unique<cgshop2027::PartitioningAlgorithm>(*problem);
        } else if (options.algorithm == "local") {
            algorithm = std::make_unique<cgshop2027::LocalSearch>(
                *problem, cgshop2027::PartitioningAlgorithm(*problem).solve(
                              options.timeout));
        } else if (options.algorithm == "boustrophedon" || options.algorithm == "a1" ||
                   options.algorithm == "zigzag") {
            algorithm = std::make_unique<cgshop2027::BoustrophedonAlgorithm>(*problem);
        } else if (options.algorithm == "stc" || options.algorithm == "a2") {
            algorithm = std::make_unique<cgshop2027::StcAlgorithm>(*problem);
        } else if (options.algorithm == "tsp-cov" || options.algorithm == "tsp_cov" ||
                   options.algorithm == "a3") {
            algorithm = std::make_unique<cgshop2027::TspCovAlgorithm>(*problem);
        } else if (options.algorithm == "frederickson" || options.algorithm == "b1") {
            algorithm =
                std::make_unique<cgshop2027::FredericksonSplitAlgorithm>(*problem);
        } else if (options.algorithm == "mstc" || options.algorithm == "b2") {
            algorithm = std::make_unique<cgshop2027::MstcAlgorithm>(*problem);
        } else if (options.algorithm == "region-partition" ||
                   options.algorithm == "b3") {
            algorithm =
                std::make_unique<cgshop2027::RegionPartitionAssignAlgorithm>(*problem);
        } else if (options.algorithm == "ilp" || options.algorithm == "c1") {
            algorithm = std::make_unique<cgshop2027::IlpAlgorithm>(*problem);
        } else if (options.algorithm == "column-gen" || options.algorithm == "c2" ||
                   options.algorithm == "bap") {
            algorithm =
                std::make_unique<cgshop2027::ColumnGenerationAlgorithm>(*problem);
        } else if (options.algorithm == "lns" || options.algorithm == "d1") {
            algorithm = std::make_unique<cgshop2027::LnsMultiCutterAlgorithm>(*problem);
        } else if (options.algorithm == "hybrid" || options.algorithm == "e") {
            algorithm = std::make_unique<cgshop2027::HybridSolver>(*problem);
        } else {
            throw std::runtime_error("unknown algorithm: " + options.algorithm);
        }
        cgshop2027::Solution solution = algorithm->solve(options.timeout);
        std::string error;
        if (!solution.validate(*problem, &error)) {
            throw std::runtime_error("algorithm produced invalid solution: " +
                                     error);
        }
        cgshop2027::SolutionWriter::write(solution, options.output);
        cgshop2027::Logger::instance().info(
            "solver", "validated solution uid=" + solution.instanceUid);
        return EXIT_SUCCESS;
    } catch (const std::exception& exception) {
        cgshop2027::Logger::instance().error("solver", exception.what());
        return EXIT_FAILURE;
    }
}
