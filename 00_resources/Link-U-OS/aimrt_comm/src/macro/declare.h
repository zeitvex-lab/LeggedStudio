// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

/**
 * \brief Declare default copy constructor and copy assignment functions for a class
 */
#define AIMRTE_DECLARE_DEFAULT_COPY(_class_)          \
  _class_(const _class_& other)            = default; \
  _class_(_class_& other)                  = default; \
  _class_& operator=(const _class_& other) = default

/**
 * \brief Declare default move constructor and move assignment function for a class
 */
#define AIMRTE_DECLARE_DEFAULT_MOVE(_class_)              \
  _class_(_class_&& other) noexcept            = default; \
  _class_& operator=(_class_&& other) noexcept = default

/**
 * \brief Declare default copy, move constructors and assignment functions for a class
 */
#define AIMRTE_DECLARE_DEFAULT_COPY_MOVE(_class_) \
  AIMRTE_DECLARE_DEFAULT_COPY(_class_);           \
  AIMRTE_DECLARE_DEFAULT_MOVE(_class_)

/**
 * \brief Delete copy constructors and copy function for a class
 */
#define AIMRTE_DECLARE_FORBIDDEN_COPY(_class_)       \
  _class_(const _class_& other)            = delete; \
  _class_(_class_& other)                  = delete; \
  _class_& operator=(const _class_& other) = delete

/**
 * \brief Delete move constructor and move assignment function for a class
 */
#define AIMRTE_DECLARE_FORBIDDEN_MOVE(_class_)           \
  _class_(_class_&& other) noexcept            = delete; \
  _class_& operator=(_class_&& other) noexcept = delete

/**
 * \brief Delete copy, move constructors, assignment functions for a class
 */
#define AIMRTE_DECLARE_FORBIDDEN_COPY_MOVE(_class_) \
  AIMRTE_DECLARE_FORBIDDEN_COPY(_class_);           \
  AIMRTE_DECLARE_FORBIDDEN_MOVE(_class_)
