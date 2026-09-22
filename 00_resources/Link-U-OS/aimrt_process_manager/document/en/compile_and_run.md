## compile

Install a dedicated Docker environment locally and clone the code. The compilation process uses the Bazel toolchain; please
refer to `integration` for details.

```sh
cd aimrt_process_manager

# compile x86 version
bazel build  //:process_manager_tar

# compile orin version
bazel build  //:process_manager_tar --config=orin_aarch64

```
The compiled output is located in the `bazel-bin` directory and is named as follows:`process_manager_tar.tar`


## run

This module will run on both Orin and x86.

The configuration file for this module depends on the configuration in the `integration` repository; the specific path is
- orin: `integration/product/a2_ultra/addons/orin/entry/bin/cfg/run_agibot.yaml`
- x86: `integration/product/a2_ultra/addons/x86/entry/bin/cfg/run_agibot.yaml`

After final deployment, the configuration file path is located at:
`/agibot/software/v0/entry/bin/cfg/run_agibot.yaml`, Please modify and refer to this document if testing and verification are required.

The startup script for the current module will be called by a daemon Python script in the `integration` repository. The specific path is:
- orin: `integration/product/a2_ultra/addons/orin/entry/bin/master_em_server.py`
- x86: `integration/product/a2_ultra/addons/x86_64/entry/bin/slave_em_server.py`


Two Python daemons are managed in a master-slave manner. They are started after time synchronization is complete to ensure that the 
startup time is consistent.

If testing only locally:
```sh
cd bazel-bin
tar xvf process_manager_tar.tar
bash ./scripts/process_manager/start_process_manager.sh
```
If testing locally, you may need to simulate the directories and necessary file information required for running the full package in your
local environment. Please build it yourself according to the prompts.