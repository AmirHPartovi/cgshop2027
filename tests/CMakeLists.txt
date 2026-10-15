add_executable(test_geometry test_geometry.cpp)
target_link_libraries(test_geometry PRIVATE cgshop_core)
target_compile_options(test_geometry PRIVATE -UNDEBUG)
add_test(NAME geometry COMMAND test_geometry)

add_executable(test_algorithms test_algorithms.cpp)
target_link_libraries(test_algorithms PRIVATE cgshop_core)
target_compile_options(test_algorithms PRIVATE -UNDEBUG)
target_compile_definitions(test_algorithms PRIVATE
    CGSHOP_TEST_FIXTURE_DIR="${PROJECT_SOURCE_DIR}/tests/fixtures"
)
add_test(NAME algorithms COMMAND test_algorithms)

add_executable(test_io test_io.cpp)
target_link_libraries(test_io PRIVATE cgshop_core)
target_compile_options(test_io PRIVATE -UNDEBUG)
target_compile_definitions(test_io PRIVATE
    CGSHOP_TEST_FIXTURE_DIR="${PROJECT_SOURCE_DIR}/tests/fixtures"
)
add_test(NAME io COMMAND test_io)

add_executable(test_execution_control test_execution_control.cpp)
target_link_libraries(test_execution_control PRIVATE cgshop_core)
target_compile_options(test_execution_control PRIVATE -UNDEBUG)
add_test(NAME execution_control COMMAND test_execution_control)

add_executable(internal_solution_check internal_solution_check.cpp)
target_link_libraries(internal_solution_check PRIVATE cgshop_core)
target_compile_options(internal_solution_check PRIVATE -UNDEBUG)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
    add_test(
        NAME solution_metrics
        COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_solution_metrics.py
    )
    add_test(
        NAME runtime_config
        COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_runtime_config.py
    )
    add_test(
        NAME instance_profiler
        COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_instance_profiler.py
    )
    add_test(
        NAME solver_policy
        COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_solver_policy.py
    )
    add_test(
        NAME reference_comparison
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_reference_comparison.py
    )
    add_test(
        NAME benchmark_resources
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_benchmark_resources.py
    )
    add_test(
        NAME benchmark_cli
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_benchmark_cli.py
                $<TARGET_FILE:solver>
    )
    add_test(
        NAME benchmark_reports
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_benchmark_reports.py
    )
    add_test(
        NAME visualization
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_visualization.py
                $<TARGET_FILE:internal_solution_check>
    )
    add_test(
        NAME auto_solve_cli
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_auto_solve_cli.py
                $<TARGET_FILE:solver>
    )
    add_test(
        NAME runtime_config_cli
        COMMAND ${Python3_EXECUTABLE}
                ${PROJECT_SOURCE_DIR}/tests/test_runtime_config_cli.py
                $<TARGET_FILE:solver>
                ${PROJECT_SOURCE_DIR}/tests/fixtures/instances/tiny-square.instance.json
    )
endif()
