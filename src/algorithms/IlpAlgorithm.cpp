#include "algorithms/IlpAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "core/ExecutionControl.h"
#include "core/RuntimeConfig.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
#include <iterator>
#include <map>
#include <signal.h>
#include <sstream>
#include <string>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace cgshop2027 {
namespace {

struct KontModelFiles {
    std::filesystem::path model;
    std::filesystem::path script;
    std::filesystem::path solution;
    std::filesystem::path log;
};

struct KontExecution {
    bool completed{false};
    bool timedOut{false};
    int exitCode{-1};
    double elapsedSeconds{0.0};
    std::string terminationReason{"not started"};
    std::string log;
};

struct KontResult {
    Solution solution;
    std::string status{"ERROR"};
    std::string rawStatus{"NOT_RUN"};
    std::string terminationReason;
    std::string log;
    double runtimeSeconds{0.0};
    int processExitCode{-1};
    size_t variableCount{0};
    size_t binaryVariableCount{0};
    size_t continuousVariableCount{0};
    size_t constraintCount{0};
    size_t assignmentConstraintCount{0};
    size_t loadConstraintCount{0};
    size_t columnCount{0};
    int64_t surrogateObjective{0};
    int64_t reconstructedMakespan{0};
    bool hasReconstructedCandidate{false};
    std::string modelName{"vertical_column_assignment_surrogate"};
};

std::vector<std::pair<int, std::vector<Point>>> columns(
    const std::vector<Point>& anchors) {
    std::map<int, std::vector<Point>> grouped;
    for (const Point point : anchors) {
        grouped[point.x].push_back(point);
    }
    return {grouped.begin(), grouped.end()};
}

int64_t columnCost(const std::vector<Point>& points) {
    if (points.empty()) {
        return 0;
    }
    int64_t low = points.front().y;
    int64_t high = points.front().y;
    for (const Point point : points) {
        low = std::min(low, static_cast<int64_t>(point.y));
        high = std::max(high, static_cast<int64_t>(point.y));
    }
    return 2 * (high - low) + 2;
}

bool writeKontModel(const std::filesystem::path& path,
                    const std::vector<std::pair<int, std::vector<Point>>>& strips,
                    int cutters) {
    std::ofstream model(path);
    if (!model) {
        return false;
    }
    model << "Minimize\n obj: z\nSubject To\n";
    for (size_t column = 0; column < strips.size(); ++column) {
        model << " assign_" << column << ":";
        for (int cutter = 0; cutter < cutters; ++cutter) {
            model << " + x_" << column << "_" << cutter;
        }
        model << " = 1\n";
    }
    for (int cutter = 0; cutter < cutters; ++cutter) {
        model << " load_" << cutter << ":";
        for (size_t column = 0; column < strips.size(); ++column) {
            model << " + " << columnCost(strips[column].second)
                  << " x_" << column << "_" << cutter;
        }
        model << " - z <= 0\n";
    }
    model << "Bounds\n z >= 0\nBinary\n";
    for (size_t column = 0; column < strips.size(); ++column) {
        for (int cutter = 0; cutter < cutters; ++cutter) {
            model << " x_" << column << "_" << cutter << "\n";
        }
    }
    model << "End\n";
    return model.good();
}

std::string readLog(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return {};
    }
    return std::string(std::istreambuf_iterator<char>(input),
                       std::istreambuf_iterator<char>());
}

std::string rawKontStatus(const std::string& log) {
    std::istringstream lines(log);
    std::string line;
    while (std::getline(lines, line)) {
        std::string lower = line;
        std::transform(lower.begin(), lower.end(), lower.begin(),
                       [](unsigned char ch) {
                           return static_cast<char>(std::tolower(ch));
                       });
        if (lower.find("optimal") != std::string::npos ||
            lower.find("infeasible") != std::string::npos ||
            lower.find("unbounded") != std::string::npos ||
            lower.find("time limit") != std::string::npos ||
            lower.find("timelimit") != std::string::npos ||
            lower.find("feasible") != std::string::npos) {
            return line;
        }
    }
    return "UNKNOWN";
}

bool kontReportedTimeLimit(const std::string& rawStatus) {
    std::string lower = rawStatus;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char ch) {
                       return static_cast<char>(std::tolower(ch));
                   });
    return lower.find("time limit") != std::string::npos ||
           lower.find("timelimit") != std::string::npos;
}

