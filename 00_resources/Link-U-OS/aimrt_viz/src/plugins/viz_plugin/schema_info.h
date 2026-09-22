// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <google/protobuf/descriptor.h>
#include <google/protobuf/descriptor.pb.h>

#include <set>
#include <string>

#include "ros_storage.h"

namespace aimrt::plugins::viz_plugin {

namespace proto_identifier {

std::string GetIndentation(int level);
std::string GetFieldTypeName(const google::protobuf::FieldDescriptor* field, bool for_map_key = false);
std::string GetFieldLabel(const google::protobuf::FieldDescriptor* field);

void AppendFieldProtoSyntax(std::ostream& out, const google::protobuf::FieldDescriptor* field, int indent_level);

void AppendEnumProtoSyntax(std::ostream& out,
                           const google::protobuf::EnumDescriptor* enum_descriptor,
                           int indent_level,
                           std::set<const void*>& defined_elements,
                           const std::set<const google::protobuf::EnumDescriptor*>& related_enums);

void AppendMessageProtoSyntax(std::ostream& out,
                              const google::protobuf::Descriptor* message_descriptor,
                              int indent_level,
                              std::set<const void*>& defined_elements,
                              const std::set<const google::protobuf::Descriptor*>& related_messages,
                              const std::set<const google::protobuf::EnumDescriptor*>& related_enums);

void CollectRelatedTypes(const google::protobuf::Descriptor* desc,
                         std::set<const google::protobuf::Descriptor*>& messages,
                         std::set<const google::protobuf::EnumDescriptor*>& enums);

void CollectRelatedTypesFromField(const google::protobuf::FieldDescriptor* field,
                                  std::set<const google::protobuf::Descriptor*>& messages,
                                  std::set<const google::protobuf::EnumDescriptor*>& enums);

std::string BuildPbSchema(const google::protobuf::Descriptor* top_descriptor);

}  // namespace proto_identifier

namespace ros2_identifier {

std::string BuildRos2Schema(const MessageMembers* members, int indent);

}  // namespace ros2_identifier

}  // namespace aimrt::plugins::viz_plugin