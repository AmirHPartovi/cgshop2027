#include "core/RuntimeConfig.h"

#include "io/Json.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace cgshop2027 {
namespace {

RuntimeConfig activeConfig;
constexpr double kMaximumTimeoutSeconds = 31536000.0;

const std::set<std::string> kConfigKeys{
    "solver_mode",
    "global_run_deadline_seconds",
    "per_instance_timeout_seconds",
    "per_algorithm_timeout_seconds",
    "ip_kont_timeout_seconds",
    "threads_per_solver",
    "benchmark_jobs",
    "memory_limit_mib",
    "random_seed",
    "algorithms",
    "algorithm_parameters",
    "difficulty_tier_filter",
    "exact_solving_policy",
    "exact_solver_max_candidates",
    "exact_solver_exploratory_time_budget_seconds",
    "heuristic_portfolio",
    "randomized_repetitions",
    "output_directory",
    "overwrite_existing",
    "logging_verbosity",
    "official_validation"};

double number(const json::Value& value, const std::string& name) {
    if (value.type != json::Value::NUMBER || !std::isfinite(value.number)) {
        throw std::runtime_error(name + " must be a finite number");
    }
    return value.number;
}

int positiveInteger(const json::Value& value, const std::string& name,
                    bool allowZero = false) {
    const int result = json::integer(value, name);
    if (result < (allowZero ? 0 : 1)) {
        throw std::runtime_error(name + (allowZero ? " must be nonnegative"
                                                   : " must be positive"));
    }
    return result;
}

std::vector<std::string> stringArray(const json::Value& value,
                                     const std::string& name) {
    if (value.type != json::Value::ARRAY) {
        throw std::runtime_error(name + " must be an array of strings");
    }
    std::vector<std::string> result;
    for (const auto& item : value.array) {
        if (item.type != json::Value::STRING || item.string.empty()) {
            throw std::runtime_error(name + " must contain nonempty strings");
        }
        result.push_back(item.string);
    }
    return result;
}

void requireBoolean(const json::Value& value, bool& output, const std::string& name) {
    if (value.type != json::Value::BOOL) {
        throw std::runtime_error(name + " must be a boolean");
    }
    output = value.boolean;
}

void applyJson(RuntimeConfig& config, const json::Value& root) {
    if (root.type != json::Value::OBJECT) {
        throw std::runtime_error("configuration root must be a JSON object");
    }
    for (const auto& item : root.object) {
        if (kConfigKeys.count(item.first) == 0U) {
            throw std::runtime_error("unknown configuration key: " + item.first);
        }
    }
    const auto setTimeout = [&](const char* key, double& target, bool nullable) {
        const auto found = root.object.find(key);
        if (found == root.object.end()) return;
        if (nullable && found->second.type == json::Value::NUL) {
            target = -1.0;
            return;
        }
        target = number(found->second, key);
        if (nullable && target < 0.0) {
            throw std::runtime_error(std::string(key) + " must be null or nonnegative");
        }
    };
    const auto mode = root.object.find("solver_mode");
    if (mode != root.object.end()) {
        if (mode->second.type != json::Value::STRING) {
            throw std::runtime_error("solver_mode must be a string");
        }
        config.solverMode = mode->second.string;
    }
    setTimeout("global_run_deadline_seconds", config.globalRunDeadlineSeconds, true);
    setTimeout("per_instance_timeout_seconds", config.perInstanceTimeoutSeconds, false);
    setTimeout("per_algorithm_timeout_seconds", config.perAlgorithmTimeoutSeconds, false);
    setTimeout("ip_kont_timeout_seconds", config.ipKontTimeoutSeconds, false);
    setTimeout("exact_solver_exploratory_time_budget_seconds",
               config.exactSolverExploratoryTimeBudgetSeconds, false);

    const auto setInt = [&](const char* key, int& target, bool allowZero = false) {
        const auto found = root.object.find(key);
        if (found != root.object.end()) target = positiveInteger(found->second, key, allowZero);
    };
    setInt("threads_per_solver", config.threadsPerSolver);
    setInt("benchmark_jobs", config.benchmarkJobs);
    setInt("memory_limit_mib", config.memoryLimitMiB);
    setInt("exact_solver_max_candidates", config.exactSolverMaxCandidates, true);
    setInt("randomized_repetitions", config.randomizedRepetitions);

    const auto seed = root.object.find("random_seed");
    if (seed != root.object.end()) {
        config.randomSeed = static_cast<uint64_t>(
            positiveInteger(seed->second, "random_seed", true));
    }
    const auto algorithms = root.object.find("algorithms");
    if (algorithms != root.object.end()) {
        config.algorithms = stringArray(algorithms->second, "algorithms");
    }
    const auto parameters = root.object.find("algorithm_parameters");
    if (parameters != root.object.end()) {
        if (parameters->second.type != json::Value::OBJECT) {
            throw std::runtime_error("algorithm_parameters must be an object");
        }
        for (const auto& item : parameters->second.object) {
            if (item.first == "lns_iterations") {
                config.algorithmParameters.lnsIterations =
                    positiveInteger(item.second, "algorithm_parameters.lns_iterations", true);
            } else if (item.first == "lns_max_anchors") {
                config.algorithmParameters.lnsMaxAnchors =
                    positiveInteger(item.second, "algorithm_parameters.lns_max_anchors");
            } else if (item.first == "lns_max_move_anchors") {
                config.algorithmParameters.lnsMaxMoveAnchors =
                    positiveInteger(item.second, "algorithm_parameters.lns_max_move_anchors");
            } else if (item.first == "tsp_max_anchors") {
                config.algorithmParameters.tspMaxAnchors =
                    positiveInteger(item.second, "algorithm_parameters.tsp_max_anchors");
            } else if (item.first == "two_opt_passes") {
                config.algorithmParameters.twoOptPasses =
                    positiveInteger(item.second, "algorithm_parameters.two_opt_passes", true);
            } else {
                throw std::runtime_error("unsupported algorithm parameter: " + item.first);
            }
        }
    }
    const auto tiers = root.object.find("difficulty_tier_filter");
    if (tiers != root.object.end()) {
        config.difficultyTierFilter = stringArray(tiers->second, "difficulty_tier_filter");
    }
    const auto policy = root.object.find("exact_solving_policy");
    if (policy != root.object.end()) {
        if (policy->second.type != json::Value::STRING) {
            throw std::runtime_error("exact_solving_policy must be a string");
        }
        config.exactSolvingPolicy = policy->second.string;
    }
    const auto portfolio = root.object.find("heuristic_portfolio");
    if (portfolio != root.object.end()) {
        config.heuristicPortfolio = stringArray(portfolio->second, "heuristic_portfolio");
    }
    const auto output = root.object.find("output_directory");
    if (output != root.object.end()) {
        if (output->second.type != json::Value::STRING || output->second.string.empty()) {
            throw std::runtime_error("output_directory must be a nonempty string");
        }
        config.outputDirectory = output->second.string;
    }
    const auto verbosity = root.object.find("logging_verbosity");
    if (verbosity != root.object.end()) {
        if (verbosity->second.type != json::Value::STRING) {
            throw std::runtime_error("logging_verbosity must be a string");
        }
        config.loggingVerbosity = verbosity->second.string;
    }
    const auto overwrite = root.object.find("overwrite_existing");
    if (overwrite != root.object.end()) {
        requireBoolean(overwrite->second, config.overwriteExisting, "overwrite_existing");
    }
    const auto official = root.object.find("official_validation");
    if (official != root.object.end()) {
        requireBoolean(official->second, config.officialValidation, "official_validation");
    }
}

std::string quote(const std::string& value) {
    return json::escapeString(value);
}

std::string stringArrayJson(const std::vector<std::string>& values) {
    std::string result = "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i != 0U) result += ',';
        result += quote(values[i]);
    }
    return result + "]";
}

