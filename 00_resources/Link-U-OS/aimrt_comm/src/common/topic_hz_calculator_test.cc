// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./topic_hz_calculator.h"
#include <thread>
#include "gtest/gtest.h"
TEST(TopicHzCalculatorTest, Test)
{
  std::set<aimrte::common::TopicHzCalculator::TopicInfo> topic_list;
  for (int i = 0; i < 100; i++) {
    topic_list.insert(aimrte::common::TopicHzCalculator::TopicInfo{
      .process_name = "test",
      .topic_name   = "test" + std::to_string(i),
      .msg_type     = "test",
    });
  }
  aimrte::common::TopicHzCalculator calculator;
  calculator.Initialize(topic_list);

  std::atomic_bool stop_flag = false;
  std::vector<std::thread> threads;
  for (int i = 0; i < 100; i++) {
    threads.emplace_back([&stop_flag, &calculator, i]() {
      while (!stop_flag) {
        calculator.FeedTopic(aimrte::common::TopicHzCalculator::TopicInfo{
          .process_name = "test",
          .topic_name   = "test" + std::to_string(i),
          .msg_type     = "test",
        });
        std::this_thread::sleep_for(std::chrono::milliseconds(i));
      }
    });
  }

  for (int i = 0; i < 100; i++) {
    threads.emplace_back([&stop_flag, &calculator, i]() {
      while (!stop_flag) {
        calculator.CalculateAll();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
    });
  }

  std::this_thread::sleep_for(std::chrono::seconds(10));
  stop_flag = true;
  for (auto& thread : threads) {
    if (thread.joinable()) {
      thread.join();
    }
  }
}
