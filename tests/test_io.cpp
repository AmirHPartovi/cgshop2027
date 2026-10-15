#include "algorithms/PartitioningAlgorithm.h"
#include "io/InstanceReader.h"
#include "io/Json.h"
#include "io/SolutionReader.h"
#include "io/SolutionWriter.h"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

#ifndef CGSHOP_TEST_FIXTURE_DIR
#error "CGSHOP_TEST_FIXTURE_DIR must point to the checked-in test fixtures"
#endif

namespace {

const std::filesystem::path kFixtures(CGSHOP_TEST_FIXTURE_DIR);

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Function>
void requireThrows(Function&& function, const std::string& message) {
    try {
        function();
    } catch (const std::exception&) {
        return;
    }
    throw std::runtime_error(message);
}

void writeSolutionJson(const std::filesystem::path& path, const std::string& uid,
                       const std::string& tours,
                       const std::string& contentType = "CGSHOP2027_Solution") {
    std::ofstream output(path, std::ios::binary);
    output << "{\"content_type\":" << cgshop2027::json::escapeString(contentType)
           << ",\"instance_uid\":" << cgshop2027::json::escapeString(uid)
           << ",\"tours\":" << tours << "}\n";
    require(static_cast<bool>(output), "could not write temporary solution fixture");
}

std::filesystem::path temporaryPath(const std::string& suffix) {
    return std::filesystem::temp_directory_path() /
        ("cgshop2027-test-io-" +
         std::to_string(std::chrono::high_resolution_clock::now()
                            .time_since_epoch()
                            .count()) +
         suffix);
}

}  // namespace