std::string fieldsJson(const RuntimeConfig& config) {
    const std::string deadline = config.globalRunDeadlineSeconds < 0.0
                                     ? "null"
                                     : std::to_string(config.globalRunDeadlineSeconds);
    return "{"
           "\"solver_mode\":" + quote(config.solverMode) +
           ","
           "\"global_run_deadline_seconds\":" + deadline +
           ",\"per_instance_timeout_seconds\":" +
           std::to_string(config.perInstanceTimeoutSeconds) +
           ",\"per_algorithm_timeout_seconds\":" +
           std::to_string(config.perAlgorithmTimeoutSeconds) +
           ",\"ip_kont_timeout_seconds\":" + std::to_string(config.ipKontTimeoutSeconds) +
           ",\"threads_per_solver\":" + std::to_string(config.threadsPerSolver) +
           ",\"benchmark_jobs\":" + std::to_string(config.benchmarkJobs) +
           ",\"memory_limit_mib\":" + std::to_string(config.memoryLimitMiB) +
           ",\"random_seed\":" + std::to_string(config.randomSeed) +
           ",\"algorithms\":" + stringArrayJson(config.algorithms) +
           ",\"algorithm_parameters\":{\"lns_iterations\":" +
           std::to_string(config.algorithmParameters.lnsIterations) +
           ",\"lns_max_anchors\":" +
           std::to_string(config.algorithmParameters.lnsMaxAnchors) +
           ",\"lns_max_move_anchors\":" +
           std::to_string(config.algorithmParameters.lnsMaxMoveAnchors) +
           ",\"tsp_max_anchors\":" +
           std::to_string(config.algorithmParameters.tspMaxAnchors) +
           ",\"two_opt_passes\":" +
           std::to_string(config.algorithmParameters.twoOptPasses) + "}" +
           ",\"difficulty_tier_filter\":" + stringArrayJson(config.difficultyTierFilter) +
           ",\"exact_solving_policy\":" + quote(config.exactSolvingPolicy) +
           ",\"exact_solver_max_candidates\":" +
           std::to_string(config.exactSolverMaxCandidates) +
           ",\"exact_solver_exploratory_time_budget_seconds\":" +
           std::to_string(config.exactSolverExploratoryTimeBudgetSeconds) +
           ",\"heuristic_portfolio\":" + stringArrayJson(config.heuristicPortfolio) +
           ",\"randomized_repetitions\":" +
           std::to_string(config.randomizedRepetitions) +
           ",\"output_directory\":" + quote(config.outputDirectory) +
           ",\"overwrite_existing\":" + (config.overwriteExisting ? "true" : "false") +
           ",\"logging_verbosity\":" + quote(config.loggingVerbosity) +
           ",\"official_validation\":" + (config.officialValidation ? "true" : "false") +
           ",\"effective_solver_timeout_seconds\":" +
           std::to_string(std::min(
               config.perInstanceTimeoutSeconds,
               std::min(config.perAlgorithmTimeoutSeconds,
                        config.globalRunDeadlineSeconds < 0.0
                            ? config.perInstanceTimeoutSeconds
                            : config.globalRunDeadlineSeconds))) +
           ",\"intended_max_active_solver_workers\":" +
           std::to_string(config.benchmarkJobs * config.threadsPerSolver) +
#if defined(__APPLE__)
           ",\"memory_enforcement\":\"not_enforced_directly; use_batch_process_tree_watchdog\"" +
#elif defined(_WIN32)
           ",\"memory_enforcement\":\"not_enforced_by_solver_process\"" +
#else
           ",\"memory_enforcement\":\"per_process_RLIMIT_AS\"" +
#endif
           "}";
}

}  // namespace

