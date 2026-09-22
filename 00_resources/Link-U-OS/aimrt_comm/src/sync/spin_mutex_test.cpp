// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./test/common.h"
#include "src/sync/sync.h"

namespace aimrte::test
{
TEST_F(SyncTest, SpinMutexBasicUsage)
{
  SyncMutexBasicUsage<sync::SpinMutex>(*this);
}

TEST_F(SyncTest, SpinMutexLotsOfParallel)
{
  SyncMutexLotsOfParallel<sync::SpinMutex>(*this);
}

TEST_F(SyncTest, SpinMutexMacro)
{
  SyncMutexMacro<sync::SpinMutex>(*this);
}
}  // namespace aimrte::test