int main() {
    try {
        const auto single = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/tiny-single.instance.json").string());
        require(single->regionArea() == 1, "tiny single-cell fixture area mismatch");

        const auto stationary = cgshop2027::SolutionReader::readSolution(
            (kFixtures / "solutions/tiny-single.solution.json").string(), *single);
        require(cgshop2027::closedTourLength(stationary.tours.front().points) == 0,
                "stationary one-point tour should have zero closed length");

        const auto square = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/tiny-square.instance.json").string());
        const auto known = cgshop2027::SolutionReader::readSolution(
            (kFixtures / "solutions/tiny-square.solution.json").string(), *square);
        require(cgshop2027::closedTourLength(known.tours.front().points) == 4,
                "known square solution makespan should be 4");
        require(cgshop2027::solutionMakespan(known) == 4,
                "known square solution objective should be 4");
        std::string error;
        auto collinearBoundary = *square;
        collinearBoundary.outerBoundary.insert(
            collinearBoundary.outerBoundary.begin() + 1, {1, 0});
        error.clear();
        require(collinearBoundary.validate(&error),
                "valid consecutive collinear boundary edge rejected: " + error);
        auto manyVertices = *square;
        manyVertices.outerBoundary = {{0, 0}, {0, 2}};
        int top = 2;
        constexpr int kColumns = 10000;
        for (int x = 1; x <= kColumns; ++x) {
            manyVertices.outerBoundary.push_back({x, top});
            if (x < kColumns) {
                top = top == 2 ? 1 : 2;
                manyVertices.outerBoundary.push_back({x, top});
            }
        }
        manyVertices.outerBoundary.push_back({kColumns, 0});
        std::reverse(manyVertices.outerBoundary.begin(),
                     manyVertices.outerBoundary.end());
        error.clear();
        require(manyVertices.validate(&error),
                "large simple orthogonal ring rejected: " + error);
        require(cgshop2027::json::integer(
                    cgshop2027::json::Parser("1.0").parse(), "integer fixture") == 1 &&
                    cgshop2027::json::integer(
                        cgshop2027::json::Parser("1e0").parse(),
                        "integer fixture") == 1,
                "integer-valued decimal/exponent JSON number rejected");
        requireThrows(
            [] {
                (void)cgshop2027::json::integer(
                    cgshop2027::json::Parser("1.5").parse(), "fractional fixture");
            },
            "fractional JSON number was accepted as an integer");

        const auto hole = cgshop2027::InstanceReader::readInstance(
            (kFixtures / "instances/tiny-hole-multicutter.instance.json").string());
        require(hole->numberOfCutters == 2,
                "hole fixture should have multiple cutters");
        require(hole->regionArea() == 8,
                "hole fixture should rasterize to eight cells");
        const auto partition = cgshop2027::PartitioningAlgorithm(*hole).solve();
        require(partition.validate(*hole, &error),
                "partition candidate for hole fixture rejected: " + error);

        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    (kFixtures / "solutions/invalid-nonrectilinear.solution.json")
                        .string(),
                    *square);
            },
            "non-rectilinear solution was unexpectedly accepted");

        requireThrows(
            [&] {
                (void)cgshop2027::InstanceReader::readInstance(
                    (kFixtures / "invalid/invalid-content-type.json").string());
            },
            "invalid instance content_type was unexpectedly accepted");
        requireThrows(
            [&] {
                (void)cgshop2027::InstanceReader::readInstance(
                    (kFixtures / "invalid/malformed.json").string());
            },
            "malformed instance JSON was unexpectedly accepted");
        for (const std::string& invalidInstance : {
                 "invalid/missing-inner-boundaries.instance.json",
                 "invalid/self-intersecting.instance.json",
                 "invalid/fractional-coordinate.instance.json",
                 "invalid/overlapping-holes.instance.json"}) {
            requireThrows(
                [&] {
                    (void)cgshop2027::InstanceReader::readInstance(
                        (kFixtures / invalidInstance).string());
                },
                "invalid instance unexpectedly accepted: " + invalidInstance);
        }
        requireThrows(
            [&] {
                (void)cgshop2027::InstanceReader::readInstance(
                    (kFixtures / "instances/does-not-exist.instance.json").string());
            },
            "missing instance file was unexpectedly accepted");

        const std::string escapedUid = "uid\"with\\escapes\n\tand \xc3\xa9";
        auto escapedProblem = *square;
        escapedProblem.instanceUid = escapedUid;
        auto escapedSolution = known;
        escapedSolution.instanceUid = escapedUid;
        escapedSolution.meta["key\"\n"] = "value\\\t";
        escapedSolution.rawMetaJson["number"] = "17";
        escapedSolution.rawMetaJson["nested"] = "{\"enabled\":true,\"items\":[1,\"x\"]}";
        const auto output = temporaryPath(".solution.json");
        cgshop2027::SolutionWriter::write(escapedSolution, escapedProblem,
                                          output.string());
        const auto serialized = cgshop2027::json::parseFile(output.string());
        require(serialized.at("instance_uid").string == escapedUid,
                "solution UID JSON escaping did not round-trip");
        require(serialized.at("meta").at("key\"\n").string == "value\\\t",
                "solution metadata JSON escaping did not round-trip");
        require(serialized.at("meta").at("number").number == 17,
                "numeric metadata did not serialize as JSON");
        require(serialized.at("meta").at("nested").at("enabled").boolean,
                "object metadata did not serialize as JSON");
        const auto roundTrip = cgshop2027::SolutionReader::readSolution(
            output.string(), escapedProblem);
        require(roundTrip.instanceUid == escapedUid,
                "solution parser did not recover escaped instance UID");
        require(cgshop2027::solutionMakespan(roundTrip) == 4,
                "round-trip objective changed");
        const auto outputAgain = temporaryPath("-roundtrip.solution.json");
        cgshop2027::SolutionWriter::write(roundTrip, escapedProblem,
                                          outputAgain.string());
        const auto serializedAgain = cgshop2027::json::parseFile(outputAgain.string());
        require(serializedAgain.at("meta").at("nested").at("items").array.size() == 2U,
                "non-string metadata was not preserved by solution parsing");

        const auto mismatch = temporaryPath("-uid.solution.json");
        writeSolutionJson(mismatch, "wrong-uid",
                          "[{\"x\":[0,2,2,0],\"y\":[0,0,2,2]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    mismatch.string(), *square);
            },
            "UID-mismatched solution was unexpectedly accepted");

        const auto wrongCount = temporaryPath("-count.solution.json");
        writeSolutionJson(wrongCount, hole->instanceUid,
                          "[{\"x\":[0],\"y\":[0]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    wrongCount.string(), *hole);
            },
            "solution with wrong cutter count was unexpectedly accepted");

        const auto uncovered = temporaryPath("-coverage.solution.json");
        writeSolutionJson(uncovered, square->instanceUid,
                          "[{\"x\":[20],\"y\":[20]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    uncovered.string(), *square);
            },
            "solution with invalid coverage was unexpectedly accepted");

        const auto invalidTour = temporaryPath("-closed-edge.solution.json");
        writeSolutionJson(invalidTour, square->instanceUid,
                          "[{\"x\":[0,2,2,0,0],\"y\":[0,0,2,2,0]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    invalidTour.string(), *square);
            },
            "solution with repeated closing point was unexpectedly accepted");

        const auto emptyTour = temporaryPath("-empty-tour.solution.json");
        writeSolutionJson(emptyTour, square->instanceUid,
                          "[{\"x\":[],\"y\":[]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    emptyTour.string(), *square);
            },
            "empty tour was unexpectedly accepted");

        const auto fractionalTour = temporaryPath("-fractional-tour.solution.json");
        writeSolutionJson(fractionalTour, square->instanceUid,
                          "[{\"x\":[0.5],\"y\":[0]}]");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    fractionalTour.string(), *square);
            },
            "fractional tour coordinate was unexpectedly accepted");

        const auto invalidContentType = temporaryPath("-content-type.solution.json");
        writeSolutionJson(invalidContentType, square->instanceUid,
                          "[{\"x\":[0,2,2,0],\"y\":[0,0,2,2]}]",
                          "CGSHOP2027.solution");
        requireThrows(
            [&] {
                (void)cgshop2027::SolutionReader::readSolution(
                    invalidContentType.string(), *square);
            },
            "solution with unofficial content_type was unexpectedly accepted");

        cgshop2027::Solution invalidOutput = known;
        invalidOutput.contentType = "wrong";
        requireThrows(
            [&] {
                cgshop2027::SolutionWriter::write(invalidOutput, *square,
                                                  output.string());
            },
            "writer accepted a solution with invalid content_type");
        std::filesystem::remove(output);
        std::filesystem::remove(outputAgain);
        std::filesystem::remove(mismatch);
        std::filesystem::remove(wrongCount);
        std::filesystem::remove(uncovered);
        std::filesystem::remove(invalidTour);
        std::filesystem::remove(emptyTour);
        std::filesystem::remove(fractionalTour);
        std::filesystem::remove(invalidContentType);
        std::cout << "canonical instance/solution validation, coverage, closed "
                     "length, escaping, and malformed input checks passed\n";
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << "test_io failed: " << exception.what() << '\n';
        return 1;
    }
}
