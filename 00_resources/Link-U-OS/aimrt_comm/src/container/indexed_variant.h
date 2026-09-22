// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <tuple>
#include <variant>

namespace aimrte
{
namespace details
{
template <std::size_t Idx, class... TArgs>
class ArgsAt : public std::tuple<TArgs&&...>
{
  using Base = std::tuple<TArgs&&...>;

 public:
  explicit ArgsAt(TArgs&&... args)
      : Base(std::forward<TArgs>(args)...)
  {
  }

  template <std::size_t IdxOfArg>
  decltype(auto) Take() &&
  {
    return std::get<IdxOfArg>(static_cast<Base&&>(*this));
  }
};
}  // namespace details

template <std::size_t Idx, class... TArgs>
auto MakeOfIdx(TArgs&&... args)
{
  return details::ArgsAt<Idx, TArgs...>(std::forward<TArgs>(args)...);
}

template <class... Ts>
class IndexedVariant
{
  template <std::size_t Idx>
  using TypeAt = std::tuple_element_t<Idx, std::tuple<Ts...>>;

  template <std::size_t Idx>
  struct DataAt {
    TypeAt<Idx> value;
    constexpr static std::size_t index = Idx;

    DataAt() = default;

    template <class... TArgs>
    explicit DataAt(details::ArgsAt<Idx, TArgs...>&& args)
        : DataAt(std::move(args), std::make_index_sequence<sizeof...(TArgs)>())
    {
    }

   public:
    template <class... TArgs, std::size_t... IdxOfArgs>
    DataAt(details::ArgsAt<Idx, TArgs...>&& args, std::index_sequence<IdxOfArgs...>)
        : value(std::move(args).template Take<IdxOfArgs>()...)
    {
    }
  };

  template <class>
  struct DataTrait;

  template <std::size_t... I>
  struct DataTrait<std::index_sequence<I...>> {
    using Type = std::variant<DataAt<I>...>;
  };

  using DataType = typename DataTrait<std::make_index_sequence<sizeof...(Ts)>>::Type;

 public:
  IndexedVariant() = default;

  template <std::size_t Idx, class... TArgs>
  explicit IndexedVariant(details::ArgsAt<Idx, TArgs...>&& args)
      : data_(std::in_place_index<Idx>, std::move(args))
  {
  }

  template <std::size_t Idx, class... TArgs>
  explicit IndexedVariant(std::in_place_index_t<Idx>, TArgs&&... args)
      : IndexedVariant(MakeOfIdx<Idx>(std::forward<TArgs>(args)...))
  {
  }

  [[nodiscard]] std::size_t Index() const
  {
    return data_.index();
  }

  template <std::size_t Idx, class... TArgs>
  TypeAt<Idx>& Emplace(TArgs&&... args)
  {
    return Emplace(MakeOfIdx<Idx>(std::forward<TArgs>(args)...));
  }

  template <std::size_t Idx, class... TArgs>
  TypeAt<Idx>& Emplace(details::ArgsAt<Idx, TArgs...>&& args)
  {
    return data_.template emplace<DataAt<Idx>>(std::move(args)).value;
  }

  template <std::size_t Idx, class... TArgs>
  TypeAt<Idx>& Emplace(std::in_place_index_t<Idx>, TArgs&&... args)
  {
    return Emplace<Idx>(std::forward<TArgs>(args)...);
  }

  template <std::size_t Idx, class... TArgs>
  IndexedVariant& operator=(details::ArgsAt<Idx, TArgs...>&& args)
  {
    Emplace(std::move(args));
    return *this;
  }

  template <std::size_t Idx>
  TypeAt<Idx>& Get() &
  {
    return std::get<Idx>(data_).value;
  }

  template <std::size_t Idx>
  TypeAt<Idx>& Get() const&
  {
    return std::get<Idx>(data_).value;
  }

  template <std::size_t Idx>
  TypeAt<Idx>& Get() &&
  {
    return std::get<Idx>(std::move(data_)).value;
  }

  template <std::size_t Idx>
  TypeAt<Idx>& Get() const&&
  {
    return std::get<Idx>(std::move(data_)).value;
  }

  template <class FVisitor>
  auto Visit(FVisitor&& visitor) &
  {
    return std::visit(
      [&visitor](auto& data) {
        return visitor(data.index, data.value);
      },
      data_);
  }

  template <class FVisitor>
  auto Visit(FVisitor&& visitor) const&
  {
    return std::visit(
      [&visitor](const auto& data) {
        return visitor(data.index, data.value);
      },
      data_);
  }

  template <class FVisitor>
  auto Visit(FVisitor&& visitor) &&
  {
    return std::visit(
      [&visitor](auto&& data) {
        return visitor(data.index, std::move(data.value));
      },
      std::move(data_));
  }

 private:
  DataType data_;
};
}  // namespace aimrte
