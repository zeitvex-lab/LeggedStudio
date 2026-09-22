// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/macro/macro.h"
#include "src/trait/trait.h"
#include <variant>

#include <iostream>

namespace aimrte::match_details
{
struct BuildByEnumValue {
};

template <class TArm>
concept HasArmTypeTrait =
  requires {
    typename TArm::ArmType;
  };

template <class TVariantType, class TArm>
struct GetArmIndex;

template <class TVariantType, class TArm>
  requires(HasArmTypeTrait<TArm>)
struct GetArmIndex<TVariantType, TArm> {
  constexpr static std::size_t value = trait::get_index<typename TArm::ArmType, TVariantType>::value;
};

template <class TVariantType, class TArm>
  requires(not HasArmTypeTrait<TArm>)
struct GetArmIndex<TVariantType, TArm> {
  constexpr static std::size_t value = TArm::ARM_INDEX;
};

template <class TDerived>
class EnumClass
{
  template <class E>
  class Match
  {
   public:
    explicit Match(E self)
        : self_(std::forward<E>(self))
    {
    }

   public:
    template <class TArms>
    auto operator|(TArms &&arms)
    {
      if constexpr (std::is_rvalue_reference_v<E>) {
        return std::visit(std::forward<TArms>(arms), std::move(self_.data()));
      } else {
        return std::visit(std::forward<TArms>(arms), self_.data());
      }
    }

   private:
    E self_;
  };

  template <class E>
  class IfLet
  {
    template <class TEnumField>
    class Some
    {
     public:
      Some(IfLet &&self, const TEnumField &field)
          : self_(std::move(self)), field_(field)
      {
      }

      template <class F>
      bool operator|(F &&func) const
      {
        return self_.operator=(field_ | std::forward<F>(func));
      }

     private:
      IfLet &&self_;
      const TEnumField &field_;
    };

   public:
    explicit IfLet(E self)
        : self_(std::forward<E>(self))
    {
    }

   public:
    template <class TArm>
    bool operator=(TArm &&arm)
    {
      auto &data = self_.data();

      using VariantType               = std::remove_cvref_t<decltype(data)>;
      constexpr std::size_t ARM_INDEX = GetArmIndex<VariantType, TArm>::value;

      if (data.index() != ARM_INDEX)
        return false;

      if constexpr (std::is_rvalue_reference_v<E>) {
        static_assert(std::is_void_v<decltype(arm(std::get<ARM_INDEX>(std::move(data))))>);
        arm(std::get<ARM_INDEX>(std::move(data)));
      } else {
        static_assert(std::is_void_v<decltype(arm(std::get<ARM_INDEX>(data)))>);
        arm(std::get<ARM_INDEX>(data));
      }

      return true;
    }

    template <class TEnumField>
    auto operator|(const TEnumField &field) &&
    {
      return Some<TEnumField>(std::move(*this), field);
    }

   private:
    E self_;
  };

 private:
  TDerived &derived() &
  {
    return *static_cast<TDerived *>(this);
  }

  TDerived &&derived() &&
  {
    return std::move(derived());
  }

  const TDerived &derived() const &
  {
    return trait::remove_const(this)->derived();
  }

  auto &data() &
  {
    return derived().data_;
  }

  auto &&data() &&
  {
    return std::move(derived().data_);
  }

  const auto &data() const &
  {
    return derived().data_;
  }

 public:
  template <class TEnumField>
  bool is(const TEnumField &) const
  {
    return data().index() == GetEnumFieldIndex<TEnumField>();
  }

 public:
  friend auto match(const TDerived &obj)
  {
    return Match<const TDerived &>(obj);
  }

  friend auto match(TDerived &obj)
  {
    return Match<TDerived &>(obj);
  }

  friend auto match(TDerived &&obj)
  {
    return Match<TDerived &&>(std::move(obj));
  }

  friend auto ifLet(const TDerived &obj)
  {
    return IfLet<const TDerived &>(obj);
  }

  friend auto ifLet(TDerived &obj)
  {
    return IfLet<TDerived &>(obj);
  }

  friend auto ifLet(TDerived &&obj)
  {
    return IfLet<TDerived &&>(std::move(obj));
  }

  static auto &GetRawData(TDerived &obj)
  {
    return obj.data();
  }

  static auto &&GetRawData(TDerived &&obj)
  {
    return std::move(std::move(obj).data());
  }

  template <class TEnumField>
  static constexpr std::size_t GetEnumFieldIndex()
  {
    return trait::get_index<typename TEnumField::ValueType, std::remove_cvref_t<decltype(std::declval<TDerived>().data())>>::value;
  }

  template <class TEnumField>
  static constexpr std::size_t GetEnumFieldIndex(const TEnumField &)
  {
    return GetEnumFieldIndex<TEnumField>();
  }

  template <class TEnumField>
  static const typename TEnumField::ValueType &GetEnumValue(const TDerived &obj, const TEnumField &)
  {
    return std::get<GetEnumFieldIndex<TEnumField>()>(obj.data());
  }

  template <class TEnumField>
  static typename TEnumField::ValueType &GetEnumValue(TDerived &obj, const TEnumField &)
  {
    return std::get<GetEnumFieldIndex<TEnumField>()>(obj.data());
  }