RuntimeConfig RuntimeConfig::load(const std::string& configPath) {
    RuntimeConfig config;
    applyJson(config, json::parseFile(CGSHOP_DEFAULT_CONFIG));
    if (!configPath.empty() && configPath != CGSHOP_DEFAULT_CONFIG) {
        applyJson(config, json::parseFile(configPath));
    }
    config.validate();
    return config;
}

void RuntimeConfig::validate() const {
    const auto modeConfig = json::parseFile(CGSHOP_SOLVER_MODES_CONFIG);
    if (modeConfig.type != json::Value::OBJECT ||
        modeConfig.object.count("canonical_modes") == 0U) {
        throw std::runtime_error("solver mode registry is malformed");
    }
    const auto& modes = modeConfig.object.at("canonical_modes");
    if (modes.type != json::Value::ARRAY) {
        throw std::runtime_error("solver mode registry canonical_modes must be an array");
    }
    bool recognizedMode = false;
    std::set<std::string> registeredModes;
    for (const auto& mode : modes.array) {
        if (mode.type != json::Value::STRING || mode.string.empty()) {
            throw std::runtime_error("solver mode registry contains an invalid mode");
        }
        if (!registeredModes.insert(mode.string).second) {
            throw std::runtime_error("solver mode registry contains duplicate modes");
        }
        recognizedMode = recognizedMode || mode.string == solverMode;
    }
    if (!recognizedMode) {
        throw std::runtime_error("unsupported solver mode: " + solverMode);
    }
    const auto validTimeout = [](double value) {
        return std::isfinite(value) && value >= 0.0 &&
               value <= kMaximumTimeoutSeconds;
    };
    if (globalRunDeadlineSeconds != -1.0 && !validTimeout(globalRunDeadlineSeconds)) {
        throw std::runtime_error(
            "global_run_deadline_seconds must be null or between 0 and 31536000");
    }
    if (!validTimeout(perInstanceTimeoutSeconds) ||
        !validTimeout(perAlgorithmTimeoutSeconds) || !validTimeout(ipKontTimeoutSeconds)) {
        throw std::runtime_error("timeout values must be between 0 and 31536000 seconds");
    }
    if (threadsPerSolver != 1) {
        throw std::runtime_error("threads_per_solver must be 1; solver algorithms are single-threaded");
    }
    if (algorithmParameters.lnsIterations < 0 ||
        algorithmParameters.lnsIterations > 100000 ||
        algorithmParameters.lnsMaxAnchors < 1 ||
        algorithmParameters.lnsMaxMoveAnchors < 1 ||
        algorithmParameters.lnsMaxMoveAnchors > algorithmParameters.lnsMaxAnchors) {
        throw std::runtime_error(
            "LNS settings require iterations in [0,100000], positive anchor limits, "
            "and lns_max_move_anchors <= lns_max_anchors");
    }
    if (benchmarkJobs < 1 || memoryLimitMiB < 1 || randomizedRepetitions < 1 ||
        randomizedRepetitions > 1000) {
        throw std::runtime_error(
            "benchmark_jobs and memory_limit_mib must be positive; "
            "randomized_repetitions must be between 1 and 1000");
    }
    static const std::set<std::string> algorithmNames{
        "strip", "partition", "local", "anchor-cover", "anchor",
        "balanced-greedy", "greedy", "boustrophedon", "a1", "zigzag",
        "stc", "a2", "tsp-cov", "tsp_cov", "a3", "frederickson", "b1",
        "mstc", "b2", "region-partition", "b3", "ilp", "c1",
        "connected-growth", "column-gen",
        "c2", "bap", "lns", "d1", "hybrid", "e"};
    if (algorithms.empty()) throw std::runtime_error("algorithms must not be empty");
    if (std::set<std::string>(algorithms.begin(), algorithms.end()).size() !=
        algorithms.size()) {
        throw std::runtime_error("algorithms must not contain duplicates");
    }
    for (const auto& name : algorithms) {
        if (algorithmNames.count(name) == 0U) {
            throw std::runtime_error("unsupported algorithm name: " + name);
        }
    }
    if (difficultyTierFilter != std::vector<std::string>{"all"}) {
        throw std::runtime_error(
            "difficulty_tier_filter only supports [\"all\"] until a validated tier classifier exists");
    }
    if (exactSolvingPolicy != "disabled" && exactSolvingPolicy != "ip_kont_surrogate") {
        throw std::runtime_error(
            "exact_solving_policy must be disabled or ip_kont_surrogate; IP-KONT does not solve the exact route objective");
    }
    if (exactSolvingPolicy == "disabled" && exactSolverMaxCandidates != 0) {
        throw std::runtime_error(
            "exact_solver_max_candidates requires exact_solving_policy=ip_kont_surrogate");
    }
    if (exactSolverExploratoryTimeBudgetSeconds != 0.0) {
        throw std::runtime_error(
            "exact_solver_exploratory_time_budget_seconds is unsupported until difficulty tiers are classified");
    }
    static const std::set<std::string> portfolioNames{
        "boustrophedon", "stc", "frederickson", "mstc", "region-partition",
        "connected-growth", "column-gen", "tsp-cov"};
    if (heuristicPortfolio.empty()) {
        throw std::runtime_error("heuristic_portfolio must not be empty");
    }
    std::set<std::string> seen;
    for (const auto& name : heuristicPortfolio) {
        if (portfolioNames.count(name) == 0U || !seen.insert(name).second) {
            throw std::runtime_error("heuristic_portfolio contains an unsupported or duplicate algorithm: " + name);
        }
    }
    static const std::set<std::string> levels{"debug", "info", "warning", "error"};
    if (levels.count(loggingVerbosity) == 0U) {
        throw std::runtime_error("logging_verbosity must be debug, info, warning, or error");
    }
    if (outputDirectory.empty()) {
        throw std::runtime_error("output_directory must not be empty");
    }
    if (randomizedRepetitions > 1 &&
        std::none_of(algorithms.begin(), algorithms.end(), [](const std::string& name) {
            return name == "local" || name == "lns" || name == "d1" ||
                   name == "hybrid" || name == "e";
        })) {
        throw std::runtime_error(
            "randomized_repetitions > 1 requires local, lns, or hybrid in algorithms");
    }
}

std::string RuntimeConfig::toJson(const RuntimeConfig& requested) const {
    return "{\n  \"requested\": " + fieldsJson(requested) +
           ",\n  \"effective\": " + fieldsJson(*this) + "\n}\n";
}

const RuntimeConfig& runtimeConfig() { return activeConfig; }

void setRuntimeConfig(const RuntimeConfig& config) { activeConfig = config; }

}  // namespace cgshop2027