KontExecution runKont(const KontModelFiles& files, double timeoutSeconds) {
    KontExecution execution;
#ifdef CGSHOP_KONT_CMD
    std::ofstream script(files.script);
    if (!script) {
        execution.terminationReason = "could not create KONT command script";
        return execution;
    }
    script << "readlp " << files.model.string() << "\n"
           << "opt\n"
           << "writesol " << files.solution.string() << "\n"
           << "quit\n";
    script.close();
    if (!script) {
        execution.terminationReason = "failed writing KONT command script";
        return execution;
    }

    const pid_t child = fork();
    if (child < 0) {
        execution.terminationReason =
            std::string("fork failed: ") + std::strerror(errno);
        return execution;
    }
    if (child == 0) {
        (void)setpgid(0, 0);
        const int logFile = open(files.log.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (logFile < 0) {
            _exit(126);
        }
        dup2(logFile, STDOUT_FILENO);
        dup2(logFile, STDERR_FILENO);
        close(logFile);
        execl(CGSHOP_KONT_CMD, CGSHOP_KONT_CMD, "-i",
              files.script.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }

    (void)setpgid(child, child);
    ExecutionControl::instance().setActiveChildProcess(static_cast<int>(child));
    const auto start = std::chrono::steady_clock::now();
    const double limit = timeoutSeconds < 0.0 ? 300.0 : timeoutSeconds;
    int status = 0;
    const auto killChildTree = [child]() {
        (void)kill(-child, SIGKILL);
        (void)kill(child, SIGKILL);
    };
    for (;;) {
        const pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) {
            ExecutionControl::instance().setActiveChildProcess(0);
            execution.completed = true;
            if (WIFEXITED(status)) {
                execution.exitCode = WEXITSTATUS(status);
                execution.terminationReason =
                    "KONT process exited with code " +
                    std::to_string(execution.exitCode);
            } else if (WIFSIGNALED(status)) {
                execution.terminationReason =
                    "KONT process terminated by signal " +
                    std::to_string(WTERMSIG(status));
            } else {
                execution.terminationReason =
                    "KONT process ended with an unrecognized wait status";
            }
            break;
        }
        if (result < 0) {
            if (errno == EINTR) continue;
            execution.terminationReason =
                std::string("waitpid failed: ") + std::strerror(errno);
            killChildTree();
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
            break;
        }
        execution.elapsedSeconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();
        if (ExecutionControl::instance().cancelled() ||
            execution.elapsedSeconds >= limit) {
            execution.timedOut = true;
            execution.terminationReason =
                ExecutionControl::instance().cancelled()
                    ? "parent solver deadline reached"
                    : "KONT wall-clock limit exceeded (" +
                          std::to_string(limit) + " seconds)";
            killChildTree();
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
            break;
        }
        usleep(10000);
    }
    ExecutionControl::instance().setActiveChildProcess(0);
    execution.elapsedSeconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start).count();
    execution.log = readLog(files.log);
#else
    (void)files;
    (void)timeoutSeconds;
    execution.terminationReason = "KONT executable was not configured at build time";
#endif
    return execution;
}

bool readKontAssignment(const std::filesystem::path& solution,
                        size_t columnCount,
                        int cutters,
                        std::vector<std::vector<int>>& assignment) {
    std::ifstream input(solution);
    if (!input) {
        return false;
    }
    assignment.assign(static_cast<size_t>(cutters), {});
    std::vector<int> selectedCount(columnCount, 0);
    std::string line;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::string name;
        if (!(row >> name) || name.front() == '#') continue;
        if (name.rfind("x_", 0) != 0) continue;
        double value = 0.0;
        std::string trailingValue;
        if (!(row >> value) || (row >> trailingValue)) return false;
        if (!std::isfinite(value) || value < -1e-7 || value > 1.0 + 1e-7 ||
            std::abs(value - std::round(value)) > 1e-7) {
            return false;
        }
        std::istringstream parser(name.substr(2));
        int column = -1;
        int cutter = -1;
        char separator = '\0';
        std::string trailingName;
        if (!(parser >> column >> separator >> cutter) || separator != '_' ||
            (parser >> trailingName) || column < 0 || cutter < 0 ||
            static_cast<size_t>(column) >= columnCount || cutter >= cutters) {
            return false;
        }
        if (value < 0.5) {
            continue;
        }
        if (++selectedCount[static_cast<size_t>(column)] != 1) {
            return false;
        }
        assignment[static_cast<size_t>(cutter)].push_back(column);
    }
    return std::all_of(selectedCount.begin(), selectedCount.end(),
                       [](int count) { return count == 1; });
}

