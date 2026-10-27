#include "algorithms/AnchorCoverAlgorithm.h"
#include "algorithms/BalancedGreedyRouteAlgorithm.h"
#include "algorithms/BoustrophedonAlgorithm.h"
#include "algorithms/ColumnGenerationAlgorithm.h"
#include "algorithms/DecomposeSolver.h"
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
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "core/SolverResult.h"
#include "io/InstanceReader.h"
#include "io/SolutionWriter.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef _WIN32
#include <signal.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <unistd.h>
#endif

namespace {

struct Options {
    std::string input;
    std::string output;
    std::string configPath;
    bool help{false};
    bool validateInstanceOnly{false};
    bool algorithmSpecified{false};
    std::vector<std::string> overrides;
};

const char kUsage[] =
    "usage: solver -i INSTANCE -o OUTPUT [--config FILE] [options]\n"
    "      --mode MODE               heuristic|ip-kont|decompose (default: heuristic)\n"
    "  -a, --algorithm NAME          legacy heuristic component override\n"
    "  -t, --timeout SECONDS         set instance and algorithm timeout\n"
    "      --instance-timeout SEC    per-instance cooperative wall-clock limit\n"
    "      --algorithm-timeout SEC   algorithm time budget\n"
    "      --kont-timeout SEC        IP-KONT subprocess timeout\n"
    "      --global-deadline SEC     invocation deadline (0 disables solving)\n"
    "      --threads-per-solver N   only 1 is supported by current algorithms\n"
    "      --benchmark-jobs N        concurrent outer benchmark processes\n"
    "      --memory-limit-mib N      per-process address-space limit\n"
    "      --seed N                  deterministic LNS random seed\n"
    "      --lns-iterations N        LNS iteration cap\n"
    "      --lns-max-anchors N       LNS coverage-anchor cap\n"
    "      --lns-max-move-anchors N  maximum anchors relocated per move\n"
    "      --tsp-max-anchors N       TSP-COV candidate cap\n"
    "      --two-opt-passes N        TSP-COV 2-opt pass cap\n"
    "      --tier all                difficulty filter (only 'all' is supported)\n"
    "      --exact-policy POLICY     legacy surrogate policy; not exact routing\n"
    "      --exact-max-candidates N  skip IP-KONT surrogate above this size (0=unlimited)\n"
    "      --exact-exploratory-budget SEC (unsupported until tier classification)\n"
    "      --portfolio CSV           hybrid portfolio algorithm names\n"
    "      connected-growth is heuristic; legacy aliases: column-gen, c2, bap\n"
    "      --repetitions N           benchmark repetitions for randomized algorithms\n"
    "      --output-dir DIR          runner output directory\n"
    "      --overwrite               allow existing output/report files\n"
    "      --no-overwrite            refuse existing output/report files\n"
    "      --no-official             disable official checks in batch runners\n"
    "      --log-level LEVEL         debug|info|warning|error\n"
    "      --validate-instance       validate input only; requires -i INSTANCE\n"
    "      --help                    show this help\n";

std::vector<std::string> csv(const std::string& value) {
    std::vector<std::string> result;
    size_t start = 0;
    while (start <= value.size()) {
        const size_t comma = value.find(',', start);
        const std::string item = value.substr(start, comma - start);
        if (item.empty()) throw std::runtime_error("comma-separated values cannot be empty");
        result.push_back(item);
        if (comma == std::string::npos) break;
        start = comma + 1U;
    }
    return result;
}

Options parseOptions(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string argument(argv[i]);
        if (argument == "--help" || argument == "-h") {
            options.help = true;
        } else if (argument == "--validate-instance") {
            options.validateInstanceOnly = true;
        } else if (argument == "--config") {
            if (++i >= argc) throw std::runtime_error("missing --config path");
            options.configPath = argv[i];
        } else if (argument == "-i" || argument == "--input") {
            if (++i >= argc) throw std::runtime_error("missing input path");
            options.input = argv[i];
        } else if (argument == "-o" || argument == "--output") {
            if (++i >= argc) throw std::runtime_error("missing output path");
            options.output = argv[i];
        } else if (argument == "--mode") {
            if (++i >= argc) throw std::runtime_error("missing solver mode");
            options.overrides.emplace_back("solver_mode");
            options.overrides.emplace_back(argv[i]);
        } else if (argument == "-a" || argument == "--algo" ||
                   argument == "--algorithm") {
            if (++i >= argc) throw std::runtime_error("missing algorithm name");
            options.algorithmSpecified = true;
            options.overrides.emplace_back("algorithms");
            options.overrides.emplace_back(argv[i]);
        } else if (argument == "-t" || argument == "--timeout") {
            if (++i >= argc) throw std::runtime_error("missing timeout");
            options.overrides.emplace_back("timeout");
            options.overrides.emplace_back(argv[i]);
        } else {
            static const std::vector<std::string> valueOptions{
                "--global-deadline", "--instance-timeout", "--algorithm-timeout",
                "--kont-timeout", "--threads-per-solver", "--benchmark-jobs",
                "--memory-limit-mib", "--seed", "--lns-iterations",
                "--lns-max-anchors", "--lns-max-move-anchors",
                "--tsp-max-anchors", "--two-opt-passes", "--tier",
                "--exact-policy", "--exact-max-candidates",
                "--exact-exploratory-budget", "--portfolio", "--repetitions",
                "--output-dir", "--log-level"};
            if (std::find(valueOptions.begin(), valueOptions.end(), argument) !=
                valueOptions.end()) {
                if (++i >= argc) throw std::runtime_error("missing value for " + argument);
                options.overrides.emplace_back(argument);
                options.overrides.emplace_back(argv[i]);
            } else if (argument == "--overwrite" || argument == "--no-overwrite" ||
                       argument == "--no-official") {
                options.overrides.emplace_back(argument);
                options.overrides.emplace_back(argument == "--overwrite" ? "true" : "false");
            } else {
                throw std::runtime_error("unknown option: " + argument);
            }
        }
    }
    return options;
}

