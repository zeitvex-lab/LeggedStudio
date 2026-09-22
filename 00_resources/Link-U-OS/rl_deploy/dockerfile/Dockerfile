# base image
FROM ubuntu:22.04

SHELL ["/bin/bash", "-c"]

# --------------------
# configurable parameters
# --------------------
ARG DEBIAN_FRONTEND=noninteractive
ARG USE_MIRROR=1                # whether replace ubuntu mirror (0/1)
ARG MIRROR_URL="mirrors.aliyun.com"
ARG INSTALL_GPP13=1             # whether install g++-13 (0/1)
ARG USERNAME=agi
ARG UID=1001
ARG GID=1001
ARG ROS_MIRROR="tuna"           # tuna / ustc / http://packages.ros.org/ros2/ubuntu
# build-time placeholder to avoid undefined-var warnings (can be overridden)
ARG LD_LIBRARY_PATH=""

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV TZ=Etc/UTC

# --------------------
# optional: replace ubuntu mirror to specified mirror (can be disabled)
# --------------------
RUN if [ "${USE_MIRROR}" = "1" ]; then \
      cp /etc/apt/sources.list /etc/apt/sources.list.bak && \
      sed -i "s|archive.ubuntu.com|${MIRROR_URL}|g" /etc/apt/sources.list && \
      sed -i "s|security.ubuntu.com|${MIRROR_URL}|g" /etc/apt/sources.list ; \
    fi

# --------------------
# basic environment + small tools (merged to reduce layers)
# also generate locale here to avoid runtime locale warnings
# --------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common \
      locales tzdata wget git vim sudo \
    && locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# --------------------
# add ROS2 official GPG key (put into keyring) and choose mirror according to ROS_MIRROR
# --------------------
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    if [ "${ROS_MIRROR}" = "tuna" ]; then \
      ROS_URL="https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu"; \
    elif [ "${ROS_MIRROR}" = "ustc" ]; then \
      ROS_URL="https://mirrors.ustc.edu.cn/ros/ubuntu"; \
    else \
      case "${ROS_MIRROR}" in http*://*) ROS_URL="${ROS_MIRROR}" ;; *) ROS_URL="${ROS_MIRROR}" ;; esac ; \
    fi && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] ${ROS_URL} $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
      > /etc/apt/sources.list.d/ros2.list

# --------------------
# update and install ROS Humble Desktop (desktop is large)
# --------------------
RUN apt-get update && \
    apt-get install -y ros-humble-desktop python3-argcomplete python3-colcon-common-extensions \
      jstest-gtk ros-humble-xacro ros-humble-gazebo-ros-pkgs \
      ros-humble-controller-manager ros-humble-gazebo-ros2-control \
      ros-humble-joint-state-publisher ros-humble-joint-state-broadcaster \
      ros-humble-joy-teleop \
    && rm -rf /var/lib/apt/lists/*

# --------------------
# optional: install g++-13 (for newer libstdc++). If installed, set it as default g++
# --------------------
RUN if [ "${INSTALL_GPP13}" = "1" ]; then \
      add-apt-repository -y ppa:ubuntu-toolchain-r/test && \
      apt-get update && \
      apt-get install -y --no-install-recommends g++-13 && \
      update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 100 || true && \
      update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 100 || true && \
      rm -rf /var/lib/apt/lists/* ; \
    fi

# --------------------
# install ONNX Runtime (decompress, copy, clean). assume onnxruntime tgz in build context root.
# --------------------
COPY onnxruntime-linux-x64-1.19.2.tgz /tmp/
RUN tar -xzf /tmp/onnxruntime-linux-x64-1.19.2.tgz -C /tmp/ && \
    mkdir -p /usr/local/include/onnxruntime /usr/local/lib64 /usr/local/lib/cmake/onnxruntime /usr/local/lib/pkgconfig && \
    cp -r /tmp/onnxruntime-linux-x64-1.19.2/include/* /usr/local/include/onnxruntime/ && \
    cp -a /tmp/onnxruntime-linux-x64-1.19.2/lib/libonnxruntime.so* /usr/local/lib64/ && \
    cp -a /tmp/onnxruntime-linux-x64-1.19.2/lib/libonnxruntime_providers_shared.so* /usr/local/lib64/ && \
    cp -a /tmp/onnxruntime-linux-x64-1.19.2/lib/cmake/onnxruntime/* /usr/local/lib/cmake/onnxruntime/ && \
    cp /tmp/onnxruntime-linux-x64-1.19.2/lib/pkgconfig/libonnxruntime.pc /usr/local/lib/pkgconfig/ && \
    rm -rf /tmp/onnxruntime-linux-x64-1.19.2* && ldconfig

# --------------------
# install libacl1-dev for iceoryx
# --------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends libacl1-dev && \
    rm -rf /var/lib/apt/lists/*

# --------------------
# install python3-pip
# --------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip && \
    rm -rf /var/lib/apt/lists/*

# --------------------
# install higher version of cmake via pip
# --------------------
RUN pip install cmake

# --------------------
# runtime environment variables (avoid undefined-var warning by using a concrete value)
# --------------------
ENV LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib:$LD_LIBRARY_PATH
ENV PATH=/usr/local/bin:$PATH

# --------------------
# create non-root user and switch (keep sudo for interactive debugging)
# --------------------
RUN groupadd -g ${GID} ${USERNAME} || true && \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash ${USERNAME} && \
    usermod -aG sudo ${USERNAME} && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER ${USERNAME}
WORKDIR /home/${USERNAME}

# add /home/agi/.local/bin to PATH for cmake installation
RUN echo "export PATH=/home/${USERNAME}/.local/bin:$PATH" >> /home/${USERNAME}/.bashrc

# automatically source ROS environment in non-root user's bashrc for interactive use
RUN echo "source /opt/ros/humble/setup.bash" >> /home/${USERNAME}/.bashrc

# add ROS_DOMAIN_ID=20 to avoid DDS conflicts in multi-robot scenarios
RUN echo "export ROS_DOMAIN_ID=20" >> /home/${USERNAME}/.bashrc

CMD ["/bin/bash"]