KontResult solveWithKont(const Problem& problem, double timeoutSeconds) {
    KontResult result;
    const auto anchors = TourConstruction::coveringAnchors(problem);
    const auto strips = columns(anchors);
    const auto& config = runtimeConfig();
    result.columnCount = strips.size();
    if (config.exactSolvingPolicy != "ip_kont_surrogate") {
        result.terminationReason =
            "IP-KONT surrogate disabled by exact_solving_policy";
        return result;
    }
    if (config.exactSolverMaxCandidates > 0 &&
        strips.size() > static_cast<size_t>(config.exactSolverMaxCandidates)) {
        result.terminationReason =
            "IP-KONT surrogate skipped by configured column safety limit";
        return result;
    }
    const int cutters = problem.numberOfCutters;
    if (strips.empty() || cutters <= 0) {
        result.status = "INVALID_OUTPUT";
        result.terminationReason = "surrogate model has no columns or cutters";
        return result;
    }
    result.variableCount = strips.size() * static_cast<size_t>(cutters) + 1U;
    result.binaryVariableCount =
        strips.size() * static_cast<size_t>(cutters);
    result.continuousVariableCount = 1U;
    result.constraintCount = strips.size() + static_cast<size_t>(cutters);
    result.assignmentConstraintCount = strips.size();
    result.loadConstraintCount = static_cast<size_t>(cutters);

    std::string temporaryPattern =
        (std::filesystem::temp_directory_path() /
         ("cgshop_kont_" + std::to_string(static_cast<long long>(getpid())) +
          "_XXXXXX")).string();
    std::vector<char> temporaryBuffer(temporaryPattern.begin(),
                                      temporaryPattern.end());
    temporaryBuffer.push_back('\0');
    char* createdDirectory = mkdtemp(temporaryBuffer.data());
    if (createdDirectory == nullptr) {
        result.terminationReason =
            std::string("could not create unique KONT temporary directory: ") +
            std::strerror(errno);
        return result;
    }
    const std::filesystem::path temporaryDirectory(createdDirectory);
    const auto base = temporaryDirectory / "model";
    const KontModelFiles files{base.string() + ".lp", base.string() + ".cmd",
                               base.string() + ".sol", base.string() + ".log"};
    if (!writeKontModel(files.model, strips, cutters)) {
        result.terminationReason = "failed writing IP-KONT surrogate model";
        std::error_code ignored;
        std::filesystem::remove(files.model, ignored);
        std::filesystem::remove(temporaryDirectory, ignored);
        return result;
    }
    const KontExecution execution = runKont(files, timeoutSeconds);
    result.runtimeSeconds = execution.elapsedSeconds;
    result.processExitCode = execution.exitCode;
    result.terminationReason = execution.terminationReason;
    result.log = execution.log;
    result.rawStatus = rawKontStatus(execution.log);
    if (execution.timedOut) {
        result.status = "TIME_LIMIT_NO_INCUMBENT";
    } else if (!execution.completed || execution.exitCode != 0) {
        result.status = "ERROR";
    } else if (!std::filesystem::is_regular_file(files.solution)) {
        result.status = "INVALID_OUTPUT";
        result.terminationReason += "; no complete solution file was produced";
    } else {
        std::vector<std::vector<int>> assignment;
        if (!readKontAssignment(files.solution, strips.size(), cutters, assignment)) {
            result.status = "INVALID_OUTPUT";
            result.terminationReason += "; assignment output was incomplete or malformed";
        } else {
            std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
            for (int cutter = 0; cutter < cutters; ++cutter) {
                for (const int column : assignment[static_cast<size_t>(cutter)]) {
                    const auto& points = strips[static_cast<size_t>(column)].second;
                    groups[static_cast<size_t>(cutter)].insert(
                        groups[static_cast<size_t>(cutter)].end(),
                        points.begin(), points.end());
                }
                std::sort(groups[static_cast<size_t>(cutter)].begin(),
                          groups[static_cast<size_t>(cutter)].end());
            }
            result.solution = TourConstruction::makeSolution(problem, groups);
            std::string validationError;
            if (result.solution.validate(problem, &validationError)) {
                result.status = kontReportedTimeLimit(result.rawStatus)
                    ? "TIME_LIMIT_WITH_INCUMBENT"
                    : "FEASIBLE_NOT_PROVEN";
                result.terminationReason +=
                    "; recovered route is feasible, but no original-objective proof exists";
                int64_t maximumLoad = 0;
                for (const auto& cutterColumns : assignment) {
                    int64_t load = 0;
                    for (const int column : cutterColumns) {
                        load += columnCost(strips[static_cast<size_t>(column)].second);
                    }
                    maximumLoad = std::max(maximumLoad, load);
                }
                result.surrogateObjective = maximumLoad;
                result.reconstructedMakespan = solutionMakespan(result.solution);
                result.hasReconstructedCandidate = true;
            } else {
                result.status = "INVALID_OUTPUT";
                result.terminationReason +=
                    "; recovered route failed validation: " + validationError;
                result.solution = {};
            }
        }
    }
    std::error_code ignored;
    std::filesystem::remove(files.model, ignored);
    std::filesystem::remove(files.script, ignored);
    std::filesystem::remove(files.solution, ignored);
    std::filesystem::remove(files.log, ignored);
    std::filesystem::remove(temporaryDirectory, ignored);
    return result;
}

