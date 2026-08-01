cmake_minimum_required(VERSION 3.22.1)
project(eira_jni LANGUAGES C)

add_library(eira_core SHARED IMPORTED)
set_target_properties(
    eira_core
    PROPERTIES IMPORTED_LOCATION
    "${CMAKE_CURRENT_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libeira_core.so"
)

add_library(eira_jni SHARED eira_jni.c)
target_compile_options(eira_jni PRIVATE -Wall -Wextra -Werror)
target_include_directories(
    eira_jni
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../crates/eira-core/include"
)
target_link_libraries(eira_jni PRIVATE eira_core)
