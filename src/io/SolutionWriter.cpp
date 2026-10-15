#include "SolutionWriter.h"

#include "../core/Problem.h"
#include "Json.h"
#include "utils/Logger.h"

#include <filesystem>
#include <fstream>
#include <map>
#include <stdexcept>
#include <utility>

namespace cgshop2027 {

void SolutionWriter::write(const Solution& solution, const Problem& problem,
                           const std::string& filename) {
    std::string error;
    if (!solution.validate(problem, &error)) {
        throw std::runtime_error("refusing to write invalid solution: " + error);
    }
    std::map<std::string, std::pair<std::string, bool>> metadata;
    for (const auto& item : solution.meta) {
        metadata.emplace(item.first, std::make_pair(item.second, false));
    }
    for (const auto& item : solution.rawMetaJson) {
        if (!metadata.emplace(item.first, std::make_pair(item.second, true)).second) {
            throw std::runtime_error("solution metadata key appears in both representations");
        }
        json::Parser(item.second).parse();
    }

    LogScope scope("writer", "write solution");
    Logger::instance().info("writer", "writing output=" + filename +
                                      " tours=" + std::to_string(solution.tours.size()));
    const std::filesystem::path outputPath(filename);
    const auto parent = outputPath.parent_path();
    if (!parent.empty() && parent != ".") std::filesystem::create_directories(parent);

    std::ofstream output(filename, std::ios::binary);
    if (!output) throw std::runtime_error("cannot open " + filename);
    output << "{\n  \"content_type\": "
           << json::escapeString(solution.contentType)
           << ",\n  \"instance_uid\": "
           << json::escapeString(solution.instanceUid)
           << ",\n  \"tours\": [\n";
    for (size_t i = 0; i < solution.tours.size(); ++i) {
        const auto& points = solution.tours[i].points;
        output << "    {\"x\": [";
        for (size_t j = 0; j < points.size(); ++j) {
            if (j != 0U) output << ',';
            output << points[j].x;
        }
        output << "], \"y\": [";
        for (size_t j = 0; j < points.size(); ++j) {
            if (j != 0U) output << ',';
            output << points[j].y;
        }
        output << "]}" << (i + 1U < solution.tours.size() ? "," : "") << '\n';
    }
    output << "  ],\n  \"meta\": {";
    size_t itemIndex = 0;
    for (const auto& item : metadata) {
        if (itemIndex++ != 0U) output << ',';
        output << json::escapeString(item.first) << ": ";
        if (item.second.second) output << item.second.first;
        else output << json::escapeString(item.second.first);
    }
    output << "}\n}\n";
    if (!output) throw std::runtime_error("failed while writing " + filename);
    Logger::instance().info("writer", "solution write complete output=" + filename);
}

}  // namespace cgshop2027
