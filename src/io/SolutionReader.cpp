#include "SolutionReader.h"

#include "Json.h"

#include <stdexcept>

namespace cgshop2027 {
namespace {

std::vector<Point> points(const json::Value& tour) {
    const auto& x = tour.at("x");
    const auto& y = tour.at("y");
    if (x.type != json::Value::ARRAY || y.type != json::Value::ARRAY) {
        throw std::runtime_error("tour x and y coordinates must be arrays");
    }
    if (x.array.size() != y.array.size()) {
        throw std::runtime_error("tour x/y coordinate lengths differ");
    }
    std::vector<Point> result;
    result.reserve(x.array.size());
    for (size_t i = 0; i < x.array.size(); ++i) {
        result.push_back({json::integer(x.array[i], "tour x coordinate"),
                          json::integer(y.array[i], "tour y coordinate")});
    }
    return result;
}

}  // namespace

Solution SolutionReader::readSolution(const std::string& filename,
                                      const Problem& problem) {
    const json::Value root = json::parseFile(filename);
    if (root.type != json::Value::OBJECT) {
        throw std::runtime_error("solution JSON root must be an object");
    }
    const auto& contentType = root.at("content_type");
    const auto& instanceUid = root.at("instance_uid");
    const auto& tours = root.at("tours");
    if (contentType.type != json::Value::STRING ||
        contentType.string != "CGSHOP2027_Solution") {
        throw std::runtime_error("unsupported solution content_type");
    }
    if (instanceUid.type != json::Value::STRING) {
        throw std::runtime_error("solution instance_uid must be a string");
    }
    if (tours.type != json::Value::ARRAY) {
        throw std::runtime_error("solution tours must be an array");
    }
    Solution solution;
    solution.contentType = contentType.string;
    solution.instanceUid = instanceUid.string;
    solution.tours.reserve(tours.array.size());
    for (const auto& item : tours.array) {
        solution.tours.push_back({points(item)});
    }
    const auto metadata = root.object.find("meta");
    if (metadata != root.object.end()) {
        if (metadata->second.type != json::Value::OBJECT) {
            throw std::runtime_error("solution meta must be an object");
        }
        for (const auto& item : metadata->second.object) {
            if (item.second.type == json::Value::STRING) {
                solution.meta.emplace(item.first, item.second.string);
            } else {
                solution.rawMetaJson.emplace(item.first, json::stringify(item.second));
            }
        }
    }
    std::string error;
    if (!solution.validate(problem, &error)) {
        throw std::runtime_error("invalid solution: " + error);
    }
    return solution;
}

}  // namespace cgshop2027
