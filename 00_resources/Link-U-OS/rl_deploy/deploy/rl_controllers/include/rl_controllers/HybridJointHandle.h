#include <controller_interface/controller_interface.hpp>

namespace legged {

class HybridJointHandle {
 public:
  HybridJointHandle(
      const hardware_interface::LoanedStateInterface& pos_feedback,
      const hardware_interface::LoanedStateInterface& vel_feedback,
      const hardware_interface::LoanedStateInterface& tau_feedback,
      hardware_interface::LoanedCommandInterface& pos_des,
      hardware_interface::LoanedCommandInterface& vel_des,
      hardware_interface::LoanedCommandInterface& tau_des,
      hardware_interface::LoanedCommandInterface& kp_des,
      hardware_interface::LoanedCommandInterface& kd_des)
      : pos_feedback(pos_feedback),
        vel_feedback(vel_feedback),
        tau_feedback(tau_feedback),
        pos_des(pos_des),
        vel_des(vel_des),
        tau_des(tau_des),
        kp_des(kp_des),
        kd_des(kd_des) {}

  void setCommand(double posdes, double veldes, double kp, double kd, double taudes) {
    my_pos_des = posdes;
    my_vel_des = veldes;
    this->kp = kp;
    this->kd = kd;
    tau_des_feedforward = taudes;

    pos_curr = pos_feedback.get_value();
    vel_curr = vel_feedback.get_value();
    tau_curr = tau_feedback.get_value();

    pos_des.set_value(posdes);
    vel_des.set_value(veldes);
    tau_des.set_value(taudes);
    kp_des.set_value(kp);
    kd_des.set_value(kd);
  }

  double getPosDes() const {
    return my_pos_des;
  }

  double getVelDes() const {
    return my_vel_des;
  }

  double getKp() const {
    return kp;
  }

  double getKd() const {
    return kd;
  }

  double getFeedforward() const {
    return tau_des_feedforward;
  }

  double getPosCurr() const {
    return pos_curr;
  }

  double getVelCurr() const {
    return vel_curr;
  }

  double getTauCurr() const {
    return tau_curr;
  }

 private:
  const hardware_interface::LoanedStateInterface& pos_feedback;
  const hardware_interface::LoanedStateInterface& vel_feedback;
  const hardware_interface::LoanedStateInterface& tau_feedback;
  hardware_interface::LoanedCommandInterface& pos_des;
  hardware_interface::LoanedCommandInterface& vel_des;
  hardware_interface::LoanedCommandInterface& tau_des;
  hardware_interface::LoanedCommandInterface& kp_des;
  hardware_interface::LoanedCommandInterface& kd_des;

  double my_pos_des{0.0};
  double my_vel_des{0.0};
  double kp{0.0};
  double kd{0.0};
  double tau_des_feedforward{0.0};

  double pos_curr{0.0};
  double vel_curr{0.0};
  double tau_curr{0.0};
};

}  // namespace legged