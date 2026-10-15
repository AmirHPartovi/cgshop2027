#include "core/Solution.h"
#include "io/InstanceReader.h"
#include "io/Json.h"
#include "io/SolutionReader.h"

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: internal_solution_check INSTANCE SOLUTION\n";
        return 2;
    }

    std::unique_ptr<cgshop2027::Problem> problem;
    try {
        problem = cgshop2027::InstanceReader::readInstance(argv[1]);
    } catch (const std::exception& error) {
        std::cout << "{\"instance_valid\":false,\"solution_valid\":false,"
                     "\"instance_error\":"
                  << cgshop2027::json::escapeString(error.what()) << "}\n";
        return 0;
    }

    try {
        const auto solution =
            cgshop2027::SolutionReader::readSolution(argv[2], *problem);
        std::cout << "{\"instance_valid\":true,\"solution_valid\":true,"
                     "\"makespan\":"
                  << cgshop2027::solutionMakespan(solution) << "}\n";
    } catch (const std::exception& error) {
        std::cout << "{\"instance_valid\":true,\"solution_valid\":false,"
                     "\"solution_error\":"
                  << cgshop2027::json::escapeString(error.what()) << "}\n";
    }
    return 0;
}
