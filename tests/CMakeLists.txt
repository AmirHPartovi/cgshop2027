add_executable(test_geometry test_geometry.cpp)
target_link_libraries(test_geometry PRIVATE cgshop_core)
target_compile_options(test_geometry PRIVATE -UNDEBUG)
add_test(NAME geometry COMMAND test_geometry)

add_executable(test_algorithms test_algorithms.cpp)
target_link_libraries(test_algorithms PRIVATE cgshop_core)
target_compile_options(test_algorithms PRIVATE -UNDEBUG)
add_test(NAME algorithms COMMAND test_algorithms)

add_executable(test_io test_io.cpp)
target_link_libraries(test_io PRIVATE cgshop_core)
target_compile_options(test_io PRIVATE -UNDEBUG)
add_test(NAME io COMMAND test_io)