double parseDouble(const std::string& value, const std::string& option) {
    size_t consumed = 0;
    const double parsed = std::stod(value, &consumed);
    if (consumed != value.size() || !std::isfinite(parsed)) {
        throw std::runtime_error(option + " must be a finite number");
    }
    return parsed;
}

int parseInteger(const std::string& value, const std::string& option) {
    size_t consumed = 0;
    const long parsed = std::stol(value, &consumed);
    if (consumed != value.size() || parsed < 0 || parsed > 2147483647L) {
        throw std::runtime_error(option + " must be a nonnegative 32-bit integer");
    }
    return static_cast<int>(parsed);
}

void applyOverrides(cgshop2027::RuntimeConfig& config,
                    const std::vector<std::string>& overrides) {
    for (size_t i = 0; i < overrides.size(); i += 2U) {
        const std::string& key = overrides[i];
        const std::string& value = overrides[i + 1U];
        if (key == "solver_mode") config.solverMode = value;
        else if (key == "algorithms") config.algorithms = {value};
        else if (key == "timeout") {
            config.perInstanceTimeoutSeconds = parseDouble(value, key);
            config.perAlgorithmTimeoutSeconds = config.perInstanceTimeoutSeconds;
        } else if (key == "--global-deadline")
            config.globalRunDeadlineSeconds = parseDouble(value, key);
        else if (key == "--instance-timeout")
            config.perInstanceTimeoutSeconds = parseDouble(value, key);
        else if (key == "--algorithm-timeout")
            config.perAlgorithmTimeoutSeconds = parseDouble(value, key);
        else if (key == "--kont-timeout")
            config.ipKontTimeoutSeconds = parseDouble(value, key);
        else if (key == "--threads-per-solver")
            config.threadsPerSolver = parseInteger(value, key);
        else if (key == "--benchmark-jobs")
            config.benchmarkJobs = parseInteger(value, key);
        else if (key == "--memory-limit-mib")
            config.memoryLimitMiB = parseInteger(value, key);
        else if (key == "--seed")
            config.randomSeed = static_cast<uint64_t>(parseInteger(value, key));
        else if (key == "--lns-iterations")
            config.algorithmParameters.lnsIterations = parseInteger(value, key);
        else if (key == "--lns-max-anchors")
            config.algorithmParameters.lnsMaxAnchors = parseInteger(value, key);
        else if (key == "--lns-max-move-anchors")
            config.algorithmParameters.lnsMaxMoveAnchors = parseInteger(value, key);
        else if (key == "--tsp-max-anchors")
            config.algorithmParameters.tspMaxAnchors = parseInteger(value, key);
        else if (key == "--two-opt-passes")
            config.algorithmParameters.twoOptPasses = parseInteger(value, key);
        else if (key == "--tier") config.difficultyTierFilter = {value};
        else if (key == "--exact-policy") config.exactSolvingPolicy = value;
        else if (key == "--exact-max-candidates")
            config.exactSolverMaxCandidates = parseInteger(value, key);
        else if (key == "--exact-exploratory-budget")
            config.exactSolverExploratoryTimeBudgetSeconds = parseDouble(value, key);
        else if (key == "--portfolio") config.heuristicPortfolio = csv(value);
        else if (key == "--repetitions")
            config.randomizedRepetitions = parseInteger(value, key);
        else if (key == "--output-dir") config.outputDirectory = value;
        else if (key == "--log-level") config.loggingVerbosity = value;
        else if (key == "--overwrite") config.overwriteExisting = true;
        else if (key == "--no-overwrite") config.overwriteExisting = false;
        else if (key == "--no-official") config.officialValidation = false;
    }
}

