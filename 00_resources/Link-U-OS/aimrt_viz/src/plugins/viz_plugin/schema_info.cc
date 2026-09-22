// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <algorithm>
#include <queue>
#include <sstream>
#include <unordered_set>
#include <vector>

#include "schema_info.h"

#include "global.h"

namespace aimrt::plugins::viz_plugin {

namespace proto_identifier {

std::string GetIndentation(int level) {
  return std::string(level * 2, ' ');
}

std::string GetFieldTypeName(const google::protobuf::FieldDescriptor* field, bool for_map_key) {
  if (!for_map_key && field->is_map()) {
    const google::protobuf::Descriptor* map_entry_type = field->message_type();
    const google::protobuf::FieldDescriptor* key_field = map_entry_type->FindFieldByName("key");
    const google::protobuf::FieldDescriptor* value_field = map_entry_type->FindFieldByName("value");
    if (key_field && value_field) {
      return "map<" + GetFieldTypeName(key_field, true) + ", " + GetFieldTypeName(value_field, false) + ">";
    }
  }

  switch (field->type()) {
    case google::protobuf::FieldDescriptor::TYPE_DOUBLE:
      return "double";
    case google::protobuf::FieldDescriptor::TYPE_FLOAT:
      return "float";
    case google::protobuf::FieldDescriptor::TYPE_INT64:
      return "int64";
    case google::protobuf::FieldDescriptor::TYPE_UINT64:
      return "uint64";
    case google::protobuf::FieldDescriptor::TYPE_INT32:
      return "int32";
    case google::protobuf::FieldDescriptor::TYPE_FIXED64:
      return "fixed64";
    case google::protobuf::FieldDescriptor::TYPE_FIXED32:
      return "fixed32";
    case google::protobuf::FieldDescriptor::TYPE_BOOL:
      return "bool";
    case google::protobuf::FieldDescriptor::TYPE_STRING:
      return "string";
    case google::protobuf::FieldDescriptor::TYPE_GROUP:
      return std::string(field->message_type()->full_name());
    case google::protobuf::FieldDescriptor::TYPE_MESSAGE: {
      std::string name(field->message_type()->full_name());
      if (!name.empty() && name[0] == '.') {
        name.erase(0, 1);
      }
      return name;
    }
    case google::protobuf::FieldDescriptor::TYPE_BYTES:
      return "bytes";
    case google::protobuf::FieldDescriptor::TYPE_UINT32:
      return "uint32";
    case google::protobuf::FieldDescriptor::TYPE_ENUM: {
      std::string name(field->enum_type()->full_name());
      if (!name.empty() && name[0] == '.') {
        name.erase(0, 1);
      }
      return name;
    }
    case google::protobuf::FieldDescriptor::TYPE_SFIXED32:
      return "sfixed32";
    case google::protobuf::FieldDescriptor::TYPE_SFIXED64:
      return "sfixed64";
    case google::protobuf::FieldDescriptor::TYPE_SINT32:
      return "sint32";
    case google::protobuf::FieldDescriptor::TYPE_SINT64:
      return "sint64";
    default:
      return "UnknownType";
  }
}

std::string GetFieldLabel(const google::protobuf::FieldDescriptor* field) {
  if (field->is_repeated() && !field->is_map()) {
    return "repeated ";
  }
  if (field->is_optional() && !field->containing_oneof()) {
    return "optional ";
  }
  if (field->is_required()) {
    return "required ";
  }

  return "";
}

void AppendFieldProtoSyntax(std::ostream& out, const google::protobuf::FieldDescriptor* field, int indent_level) {
  out << GetIndentation(indent_level)
      << GetFieldLabel(field)
      << GetFieldTypeName(field, false) << " "
      << field->name() << " = " << field->number();

  if (field->has_default_value()) {
    out << " [default = ";
    switch (field->cpp_type()) {
      case google::protobuf::FieldDescriptor::CPPTYPE_INT32:
        out << field->default_value_int32();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_INT64:
        out << field->default_value_int64();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT32:
        out << field->default_value_uint32();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_UINT64:
        out << field->default_value_uint64();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_FLOAT:
        out << field->default_value_float();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_DOUBLE:
        out << field->default_value_double();
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_BOOL:
        out << (field->default_value_bool() ? "true" : "false");
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_STRING:
        out << "\"" << field->default_value_string() << "\"";
        break;
      case google::protobuf::FieldDescriptor::CPPTYPE_ENUM:
        out << field->default_value_enum()->name();
        break;
      default:
        out << "?";
        break;
    }
    out << "]";
  }
  out << ";\n";
}

void CollectRelatedTypesFromField(const google::protobuf::FieldDescriptor* field,
                                  std::set<const google::protobuf::Descriptor*>& messages,
                                  std::set<const google::protobuf::EnumDescriptor*>& enums) {
  if (!field) return;

  if (field->type() == google::protobuf::FieldDescriptor::TYPE_MESSAGE) {
    CollectRelatedTypes(field->message_type(), messages, enums);
  } else if (field->type() == google::protobuf::FieldDescriptor::TYPE_ENUM) {
    if (field->enum_type() && enums.find(field->enum_type()) == enums.end()) {
      enums.insert(field->enum_type());
    }
  }

  if (field->is_map()) {
    const google::protobuf::Descriptor* map_entry_type = field->message_type();

    const google::protobuf::FieldDescriptor* key_field = map_entry_type->FindFieldByName("key");
    const google::protobuf::FieldDescriptor* value_field = map_entry_type->FindFieldByName("value");
    CollectRelatedTypesFromField(key_field, messages, enums);
    CollectRelatedTypesFromField(value_field, messages, enums);
  }
}

void CollectRelatedTypes(const google::protobuf::Descriptor* desc,
                         std::set<const google::protobuf::Descriptor*>& messages,
                         std::set<const google::protobuf::EnumDescriptor*>& enums) {
  if (!desc || messages.count(desc)) {
    return;
  }
  messages.insert(desc);

  for (int i = 0; i < desc->field_count(); ++i) {
    CollectRelatedTypesFromField(desc->field(i), messages, enums);
  }

  for (int i = 0; i < desc->nested_type_count(); ++i) {
    CollectRelatedTypes(desc->nested_type(i), messages, enums);
  }

  for (int i = 0; i < desc->enum_type_count(); ++i) {
    if (desc->enum_type(i) && enums.find(desc->enum_type(i)) == enums.end()) {
      enums.insert(desc->enum_type(i));
    }
  }
}

void AppendEnumProtoSyntax(std::ostream& out,
                           const google::protobuf::EnumDescriptor* enum_descriptor,
                           int indent_level,
                           std::set<const void*>& defined_elements,
                           const std::set<const google::protobuf::EnumDescriptor*>& related_enums) {
  if (!enum_descriptor || !related_enums.count(enum_descriptor) || defined_elements.count(enum_descriptor)) {
    return;
  }
  defined_elements.insert(enum_descriptor);

  std::string indentStr = GetIndentation(indent_level);
  out << indentStr << "enum " << enum_descriptor->name() << " {\n";
  if (enum_descriptor->options().allow_alias()) {
    out << GetIndentation(indent_level + 1) << "option allow_alias = true;\n";
  }
  for (int i = 0; i < enum_descriptor->value_count(); ++i) {
    const google::protobuf::EnumValueDescriptor* valueDesc = enum_descriptor->value(i);
    out << GetIndentation(indent_level + 1) << valueDesc->name() << " = " << valueDesc->number() << ";\n";
  }
  out << indentStr << "}\n\n";
}

void AppendMessageProtoSyntax(std::ostream& out,
                              const google::protobuf::Descriptor* message_descriptor,
                              int indent_level,
                              std::set<const void*>& defined_elements,
                              const std::set<const google::protobuf::Descriptor*>& related_messages,
                              const std::set<const google::protobuf::EnumDescriptor*>& related_enums) {
  if (!message_descriptor || !related_messages.count(message_descriptor) || defined_elements.count(message_descriptor)) {
    return;
  }
  defined_elements.insert(message_descriptor);

  std::string indentStr = GetIndentation(indent_level);
  out << indentStr << "message " << message_descriptor->name() << " {\n";

  for (int i = 0; i < message_descriptor->enum_type_count(); ++i) {
    AppendEnumProtoSyntax(out, message_descriptor->enum_type(i), indent_level + 1, defined_elements, related_enums);
  }

  for (int i = 0; i < message_descriptor->nested_type_count(); ++i) {
    AppendMessageProtoSyntax(out, message_descriptor->nested_type(i), indent_level + 1, defined_elements, related_messages, related_enums);
  }

  for (int i = 0; i < message_descriptor->oneof_decl_count(); ++i) {
    const google::protobuf::OneofDescriptor* oneof = message_descriptor->oneof_decl(i);
    out << GetIndentation(indent_level + 1) << "oneof " << oneof->name() << " {\n";
    for (int j = 0; j < oneof->field_count(); ++j) {
      AppendFieldProtoSyntax(out, oneof->field(j), indent_level + 2);
    }
    out << GetIndentation(indent_level + 1) << "}\n";
  }

  for (int i = 0; i < message_descriptor->field_count(); ++i) {
    const google::protobuf::FieldDescriptor* field = message_descriptor->field(i);
    if (!field->containing_oneof()) {
      AppendFieldProtoSyntax(out, field, indent_level + 1);
    }
  }
  out << indentStr << "}\n\n";
}

std::string BuildPbSchema(const google::protobuf::Descriptor* top_descriptor) {
  if (!top_descriptor || !top_descriptor->file()) {
    AIMRT_ERROR("Null top_descriptor or its file is null.");
    return "";
  }

  std::ostringstream oss;
  std::unordered_set<std::string> processed_file_names_for_headers;

  std::set<const google::protobuf::Descriptor*> related_messages;
  std::set<const google::protobuf::EnumDescriptor*> related_enums;
  CollectRelatedTypes(top_descriptor, related_messages, related_enums);

  std::queue<const google::protobuf::FileDescriptor*> discovery_que;
  std::unordered_set<std::string> discovered_file_names;
  std::vector<const google::protobuf::FileDescriptor*> all_involved_files;

  std::queue<const google::protobuf::Descriptor*> descriptors_to_process;
  descriptors_to_process.push(top_descriptor);
  std::set<const google::protobuf::Descriptor*> visited_descriptors_for_file_discovery;

  std::set<const google::protobuf::FileDescriptor*> files_containing_related_types;

  for (const auto* msg_desc : related_messages) {
    if (msg_desc && msg_desc->file()) {
      files_containing_related_types.insert(msg_desc->file());
    }
  }
  for (const auto* enum_desc : related_enums) {
    if (enum_desc && enum_desc->file()) {
      files_containing_related_types.insert(enum_desc->file());
    }
  }

  for (const auto* initial_file_desc : files_containing_related_types) {
    std::string file_name(initial_file_desc->name());
    if (discovered_file_names.find(file_name) == discovered_file_names.end()) {
      discovery_que.push(initial_file_desc);
      discovered_file_names.insert(file_name);
    }
  }

  while (!discovery_que.empty()) {
    const google::protobuf::FileDescriptor* current_fd = discovery_que.front();
    discovery_que.pop();
    all_involved_files.push_back(current_fd);

    for (int i = 0; i < current_fd->dependency_count(); ++i) {
      const google::protobuf::FileDescriptor* dep_fd = current_fd->dependency(i);
      std::string dep_file_name(dep_fd->name());
      if (discovered_file_names.find(dep_file_name) == discovered_file_names.end()) {
        discovered_file_names.insert(dep_file_name);
        discovery_que.push(dep_fd);
      }
    }
  }
  std::reverse(all_involved_files.begin(), all_involved_files.end());

  std::set<const void*> globally_defined_elements;

  for (const auto* file_descriptor : all_involved_files) {
    bool file_has_any_related_definitions = false;
    for (int i = 0; i < file_descriptor->message_type_count(); ++i) {
      if (related_messages.count(file_descriptor->message_type(i))) {
        file_has_any_related_definitions = true;
        break;
      }
    }
    if (!file_has_any_related_definitions) {
      for (int i = 0; i < file_descriptor->enum_type_count(); ++i) {
        if (related_enums.count(file_descriptor->enum_type(i))) {
          file_has_any_related_definitions = true;
          break;
        }
      }
    }

    if (file_has_any_related_definitions && processed_file_names_for_headers.find(std::string(file_descriptor->name())) == processed_file_names_for_headers.end()) {
      oss << "// Schema definitions from file: " << file_descriptor->name() << "\n";
      oss << "syntax = \""
          << "proto3"
          << "\";\n\n";

      if (!file_descriptor->package().empty()) {
        oss << "package " << file_descriptor->package() << ";\n\n";
      }
      processed_file_names_for_headers.insert(std::string(file_descriptor->name()));
    }

    for (int i = 0; i < file_descriptor->enum_type_count(); ++i) {
      AppendEnumProtoSyntax(oss, file_descriptor->enum_type(i), 0, globally_defined_elements, related_enums);
    }

    for (int i = 0; i < file_descriptor->message_type_count(); ++i) {
      AppendMessageProtoSyntax(oss, file_descriptor->message_type(i), 0, globally_defined_elements, related_messages, related_enums);
    }
  }

  return oss.str();
}
}  // namespace proto_identifier

namespace ros2_identifier {

std::string BuildRos2Schema(const MessageMembers* members, int indent = 0) {
  std::stringstream schema;
  std::queue<std::pair<const MessageMembers*, int>> queue;
  std::unordered_set<const MessageMembers*> visited;

  queue.push({members, indent});
  visited.insert(members);

  static auto AppendArrayNotation = [](std::stringstream& ss, bool is_array) {
    if (is_array) {
      ss << "[] ";
    } else {
      ss << " ";
    }
  };

  static auto RosSchemaFormat = [](const MessageMembers* members) {
    std::string ns(members->message_namespace_);
    if (auto pos = ns.find("::"); pos != std::string::npos)
      ns.replace(pos, 2, "/");

    std::string schema_string = ns + "/" + members->message_name_;
    if (auto pos = schema_string.find("/msg"); pos != std::string::npos)
      schema_string.replace(pos, 4, "");

    return schema_string;
  };

  while (!queue.empty()) {
    auto [current_members, current_indent] = queue.front();
    queue.pop();

    AIMRT_CHECK_ERROR_THROW(current_indent <= 50, "Reached max recursion depth to resolve the schema");

    if (current_indent != 0) {
      schema << "================================================================================\n";
      schema << "MSG: " << RosSchemaFormat(current_members) << "\n";
    }

    for (size_t i = 0; i < current_members->member_count_; ++i) {
      const auto& member = current_members->members_[i];

      if (member.type_id_ == ROS_TYPE_MESSAGE) {
        const auto* nested_members = static_cast<const MessageMembers*>(member.members_->data);
        if (nested_members) {
          schema << RosSchemaFormat(nested_members);
          AppendArrayNotation(schema, member.is_array_);
          schema << member.name_ << "\n";
          if (visited.find(nested_members) == visited.end()) {
            queue.push({nested_members, current_indent + 1});
            visited.insert(nested_members);
          }
        }
        continue;
      }

      switch (member.type_id_) {
        case ROS_TYPE_FLOAT:
          schema << "float32";
          break;
        case ROS_TYPE_DOUBLE:
          schema << "float64";
          break;
        case ROS_TYPE_CHAR:
          schema << "char";
          break;
        case ROS_TYPE_BOOL:
          schema << "bool";
          break;
        case ROS_TYPE_BYTE:
          schema << "byte";
          break;
        case ROS_TYPE_UINT8:
          schema << "uint8";
          break;
        case ROS_TYPE_INT8:
          schema << "int8";
          break;
        case ROS_TYPE_UINT16:
          schema << "uint16";
          break;
        case ROS_TYPE_INT16:
          schema << "int16";
          break;
        case ROS_TYPE_UINT32:
          schema << "uint32";
          break;
        case ROS_TYPE_INT32:
          schema << "int32";
          break;
        case ROS_TYPE_UINT64:
          schema << "uint64";
          break;
        case ROS_TYPE_INT64:
          schema << "int64";
          break;
        case ROS_TYPE_STRING:
          schema << "string";
          break;
        case ROS_TYPE_WSTRING:
          schema << "wstring";
          break;
        case ROS_TYPE_MESSAGE:
          schema << "message";
          break;
        default:
          schema << "unknown";
          break;
      }
      AppendArrayNotation(schema, member.is_array_);
      schema << member.name_ << "\n";
    }
  }

  return schema.str();
}

}  // namespace ros2_identifier

}  // namespace aimrt::plugins::viz_plugin