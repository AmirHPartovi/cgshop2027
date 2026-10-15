cmake_minimum_required(VERSION 3.16)
project(cgshop2027_solver LANGUAGES CXX)

find_program(KONT_CMD_EXECUTABLE
    NAMES kont_cmd
    PATHS /Applications/kont72/bin
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

set(CORE_SOURCES
    src/core/Point.cpp
    src/core/Polyomino.cpp
    src/core/GeometryUtils.cpp
    src/core/Problem.cpp
    src/core/Solution.cpp
    src/io/InstanceReader.cpp
    src/io/SolutionWriter.cpp
)
set(UTIL_SOURCES src/utils/Logger.cpp)
set(ALGORITHM_SOURCES
    src/algorithms/BaseAlgorithm.cpp
    src/algorithms/TourConstruction.cpp
    src/algorithms/StripAlgorithm.cpp
    src/algorithms/PartitioningAlgorithm.cpp
    src/algorithms/LocalSearch.cpp
    src/algorithms/AnchorCoverAlgorithm.cpp
    src/algorithms/BalancedGreedyRouteAlgorithm.cpp
    src/algorithms/BoustrophedonAlgorithm.cpp
    src/algorithms/StcAlgorithm.cpp
    src/algorithms/TspCovAlgorithm.cpp
    src/algorithms/FredericksonSplitAlgorithm.cpp
    src/algorithms/MstcAlgorithm.cpp
    src/algorithms/RegionPartitionAssignAlgorithm.cpp
    src/algorithms/IlpAlgorithm.cpp
    src/algorithms/ColumnGenerationAlgorithm.cpp
    src/algorithms/LnsMultiCutterAlgorithm.cpp
    src/algorithms/HybridSolver.cpp
)

add_library(cgshop_core ${CORE_SOURCES} ${UTIL_SOURCES} ${ALGORITHM_SOURCES})
target_include_directories(cgshop_core PUBLIC src)
target_compile_definitions(cgshop_core PUBLIC CGSHOP_PROJECT_SOURCE_DIR="${CMAKE_SOURCE_DIR}")
if(KONT_CMD_EXECUTABLE)
    target_compile_definitions(cgshop_core PRIVATE
        CGSHOP_KONT_CMD="${KONT_CMD_EXECUTABLE}"
    )
endif()

add_executable(solver src/main.cpp)
target_link_libraries(solver PRIVATE cgshop_core)

enable_testing()
add_subdirectory(tests)
