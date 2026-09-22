// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/sync/sync.h"
#include "./test/common.h"

namespace aimrte::test
{
TEST_F(SyncTest, CVBasicUsage)
{
  SyncCVBasicUsage<sync::ConditionVariable, sync::Mutex>(*this);
}

TEST_F(SyncTest, CVPreCondition)
{
  SyncCVPreCondition<sync::ConditionVariable, sync::Mutex>(*this);
}

TEST_F(SyncTest, CVNotify)
{
  SyncCVNotify<sync::ConditionVariable, sync::Mutex>(*this);
}

TEST_F(SyncTest, CVSpinMutexBasicUsage)
{
  SyncCVBasicUsage<sync::ConditionVariable, sync::SpinMutex>(*this);
}

TEST_F(SyncTest, CVSpinMutexPreCondition)
{
  SyncCVPreCondition<sync::ConditionVariable, sync::SpinMutex>(*this);
}

TEST_F(SyncTest, CVSpinMutexNotify)
{
  SyncCVNotify<sync::ConditionVariable, sync::SpinMutex>(*this);
}

TEST_F(SyncTest, CVLockAndNotify)
{
  SyncCVLockAndNotify<sync::ConditionVariable, sync::SpinMutex>(*this);
}
}  // namespace aimrte::test
