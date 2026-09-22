// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./register.h"

// Pick your poison.
//
// On GNU/Linux, you have few choices to get the most out of your stack trace.
//
// By default you get:
//	- object filename
//	- function name
//
// In order to add:
//	- source filename
//	- line and column numbers
//	- source code snippet (assuming the file is accessible)

// Install one of the following libraries then uncomment one of the macro (or
// better, add the detection of the lib and the macro definition in your build
// system)

// - apt-get install libdw-dev ...
// - g++/clang++ -ldw ...
#define BACKWARD_HAS_DW 1

// - apt-get install binutils-dev ...
// - g++/clang++ -lbfd ...
// #define BACKWARD_HAS_BFD 1

// - apt-get install libdwarf-dev ...
// - g++/clang++ -ldwarf ...
// #define BACKWARD_HAS_DWARF 1

// Regardless of the library you choose to read the debug information,
// for potentially more detailed stack traces you can use libunwind
// - apt-get install libunwind-dev
// - g++/clang++ -lunwind
// #define BACKWARD_HAS_LIBUNWIND 1

#include "src/private/backward/backward.h"

namespace
{
using namespace backward;

/*************** SIGNALS HANDLING ***************/

#if defined(BACKWARD_SYSTEM_LINUX) || defined(BACKWARD_SYSTEM_DARWIN)

class SignalHandling
{
 public:
  static std::vector<int> make_default_signals()
  {
    const int posix_signals[] = {
      // Signals for which the default action is "Core".
      SIGABRT,  // Abort signal from abort(3)
      SIGBUS,   // Bus error (bad memory access)
      SIGFPE,   // Floating point exception
      SIGILL,   // Illegal Instruction
      SIGIOT,   // IOT trap. A synonym for SIGABRT
      SIGQUIT,  // Quit from keyboard
      SIGSEGV,  // Invalid memory reference
      SIGSYS,   // Bad argument to routine (SVr4)
      SIGTRAP,  // Trace/breakpoint trap
      SIGXCPU,  // CPU time limit exceeded (4.2BSD)
      SIGXFSZ,  // File size limit exceeded (4.2BSD)
  #if defined(BACKWARD_SYSTEM_DARWIN)
      SIGEMT,  // emulation instruction executed
  #endif
    };
    return std::vector<int>(posix_signals, posix_signals + sizeof posix_signals / sizeof posix_signals[0]);
  }

  SignalHandling(const std::vector<int> &posix_signals = make_default_signals())
      : _loaded(false)
  {
    bool success = true;

    const size_t stack_size = 1024 * 1024 * 8;
    _stack_content.reset(static_cast<char *>(malloc(stack_size)));
    if (_stack_content) {
      stack_t ss;
      ss.ss_sp    = _stack_content.get();
      ss.ss_size  = stack_size;
      ss.ss_flags = 0;
      if (sigaltstack(&ss, nullptr) < 0) {
        success = false;
      }
    } else {
      success = false;
    }

    for (size_t i = 0; i < posix_signals.size(); ++i) {
      struct sigaction action;
      memset(&action, 0, sizeof action);
      action.sa_flags =
        static_cast<int>(SA_SIGINFO | SA_ONSTACK | SA_NODEFER | SA_RESETHAND);
      sigfillset(&action.sa_mask);
      sigdelset(&action.sa_mask, posix_signals[i]);
  #if defined(__clang__)
    #pragma clang diagnostic push
    #pragma clang diagnostic ignored "-Wdisabled-macro-expansion"
  #endif
      action.sa_sigaction = &sig_handler;
  #if defined(__clang__)
    #pragma clang diagnostic pop
  #endif

      int r = sigaction(posix_signals[i], &action, nullptr);
      if (r < 0)
        success = false;
    }

    _loaded = success;
  }

  bool loaded() const { return _loaded; }

  static void handleSignal(int, siginfo_t *info, void *_ctx)
  {
    ucontext_t *uctx = static_cast<ucontext_t *>(_ctx);

    StackTrace st;
    void *error_addr = nullptr;
  #ifdef REG_RIP  // x86_64
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.gregs[REG_RIP]);
  #elif defined(REG_EIP)  // x86_32
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.gregs[REG_EIP]);
  #elif defined(__arm__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.arm_pc);
  #elif defined(__aarch64__)
    #if defined(__APPLE__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext->__ss.__pc);
    #else
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.pc);
    #endif
  #elif defined(__mips__)
    error_addr = reinterpret_cast<void *>(
      reinterpret_cast<struct sigcontext *>(&uctx->uc_mcontext)->sc_pc);
  #elif defined(__ppc__) || defined(__powerpc) || defined(__powerpc__) || \
    defined(__POWERPC__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.regs->nip);
  #elif defined(__riscv)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.__gregs[REG_PC]);
  #elif defined(__s390x__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext.psw.addr);
  #elif defined(__APPLE__) && defined(__x86_64__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext->__ss.__rip);
  #elif defined(__APPLE__)
    error_addr = reinterpret_cast<void *>(uctx->uc_mcontext->__ss.__eip);
  #else
    #warning ":/ sorry, ain't know no nothing none not of your architecture!"
  #endif
    if (error_addr) {
      st.load_from(error_addr, 32, reinterpret_cast<void *>(uctx), info->si_addr);
    } else {
      st.load_here(32, reinterpret_cast<void *>(uctx), info->si_addr);
    }

    Printer printer;
    printer.address    = true;
    printer.color_mode = ColorMode::always;
    printer.print(st, std::cerr);

    // todo: 补充系统错误日志

  #if (defined(_XOPEN_SOURCE) && _XOPEN_SOURCE >= 700) || \
    (defined(_POSIX_C_SOURCE) && _POSIX_C_SOURCE >= 200809L)
    psiginfo(info, nullptr);
  #else
    (void)info;
  #endif
  }

 private:
  ::backward::details::handle<char *> _stack_content;
  bool _loaded;

  #ifdef __GNUC__
  __attribute__((noreturn))
  #endif
  static void
  sig_handler(int signo, siginfo_t *info, void *_ctx)
  {
    handleSignal(signo, info, _ctx);

    // try to forward the signal.
    raise(info->si_signo);

    // terminate the process immediately.
    puts("watf? exit");
    _exit(EXIT_FAILURE);
  }
};

#endif  // BACKWARD_SYSTEM_LINUX || BACKWARD_SYSTEM_DARWIN

SignalHandling sh;
}  // namespace

namespace aimrte::private_::backward
{
AIMRTE_NOT_OPTIMIZE_OUT_HELPER_IMPL(Backward) {}
}  // namespace aimrte::private_::backward