void configureMemoryLimit(int memoryMiB) {
#if defined(__APPLE__)
    (void)memoryMiB;
#elif !defined(_WIN32)
    const rlim_t bytes = static_cast<rlim_t>(memoryMiB) * 1024U * 1024U;
    struct rlimit limit{};
    if (getrlimit(RLIMIT_AS, &limit) != 0) {
        throw std::runtime_error("cannot inspect per-process address-space limit");
    }
    limit.rlim_cur = limit.rlim_max == RLIM_INFINITY
                         ? bytes
                         : std::min(bytes, limit.rlim_max);
    if (setrlimit(RLIMIT_AS, &limit) != 0) {
        throw std::runtime_error("cannot enforce per-process memory limit");
    }
#else
    (void)memoryMiB;
#endif
}

void configureDeadline(double timeoutSeconds) {
#ifndef _WIN32
    if (timeoutSeconds <= 0.0) {
        throw std::runtime_error("effective wall-clock timeout is zero");
    }
    struct sigaction action{};
    action.sa_handler = [](int) {
        cgshop2027::ExecutionControl::killActiveChildProcess();
        static constexpr char message[] = "solver hard wall-clock deadline exceeded\n";
        (void)write(STDERR_FILENO, message, sizeof(message) - 1U);
        _Exit(124);
    };
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, nullptr) != 0) {
        throw std::runtime_error("cannot install wall-clock watchdog");
    }
    struct itimerval timer{};
    const auto micros = std::max(
        1LL, static_cast<long long>(std::ceil(timeoutSeconds * 1000000.0)));
    timer.it_value.tv_sec = static_cast<time_t>(micros / 1000000LL);
    timer.it_value.tv_usec = static_cast<suseconds_t>(micros % 1000000LL);
    if (setitimer(ITIMER_REAL, &timer, nullptr) != 0) {
        throw std::runtime_error("cannot start wall-clock watchdog");
    }
#else
    (void)timeoutSeconds;
#endif
}

void disableDeadline() {
#ifndef _WIN32
    struct itimerval timer{};
    (void)setitimer(ITIMER_REAL, &timer, nullptr);
#endif
}

