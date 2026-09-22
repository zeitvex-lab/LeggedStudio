// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/sync/sync.h"
#include "./test/common.h"

namespace aimrte::test
{
TEST_F(SyncTest, MutexBasicUsage)
{
  SyncMutexBasicUsage<sync::Mutex>(*this);
}

TEST_F(SyncTest, MutexLotsOfParallel)
{
  SyncMutexLotsOfParallel<sync::Mutex>(*this);
}

TEST_F(SyncTest, MutexMacro)
{
  SyncMutexMacro<sync::Mutex>(*this);
}
}  // namespace aimrte::test
