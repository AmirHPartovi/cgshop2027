#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace cgshop2027 {

struct AlgorithmParameters {
    int lnsIterations{250};
    int lnsMaxAnchors{5000};
    int lnsMaxMoveAnchors{16};
    int tspMaxAnchors{3500};
    int twoOptPasses{12};
};

struct RuntimeConfig {
    double globalRunDeadlineSeconds{-1.0};
    double perInstanceTimeoutSeconds{10.0};
    double perAlgorithmTimeoutSeconds{10.0};
    double ipKontTimeoutSeconds{30.0};
    int threadsPerSolver{1};
    int benchmarkJobs{1};
    int memoryLimitMiB{2048};
    uint64_t randomSeed{2027};
    std::vector<std::string> algorithms{"hybrid"};
    AlgorithmParameters algorithmParameters;
    std::vector<std::string> difficultyTierFilter{"all"};
    std::string exactSolvingPolicy{"ip_kont_surrogate"};
    int exactSolverMaxCandidates{0};
    double exactSolverExploratoryTimeBudgetSeconds{0.0};
    std::vector<std::string> heuristicPortfolio{
        "boustrophedon", "stc", "frederickson", "mstc",
        "region-partition", "ilp", "connected-growth", "tsp-cov"};
    int randomizedRepetitions{1};
    std::string outputDirectory{"build/results"};
    bool overwriteExisting{false};
    std::string loggingVerbosity{"info"};
    bool officialValidation{false};

    static RuntimeConfig load(const std::string& configPath = {});
    void validate() const;
    std::string toJson(const RuntimeConfig& requested) const;
};

const RuntimeConfig& runtimeConfig();
void setRuntimeConfig(const RuntimeConfig& config);

}  // namespace cgshop2027