void addKontMetadata(Solution& solution, const KontResult& result) {
    solution.meta["ip_kont_model"] = result.modelName;
    solution.meta["ip_kont_status"] = result.status;
    solution.meta["ip_kont_raw_status"] = result.rawStatus;
    solution.meta["ip_kont_termination_reason"] = result.terminationReason;
    solution.meta["ip_kont_solver_log"] = result.log;
    solution.meta["ip_kont_runtime_seconds"] = std::to_string(result.runtimeSeconds);
    solution.meta["ip_kont_process_exit_code"] =
        std::to_string(result.processExitCode);
    solution.meta["ip_kont_column_count"] = std::to_string(result.columnCount);
    solution.meta["ip_kont_variable_count"] = std::to_string(result.variableCount);
    solution.meta["ip_kont_binary_variable_count"] =
        std::to_string(result.binaryVariableCount);
    solution.meta["ip_kont_continuous_variable_count"] =
        std::to_string(result.continuousVariableCount);
    solution.meta["ip_kont_constraint_count"] = std::to_string(result.constraintCount);
    solution.meta["ip_kont_assignment_constraint_count"] =
        std::to_string(result.assignmentConstraintCount);
    solution.meta["ip_kont_load_constraint_count"] =
        std::to_string(result.loadConstraintCount);
    if (result.hasReconstructedCandidate) {
        solution.rawMetaJson["ip_kont_surrogate_assignment_objective"] =
            std::to_string(result.surrogateObjective);
        solution.rawMetaJson["ip_kont_reconstructed_makespan"] =
            std::to_string(result.reconstructedMakespan);
    }
    solution.meta["ip_kont_exact_for_original_objective"] = "false";
}

}  // namespace

Solution IlpAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.ilp", "solve");
    double kontTimeout = std::min(
        timeoutSeconds, runtimeConfig().ipKontTimeoutSeconds);
    if (timeoutSeconds >= 0.0 && kontTimeout >= timeoutSeconds) {
        kontTimeout = std::max(0.0, timeoutSeconds - 0.1);
    }
    const double parentRemaining =
        ExecutionControl::instance().remainingSeconds();
    if (parentRemaining >= 0.0) {
        kontTimeout = std::min(kontTimeout, parentRemaining);
    }
    KontResult result = solveWithKont(problem_, kontTimeout);
    Solution solution = std::move(result.solution);
    if (solution.tours.empty()) {
        std::string error = result.terminationReason;
        Logger::instance().warning(
            "KONT surrogate unavailable or did not produce a feasible route; "
            "using the validated partition fallback (" + error + ")");
        solution = PartitioningAlgorithm(problem_).solve(timeoutSeconds);
        solution.meta["ilp_backend"] = "partition-fallback";
        addKontMetadata(solution, result);
        solution.meta["requested_algorithm"] = "ilp";
        solution.meta["algorithm_implementation"] = "partition";
        solution.meta["candidate_source"] = "partition_fallback";
        solution.meta["fallback_algorithm"] = "partition";
        solution.meta["fallback_reason"] = error;
        return solution;
    }
    solution.meta["ilp_backend"] = "KONT";
    addKontMetadata(solution, result);
    solution.meta["requested_algorithm"] = "ilp";
    solution.meta["algorithm_implementation"] = "ip_kont_surrogate";
    solution.meta["candidate_source"] = "ip_kont_surrogate_incumbent";
    return solution;
}
}  // namespace cgshop2027
