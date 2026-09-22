// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/macro/macro.h"
#include <variant>

/**
 * @brief Define a rust-like enum class
 * @code
 *   AIMRTE_ENUM_CLASS(
 *     MyEnumName,
 *     (MyItemName1, Type1, Type2)
 *     (MyItemName2, Type3, Type4, Type5)
 *     (MyItemName3)
 *  );
 *
 *  MyEnumName x = MyEnumName::MyItemName1(Type1(), Type2());
 *
 *  // use match
 *  match(x) | aimrte::trait::impl{
 *    MyEnumName::MyItemName1 | [](Type1, Type2) {},
 *    MyEnumName::MyItemName2 | [](Type3 &, Type4, auto) {},
 *    MyEnumName::MyItemName3 | []() {}
 *  };
 *
 *  // use if let
 *  ifLet(x) = MyEnumName::MyItemName1 | [](Type1, Type2) {};
 *
 *  // if let can be cascaded
 *  ifLet(x) |MyEnumName::MyItemName1| [](Type1, Type2) {}
 *  or
 *  ifLet(x) |MyEnumName::MyItemName2| [](auto, auto, auto) {}
 *  or
 *  aimrte::trait::otherwise{
 *    [](){}
 *  };
 *  @endcode
 */
#define AIMRTE_ENUM_CLASS(_name_, ...) AIMRTE_ENUM_TEMPLATE_CLASS(_name_, (), __VA_ARGS__)

/**
 * @brief Define a rust-like enum class with template parameters
 * @code
 *   template<class T1, class T2>
 *   AIMRTE_ENUM_TEMPLATE_CLASS(
 *      MyEnumName,
 *      (T1, T2),
 *      (MyItemName1, T1, int, T2)
 *      (MyItemName2, int, bool)
 *   );
 * @endcode
 */
#define AIMRTE_ENUM_TEMPLATE_CLASS(_name_, _pack_templates_, ...)            \
  class _name_ : public ::aimrte::match_details::EnumClass<                  \
                   _name_ AIMRTE_DETIALS_ENUM_TEMPLATE_OPT _pack_templates_> \
  {                                                                          \
    using _this_enum_class_type_ = _name_;                                   \
                                                                             \
   public:                                                                   \
    _name_() = delete;                                                       \
    AIMRTE_DECLARE_DEFAULT_COPY_MOVE(_name_);                                \
                                                                             \
    template <class EValueType>                                              \
    _name_(EValueType&& value, ::aimrte::match_details::BuildByEnumValue)    \
        : data_(std::forward<EValueType>(value))                             \
    {                                                                        \
    }                                                                        \
                                                                             \
    AIMRTE_INVOKE_INDEX(AIMRTE_DETAILS_ENUM_FIELD, __VA_ARGS__)              \
   private:                                                                  \
    ::aimrte::match_details::VariantExceptFirstType<                         \
      std::nullptr_t                                                         \
        AIMRTE_INVOKE(AIMRTE_DETAILS_ENUM_TYPE_UNPACK, __VA_ARGS__)>         \
      data_;                                                                 \
                                                                             \
    friend class ::aimrte::match_details::EnumClass<_name_>;                 \
  }

// Declare an optional template parameter list
#define AIMRTE_DETIALS_ENUM_TEMPLATE_OPT(...) \
  __VA_OPT__(<)                               \
  __VA_ARGS__ __VA_OPT__(>)

// Declare an enum item for aimrte enum class
#define AIMRTE_DETAILS_ENUM_FIELD(_idx_, _pack_params_)       \
 private:                                                     \
  struct AIMRTE_DETAILS_UNPACK_FIELD_NAME_TAG _pack_params_ { \
  };                                                          \
                                                              \
 public:                                                      \
  static inline aimrte::match_details::EnumField<             \
    _this_enum_class_type_,                                   \
    AIMRTE_DETAILS_UNPACK_FIELD_NAME_TAG _pack_params_,       \
    _idx_ AIMRTE_DETAILS_UNPACK_FIELD_TUPLE _pack_params_>    \
    AIMRTE_DETAILS_UNPACK_FIELD_NAME _pack_params_;

// Unpack the field parameters
#define AIMRTE_DETAILS_UNPACK_FIELD_TUPLE(_name_, ...) __VA_OPT__(, ) __VA_ARGS__
#define AIMRTE_DETAILS_UNPACK_FIELD_NAME(_name_, ...) _name_
#define AIMRTE_DETAILS_UNPACK_FIELD_NAME_TAG(_name_, ...) _name_##Tag

// Declare a possible variant type for enum
#define AIMRTE_DETAILS_ENUM_TYPE_UNPACK(_pack_params_) \
  AIMRTE_DETAILS_ENUM_TYPE _pack_params_

#define AIMRTE_DETAILS_ENUM_TYPE(_name_, ...) \
  , typename decltype(_name_)::ValueType

namespace aimrte::match_details
{
template <class, class... Ts>
using VariantExceptFirstType = std::variant<Ts...>;
}
