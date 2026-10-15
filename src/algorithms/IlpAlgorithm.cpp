#include "algorithms/IlpAlgorithm.h"
#include "algorithms/PartitioningAlgorithm.h"
#include "algorithms/TourConstruction.h"
#include "utils/Logger.h"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
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
};

std::vector<std::pair<int, std::vector<Point>>> columns(
    const std::vector<Point>& anchors) {
    std::map<int, std::vector<Point>> grouped;
    for (const Point point : anchors) {
        grouped[point.x].push_back(point);
    }
    return {grouped.begin(), grouped.end()};
}

int columnCost(const std::vector<Point>& points) {
    if (points.empty()) {
        return 0;
    }
    int low = points.front().y;
    int high = points.front().y;
    for (const Point point : points) {
        low = std::min(low, point.y);
        high = std::max(high, point.y);
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

bool runKont(const KontModelFiles& files, double timeoutSeconds) {
#ifdef CGSHOP_KONT_CMD
    std::ofstream script(files.script);
    if (!script) {
        return false;
    }
    script << "readlp " << files.model.string() << "\n"
           << "opt\n"
           << "writesol " << files.solution.string() << "\n"
           << "quit\n";
    script.close();

    const pid_t child = fork();
    if (child < 0) {
        return false;
    }
    if (child == 0) {
        const int nullDevice = open("/dev/null", O_WRONLY);
        if (nullDevice >= 0) {
            dup2(nullDevice, STDOUT_FILENO);
            dup2(nullDevice, STDERR_FILENO);
            close(nullDevice);
        }
        execl(CGSHOP_KONT_CMD, CGSHOP_KONT_CMD, "-i",
              files.script.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }

    const auto start = std::chrono::steady_clock::now();
    const double limit = timeoutSeconds < 0.0 ? 300.0 : timeoutSeconds;
    int status = 0;
    for (;;) {
        const pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) {
            break;
        }
        if (result < 0) {
            return false;
        }
        if (std::filesystem::exists(files.solution)) {
            kill(child, SIGKILL);
            waitpid(child, &status, 0);
            break;
        }
        const double elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();
        if (elapsed >= limit) {
            kill(child, SIGKILL);
            waitpid(child, &status, 0);
            return false;
        }
        usleep(10000);
    }
    return std::filesystem::exists(files.solution);
#else
    (void)files;
    (void)timeoutSeconds;
    return false;
#endif
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
    std::string name;
    double value = 0.0;
    while (input >> name >> value) {
        if (name.rfind("x_", 0) != 0 || value < 0.5) {
            continue;
        }
        std::istringstream parser(name.substr(2));
        int column = -1;
        int cutter = -1;
        char separator = '\0';
        if (!(parser >> column >> separator >> cutter) || separator != '_' ||
            column < 0 || cutter < 0 ||
            static_cast<size_t>(column) >= columnCount || cutter >= cutters) {
            continue;
        }
        assignment[static_cast<size_t>(cutter)].push_back(column);
    }
    size_t assigned = 0;
    for (const auto& group : assignment) {
        assigned += group.size();
    }
    return assigned == columnCount;
}

Solution solveWithKont(const Problem& problem, double timeoutSeconds) {
    const auto anchors = TourConstruction::coveringAnchors(problem);
    const auto strips = columns(anchors);
    const int cutters = problem.numberOfCutters;
    if (strips.empty() || cutters <= 0) {
        return {};
    }

    const auto base = std::filesystem::temp_directory_path() /
        ("cgshop_kont_" + std::to_string(static_cast<long long>(getpid())));
    const KontModelFiles files{base.string() + ".lp", base.string() + ".cmd",
                               base.string() + ".sol"};
    const bool modelWritten = writeKontModel(files.model, strips, cutters);
    if (!modelWritten || !runKont(files, timeoutSeconds)) {
        std::error_code ignored;
        std::filesystem::remove(files.model, ignored);
        std::filesystem::remove(files.script, ignored);
        std::filesystem::remove(files.solution, ignored);
        return {};
    }

    std::vector<std::vector<int>> assignment;
    const bool parsed = readKontAssignment(files.solution, strips.size(), cutters,
                                           assignment);
    std::error_code ignored;
    std::filesystem::remove(files.model, ignored);
    std::filesystem::remove(files.script, ignored);
    std::filesystem::remove(files.solution, ignored);
    if (!parsed) {
        return {};
    }

    std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
    for (int cutter = 0; cutter < cutters; ++cutter) {
        for (const int column : assignment[static_cast<size_t>(cutter)]) {
            const auto& points = strips[static_cast<size_t>(column)].second;
            groups[static_cast<size_t>(cutter)].insert(
                groups[static_cast<size_t>(cutter)].end(), points.begin(), points.end());
        }
        std::sort(groups[static_cast<size_t>(cutter)].begin(),
                  groups[static_cast<size_t>(cutter)].end());
    }
    return TourConstruction::makeSolution(problem, groups);
}

}  // namespace

Solution IlpAlgorithm::solve(double timeoutSeconds) {
    LogScope scope("algorithm.ilp", "solve");
    Solution solution = solveWithKont(problem_, timeoutSeconds);
    std::string error;
    if (!solution.validate(problem_, &error)) {
        Logger::instance().warning(
            "KONT ILP was unavailable or did not produce a feasible assignment; "
            "using the validated partition fallback (" + error + ")");
        solution = PartitioningAlgorithm(problem_).solve(timeoutSeconds);
        solution.meta["ilp_backend"] = "partition-fallback";
        return solution;
    }
    solution.meta["ilp_backend"] = "KONT";
    return solution;
}
}  // namespace cgshop2027
