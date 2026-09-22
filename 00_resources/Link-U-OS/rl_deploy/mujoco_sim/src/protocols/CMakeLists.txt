# ros2 msg
add_subdirectory(joint_msgs)

# protobuf code generation
file(GLOB_RECURSE PROTO_FILES "${CMAKE_CURRENT_SOURCE_DIR}/aimdk/protocol/*.proto")

set(PROTO_SRCS "")
set(PROTO_HDRS "")
foreach(PROTO_FILE ${PROTO_FILES})
  get_filename_component(PROTO_NAME ${PROTO_FILE} NAME_WE)
  get_filename_component(PROTO_PATH ${PROTO_FILE} PATH)
  file(RELATIVE_PATH PROTO_REL_PATH ${CMAKE_CURRENT_SOURCE_DIR} ${PROTO_PATH})
  if(PROTO_REL_PATH)
    set(PROTO_SRC "${CMAKE_CURRENT_BINARY_DIR}/${PROTO_REL_PATH}/${PROTO_NAME}.pb.cc")
    set(PROTO_HDR "${CMAKE_CURRENT_BINARY_DIR}/${PROTO_REL_PATH}/${PROTO_NAME}.pb.h")
  else()
    set(PROTO_SRC "${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME}.pb.cc")
    set(PROTO_HDR "${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME}.pb.h")
  endif()

  list(APPEND PROTO_SRCS ${PROTO_SRC})
  list(APPEND PROTO_HDRS ${PROTO_HDR})

  add_custom_command(
    OUTPUT ${PROTO_SRC} ${PROTO_HDR}
    COMMAND $<TARGET_FILE:protobuf::protoc> --cpp_out=${CMAKE_CURRENT_BINARY_DIR} --proto_path=${CMAKE_CURRENT_SOURCE_DIR} ${PROTO_FILE}
    DEPENDS ${PROTO_FILE} protobuf::protoc
    COMMENT "Generating C++ code from ${PROTO_FILE}"
    VERBATIM)
endforeach()

add_library(aimdk_protocol STATIC)

target_sources(aimdk_protocol PRIVATE ${PROTO_SRCS})
target_sources(aimdk_protocol PUBLIC FILE_SET HEADERS BASE_DIRS ${CMAKE_CURRENT_BINARY_DIR} FILES ${PROTO_HDRS})
target_include_directories(
  aimdk_protocol
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
         $<INSTALL_INTERFACE:include/aimdk_protocol>)
target_link_libraries(
  aimdk_protocol
  PUBLIC protobuf::libprotobuf)