  template <class TEnumField>
  static typename TEnumField::ValueType &&GetEnumValue(TDerived &&obj, const TEnumField &)
  {
    return std::get<GetEnumFieldIndex<TEnumField>()>(std::move(obj).data());
  }
};
}  // namespace aimrte::match_details

/**
 * @brief ifLet 的封装宏，实现枚举类型展开的同时，保持在当前函数域下
 *        if AIMRTE(let(some_enum_class_object), as(some_enum_kind), then(enum_tuple_0, enum_tuple_1, ...)) {
 *          return enum_tuple_1; // 将结束当前作用域
 *        }
 */
#define AIMRTE_DETAILS_let(...) AIMRTE_DETAILS_let_DO
#define AIMRTE_DETAILS_let_DO(_let_pack_, _as_pack_, _then_pack_)                                                               \
  (auto &&AIMRTE_LINE_UNIQUE(__enum_class_object__) = AIMRTE_DETAILS_let_DO_UNPACK_##_let_pack_;                                \
   AIMRTE_LINE_UNIQUE(__enum_class_object__).is(AIMRTE_DETAILS_let_DO_UNPACK_##_as_pack_))                                      \
    AIMRTE_DETAILS_ENUM_CLASS_UNPACK_VALUE(AIMRTE_LINE_UNIQUE(__enum_class_object__), AIMRTE_DETAILS_let_DO_UNPACK_##_as_pack_) \
      AIMRTE_DETAILS_let_DO_UNPACK_##_then_pack_

#define AIMRTE_DETAILS_let_DO_UNPACK_let(...) __VA_ARGS__
#define AIMRTE_DETAILS_let_DO_UNPACK_as(...) __VA_ARGS__
#define AIMRTE_DETAILS_let_DO_UNPACK_then(...) AIMRTE_INVOKE_INDEX(AIMRTE_DETAILS_let_DO_UNPACK_then_DECALARE, __VA_ARGS__)
#define AIMRTE_DETAILS_let_DO_UNPACK_then_DECALARE(_idx_, _expr_)                                                              \
  if constexpr (                                                                                                               \
    _expr_ = std::get<_idx_>(                                                                                                  \
      ::aimrte::trait::as_is<decltype(AIMRTE_LINE_UNIQUE(__enum_value_object__))>(AIMRTE_LINE_UNIQUE(__enum_value_object__))); \
    false)                                                                                                                     \
    ;                                                                                                                          \
  else

/**
 * @brief match 的封装宏，实现枚举类型展开的同时，保持在当前函数域下
 *        AIMRTE(match(som_enum_class_object)) {
 *          case AIMRTE(as(some_enum_kind), then(enum_tuple_0, enum_tuple_1, ...)) {
 *
 *          } break;
 *        }
 */
#define AIMRTE_DETAILS_match(...) AIMRTE_DETAILS_match_DO
#define AIMRTE_DETAILS_match_DO(_match_pack_)                                                              \
  if constexpr (auto &&__match_enum_class_object__ = AIMRTE_DETAILS_match_DO_UNPACK_##_match_pack_; false) \
    ;                                                                                                      \
  else                                                                                                     \
    switch (std::remove_cvref_t<decltype(__match_enum_class_object__)>::GetRawData(                        \
              __match_enum_class_object__)                                                                 \
              .index())
#define AIMRTE_DETAILS_match_DO_UNPACK_match(...) __VA_ARGS__

#define AIMRTE_DETAILS_as(...) AIMRTE_DETAILS_as_DO
#define AIMRTE_DETAILS_as_DO(_as_pack_, _then_pack_)                                                                                                        \
  std::remove_cvref_t<decltype(__match_enum_class_object__)>::GetEnumFieldIndex(                                                                            \
    AIMRTE_DETAILS_as_DO_UNPACK_##_as_pack_) : AIMRTE_DETAILS_ENUM_CLASS_UNPACK_VALUE(__match_enum_class_object__, AIMRTE_DETAILS_as_DO_UNPACK_##_as_pack_) \
                                                 AIMRTE_DETAILS_as_DO_UNPACK_##_then_pack_

#define AIMRTE_DETAILS_as_DO_UNPACK_as(...) __VA_ARGS__
#define AIMRTE_DETAILS_as_DO_UNPACK_then(...) AIMRTE_DETAILS_let_DO_UNPACK_then(__VA_ARGS__)

// 取出指定 enum field 对象（从 enum class 这个 tuple 中取出，而 enum field value 也是一个 tuple）
// 第一个参数：指向被展开的 enum class 对象
// 第二个参数：指定的 enum class field 类型标识对象
#define AIMRTE_DETAILS_ENUM_CLASS_UNPACK_VALUE(_enum_class_object_, ...)            \
  if constexpr (auto &&AIMRTE_LINE_UNIQUE(__enum_value_object__) =                  \
                  std::remove_cvref_t<decltype(_enum_class_object_)>::GetEnumValue( \
                    ::aimrte::trait::as_is<                                         \
                      decltype(_enum_class_object_)>(_enum_class_object_),          \
                    __VA_ARGS__);                                                   \
                false)                                                              \
    ;                                                                               \
  else
