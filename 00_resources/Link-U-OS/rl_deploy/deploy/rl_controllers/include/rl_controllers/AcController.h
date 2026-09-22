#pragma once

#include "rl_controllers/RLControllerBase.h"

namespace legged {

class AcController : public RLControllerBase {
  using tensor_element_t = float;

 public:
  AcController() : memoryInfo(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault)) {}
  ~AcController() override = default;

 protected:
  bool loadModel() override;
  bool loadRLCfg() override;
  void computeActions() override;
  void computeObservation() override;
  void handleWalkMode() override;

 private:
  // onnx policy model
  std::string policyFilePath_;
  std::shared_ptr<Ort::Env> onnxEnvPrt_;
  std::unique_ptr<Ort::Session> sessionPtr_;
  std::vector<const char*> inputNames_;
  std::vector<const char*> outputNames_;
  std::vector<Ort::AllocatedStringPtr> inputNodeNameAllocatedStrings;
  std::vector<Ort::AllocatedStringPtr> outputNodeNameAllocatedStrings;
  std::vector<std::vector<int64_t>> inputShapes_;
  std::vector<std::vector<int64_t>> outputShapes_;
  bool sw_mode_;
  double cmd_threshold_;
  double phase_start_time_ = 0;

  vector3_t baseLinVel_;
  vector3_t basePosition_;
  vector_t lastActions_;
  vector_t defaultJointAngles_;
  vector_t defaultJointAnglesActuated_;
  Ort::MemoryInfo memoryInfo;

  int observationSize_;
  int num_hist_;
  std::vector<tensor_element_t> actions_;
  std::vector<tensor_element_t> observations_;
  Eigen::Matrix<tensor_element_t, Eigen::Dynamic, 1> proprioHistoryBuffer_;

  bool isfirstRecObs_{true};
};

}  // namespace legged