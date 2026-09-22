// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./condition.h"

namespace aimrte::sync
{
Condition::Condition(bool value)
    : value_(value)
{
}

Condition::~Condition()
{
  Fail();
}

void Condition::Init(bool value)
{
  std::unique_lock lock(mutex_);
  value_  = value;
  failed_ = false;
}

bool Condition::Wait() const
{
  std::unique_lock lock(mutex_);

  while (not failed_ and not value_) {
    condition_.wait(lock);
  }

  return value_;
}

void Condition::Satisfy()
{
  std::unique_lock lock(mutex_);
  value_  = true;
  failed_ = false;
  condition_.notify_all();
}

void Condition::Fail()
{
  std::unique_lock lock(mutex_);
  value_  = false;
  failed_ = true;
  condition_.notify_all();
}

Condition::operator bool() const
{
  std::unique_lock lock(mutex_);
  return value_;
}
}  // namespace aimrte::sync