void configureLogging(const std::string& level) {
    using cgshop2027::LogLevel;
    if (level == "debug") cgshop2027::Logger::instance().setLevel(LogLevel::Debug);
    else if (level == "info") cgshop2027::Logger::instance().setLevel(LogLevel::Info);
    else if (level == "warning") cgshop2027::Logger::instance().setLevel(LogLevel::Warning);
    else if (level == "error") cgshop2027::Logger::instance().setLevel(LogLevel::Error);
}

void writeResultReport(const std::string& path,
                       const cgshop2027::SolverResult& result,
                       const std::string& candidatePath = {}) {
    const std::filesystem::path resultPath(path);
    if (!resultPath.parent_path().empty()) {
        std::filesystem::create_directories(resultPath.parent_path());
    }
    std::ofstream output(path);
    if (!output) throw std::runtime_error("cannot write solver result report");
    output << result.toJson(candidatePath);
    if (!output) throw std::runtime_error("failed writing solver result report");
}

}  // namespace

int main(int argc, char** argv) {
    std::string failureResultPath;
    std::string failureSolverMode;
    const auto processStarted = std::chrono::steady_clock::now();
    try {
        const Options options = parseOptions(argc, argv);
        if (options.help) {
            std::cout << kUsage;
            return EXIT_SUCCESS;
        }
        if (options.validateInstanceOnly) {
            if (options.input.empty())
                throw std::runtime_error("--validate-instance requires -i INSTANCE");
            (void)cgshop2027::InstanceReader::readInstance(options.input);
            std::cout << "instance valid\n";
            return 0;
        }
        auto config = cgshop2027::RuntimeConfig::load(options.configPath);
        applyOverrides(config, options.overrides);
        config.validate();
        failureSolverMode = config.solverMode;
        if (options.algorithmSpecified && config.solverMode != "heuristic") {
            throw std::runtime_error(
                "--algorithm is a legacy heuristic override and requires --mode heuristic");
        }
        if (config.officialValidation) {
            throw std::runtime_error(
                "official validation runs in scripts/benchmark.py or scripts/solve_all.py, not in the C++ solver");
        }
        if (config.algorithms.size() != 1U) {
            throw std::runtime_error(
                "solver accepts one algorithm; use the batch runner for algorithm lists");
        }
        if (options.input.empty() || options.output.empty()) {
            throw std::runtime_error(kUsage);
        }
        const std::filesystem::path outputPath(options.output);
        const std::filesystem::path reportPath(options.output + ".config.json");
        const std::filesystem::path resultPath(options.output + ".result.json");
        failureResultPath = resultPath.string();
        if (!config.overwriteExisting &&
            (std::filesystem::exists(outputPath) ||
             std::filesystem::exists(reportPath) ||
             std::filesystem::exists(resultPath))) {
            throw std::runtime_error(
                "output or solver report already exists; pass --overwrite");
        }

        cgshop2027::setRuntimeConfig(config);
        configureLogging(config.loggingVerbosity);
        configureMemoryLimit(config.memoryLimitMiB);
        const auto reportParent = reportPath.parent_path();
        if (!reportParent.empty()) std::filesystem::create_directories(reportParent);
        std::ofstream report(reportPath);
        if (!report) throw std::runtime_error("cannot write effective configuration report");
        report << config.toJson(config);
        if (!report) throw std::runtime_error("failed writing effective configuration report");
        report.close();
        cgshop2027::LogScope scope("solver", "run");
        const auto started = std::chrono::steady_clock::now();
        auto problem = cgshop2027::InstanceReader::readInstance(options.input);
        if (config.solverMode == "ip-kont") {
            cgshop2027::SolverResult result;
            result.solverMode = config.solverMode;
            result.completion = cgshop2027::SolverCompletionStatus::Unavailable;
            result.algorithmImplementation = config.solverMode;
            result.terminationReason =
                "the verified exact closed-tour IP-KONT model is not implemented; legacy ilp is a surrogate";
            result.runtimeSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started).count();
            writeResultReport(resultPath.string(), result);
            cgshop2027::Logger::instance().error(
                "solver", config.solverMode + " mode unavailable: " +
                              result.terminationReason);
            return EXIT_FAILURE;
        }
        const double timeout = std::min(
            config.perInstanceTimeoutSeconds,
            std::min(config.perAlgorithmTimeoutSeconds,
                     config.globalRunDeadlineSeconds < 0.0
                         ? config.perInstanceTimeoutSeconds
                         : config.globalRunDeadlineSeconds));
        if (timeout <= 0.0) {
            cgshop2027::SolverResult result;
            result.solverMode = config.solverMode;
            result.completion =
                cgshop2027::SolverCompletionStatus::TimedOutWithoutIncumbent;
            result.terminationReason = "effective solver timeout is zero";
            result.runtimeSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started).count();
            writeResultReport(resultPath.string(), result);
            return EXIT_FAILURE;
        }
        configureDeadline(timeout);
        const auto invocationDeadline =
            cgshop2027::ExecutionControl::Clock::now() +
            std::chrono::duration_cast<cgshop2027::ExecutionControl::Clock::duration>(
                std::chrono::duration<double>(timeout));
        const double finalizationReserve =
            std::min(5.0, std::max(0.25, timeout * 0.2));
        const double searchTimeout = std::max(0.0, timeout - finalizationReserve);
        cgshop2027::ExecutionControl::instance().setDeadline(
            invocationDeadline -
            std::chrono::duration_cast<cgshop2027::ExecutionControl::Clock::duration>(
                std::chrono::duration<double>(finalizationReserve)));
        const std::string algorithmName =
            config.solverMode == "decompose" ? "decompose" : config.algorithms.front();
        cgshop2027::Logger::instance().info(
            "solver", "algorithm=" + algorithmName + " effective_timeout=" +
                          std::to_string(timeout) + "s cooperative_search_cap=" +
                          std::to_string(searchTimeout) + "s finalization_reserve=" +
                          std::to_string(finalizationReserve) + "s");
        std::unique_ptr<cgshop2027::BaseAlgorithm> algorithm;
        if (algorithmName == "decompose") {
            algorithm = std::make_unique<cgshop2027::DecomposeSolver>(*problem);
        } else if (algorithmName == "anchor-cover" || algorithmName == "anchor") {
            algorithm = std::make_unique<cgshop2027::AnchorCoverAlgorithm>(*problem);
        } else if (algorithmName == "balanced-greedy" || algorithmName == "greedy") {
            algorithm = std::make_unique<cgshop2027::BalancedGreedyRouteAlgorithm>(*problem);
        } else if (algorithmName == "strip") {
            algorithm = std::make_unique<cgshop2027::StripAlgorithm>(*problem);
        } else if (algorithmName == "partition") {
            algorithm = std::make_unique<cgshop2027::PartitioningAlgorithm>(*problem);
        } else if (algorithmName == "local") {
            algorithm = std::make_unique<cgshop2027::LocalSearch>(
                *problem, cgshop2027::PartitioningAlgorithm(*problem).solve(timeout));
        } else if (algorithmName == "boustrophedon" || algorithmName == "a1" ||
                   algorithmName == "zigzag") {
            algorithm = std::make_unique<cgshop2027::BoustrophedonAlgorithm>(*problem);
        } else if (algorithmName == "stc" || algorithmName == "a2") {
            algorithm = std::make_unique<cgshop2027::StcAlgorithm>(*problem);
        } else if (algorithmName == "tsp-cov" || algorithmName == "tsp_cov" ||
                   algorithmName == "a3") {
            algorithm = std::make_unique<cgshop2027::TspCovAlgorithm>(*problem);
        } else if (algorithmName == "frederickson" || algorithmName == "b1") {
            algorithm = std::make_unique<cgshop2027::FredericksonSplitAlgorithm>(*problem);
        } else if (algorithmName == "mstc" || algorithmName == "b2") {
            algorithm = std::make_unique<cgshop2027::MstcAlgorithm>(*problem);
        } else if (algorithmName == "region-partition" || algorithmName == "b3") {
            algorithm = std::make_unique<cgshop2027::RegionPartitionAssignAlgorithm>(*problem);
        } else if (algorithmName == "ilp" || algorithmName == "c1") {
            algorithm = std::make_unique<cgshop2027::IlpAlgorithm>(*problem);
        } else if (algorithmName == "connected-growth" || algorithmName == "column-gen" ||
                   algorithmName == "c2" ||
                   algorithmName == "bap") {
            algorithm = std::make_unique<cgshop2027::ConnectedGrowthAlgorithm>(
                *problem, algorithmName);
        } else if (algorithmName == "lns" || algorithmName == "d1") {
            algorithm = std::make_unique<cgshop2027::LnsMultiCutterAlgorithm>(*problem);
        } else if (algorithmName == "hybrid" || algorithmName == "e") {
            algorithm = std::make_unique<cgshop2027::HybridSolver>(*problem);
        } else {
            throw std::runtime_error("unknown algorithm: " + algorithmName);
        }
        cgshop2027::Solution solution;
        bool timedOutWithFallback = false;
        bool usedPartitionFallback = false;
        try {
            cgshop2027::ExecutionControl::instance().checkpoint();
            solution = algorithm->solve(searchTimeout);
            timedOutWithFallback =
                cgshop2027::ExecutionControl::instance().cancelled();
        } catch (const cgshop2027::ExecutionCancelled&) {
            timedOutWithFallback = true;
            usedPartitionFallback = true;
            cgshop2027::ExecutionControl::instance().clearDeadline();
            cgshop2027::Logger::instance().warning(
                "solver", "requested algorithm exceeded its cooperative deadline; "
                          "using partition fallback");
            solution = cgshop2027::PartitioningAlgorithm(*problem).solve();
            solution.meta["requested_algorithm"] = algorithmName;
            solution.meta["algorithm_implementation"] = "partition";
            solution.meta["candidate_source"] = "partition_fallback";
            solution.meta["fallback_algorithm"] = "partition";
            solution.meta["fallback_reason"] =
                "requested algorithm exceeded cooperative deadline";
            if (config.solverMode == "decompose") {
                solution.meta["decomposition_status"] =
                    "TIME_LIMIT_WITH_PARTITION_INCUMBENT";
                solution.meta["decomposition_exact"] = "false";
                solution.meta["decomposition_local_exact"] = "false";
                solution.meta["decomposition_local_solver"] =
                    "not_started_before_deadline";
            }
        }
        cgshop2027::ExecutionControl::instance().clearDeadline();
        if (solution.meta.find("requested_algorithm") == solution.meta.end())
            solution.meta["requested_algorithm"] = algorithmName;
        solution.meta["cooperative_search_budget_cap_seconds"] =
            std::to_string(searchTimeout);
        solution.meta["finalization_reserve_seconds"] =
            std::to_string(finalizationReserve);
        if (timedOutWithFallback) {
            if (solution.meta.find("execution_status") == solution.meta.end())
                solution.meta["execution_status"] =
                    "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE";
            if (solution.meta.find("candidate_source") == solution.meta.end())
                solution.meta["candidate_source"] = usedPartitionFallback
                    ? "partition_fallback" : "requested_algorithm_candidate";
        } else {
            if (solution.meta.find("execution_status") == solution.meta.end())
                solution.meta["execution_status"] = "COMPLETED";
            if (solution.meta.find("candidate_source") == solution.meta.end())
                solution.meta["candidate_source"] = "requested_algorithm";
        }
        const std::string executionStatus = solution.meta.at("execution_status");
        const bool hasTimedOutStatus =
            timedOutWithFallback ||
            executionStatus == "TIME_LIMIT_WITH_FEASIBLE_CANDIDATE" ||
            executionStatus == "TIME_LIMIT_WITH_INCUMBENT" ||
            executionStatus == "WALL_CLOCK_TIMEOUT_WITH_FEASIBLE_INCUMBENT";
        std::string error;
        if (!solution.validate(*problem, &error)) {
            cgshop2027::SolverResult result;
            result.solverMode = config.solverMode;
            result.candidate = solution;
            result.internalValidation =
                cgshop2027::CandidateValidationStatus::Failed;
            result.completion = cgshop2027::SolverCompletionStatus::Failed;
            result.algorithmImplementation =
                solution.meta.count("algorithm_implementation") != 0U
                    ? solution.meta.at("algorithm_implementation") : algorithmName;
            result.candidateSource =
                solution.meta.count("candidate_source") != 0U
                    ? solution.meta.at("candidate_source") : "unknown";
            result.runtimeSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started).count();
            result.terminationReason = "final validation rejected candidate: " + error;
            writeResultReport(resultPath.string(), result);
            throw std::runtime_error("algorithm produced invalid solution: " + error);
        }
        cgshop2027::SolverResult result;
        result.solverMode = config.solverMode;
        result.candidate = solution;
        result.internalValidation = cgshop2027::CandidateValidationStatus::Passed;
        result.completion = hasTimedOutStatus
                                ? cgshop2027::SolverCompletionStatus::TimedOutWithIncumbent
                                : cgshop2027::SolverCompletionStatus::FeasibleNotProven;
        result.algorithmImplementation = solution.meta.at("algorithm_implementation");
        result.candidateSource = solution.meta.at("candidate_source");
        result.runtimeSeconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        result.terminationReason = hasTimedOutStatus
                                       ? "cooperative deadline reached; retained feasible heuristic candidate"
                                       : "heuristic search completed without an optimality proof";
        solution.meta["solver_mode"] = config.solverMode;
        solution.meta["solver_completion_status"] =
            cgshop2027::toString(result.completion);
        solution.meta["internal_validation_status"] = "passed";
        solution.meta["official_validation_status"] = "not_requested";
        solution.meta["optimality_proved"] = "false";
        solution.meta["runtime_seconds"] = std::to_string(result.runtimeSeconds);
        solution.meta["termination_reason"] = result.terminationReason;
        cgshop2027::SolutionWriter::write(solution, *problem, options.output);
        writeResultReport(resultPath.string(), result, options.output);
        disableDeadline();
        cgshop2027::Logger::instance().info(
            "solver", "validated solution uid=" + solution.instanceUid);
        return EXIT_SUCCESS;
    } catch (const cgshop2027::ExecutionCancelled&) {
        cgshop2027::Logger::instance().error(
            "solver", "cooperative deadline reached before a valid candidate was produced");
        if (!failureResultPath.empty() &&
            !std::filesystem::exists(failureResultPath)) {
            cgshop2027::SolverResult result;
            result.solverMode = failureSolverMode;
            result.completion =
                cgshop2027::SolverCompletionStatus::TimedOutWithoutIncumbent;
            result.terminationReason =
                "cooperative deadline reached before a valid candidate was produced";
            result.runtimeSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - processStarted).count();
            writeResultReport(failureResultPath, result);
        }
        return EXIT_FAILURE;
    } catch (const std::exception& exception) {
        cgshop2027::Logger::instance().error("solver", exception.what());
        if (!failureResultPath.empty() &&
            !std::filesystem::exists(failureResultPath)) {
            try {
                cgshop2027::SolverResult result;
                result.solverMode = failureSolverMode;
                result.completion = cgshop2027::SolverCompletionStatus::Failed;
                result.terminationReason = exception.what();
                result.runtimeSeconds = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - processStarted).count();
                writeResultReport(failureResultPath, result);
            } catch (const std::exception& reportError) {
                cgshop2027::Logger::instance().error(
                    "solver", std::string("cannot persist failure result: ") +
                                  reportError.what());
            }
        }
        return EXIT_FAILURE;
    }
}
