// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "h264raw.hpp"

namespace aima::sensors::camera {

H264RawStreamer::~H264RawStreamer() {
    // free dma buf pool
    for (const auto& fd : dma_fd_pool_) {
        NvBufSurf::NvDestroy(fd);
    }

    if (video_encoder_) {
        delete video_encoder_;
    }
}

int H264RawStreamer::Init(const std::string& name) {
    // allocate dma buf pool
    NvBufSurf::NvCommonAllocateParams params;
    params.memType = NVBUF_MEM_SURFACE_ARRAY;
    params.width = output_width_;
    params.height = output_height_;
    params.layout = NVBUF_LAYOUT_PITCH;
    params.colorFormat = NVBUF_COLOR_FORMAT_NV12;
    params.memtag = NvBufSurfaceTag_VIDEO_ENC;
    
    dma_fd_pool_.resize(dma_fd_pool_size_);
    for (int i = 0; i < dma_fd_pool_size_; i++) {
        int fd = -1;
        NvBufSurf::NvAllocate(&params, 1, &fd);
        if (fd < 0) {
            AIMRTE_ERROR("Failed to allocate DMA buffer");
            return -1;
        }
        dma_fd_pool_[i] = fd;
    }

    auto expect_height = (input_width_ * output_height_) / output_width_;
    int src_top = 0;
    if (expect_height < input_height_) {
      // 裁剪
      src_top = (input_height_ - expect_height) / 2;
    }
    transform_params_.src_top = src_top;
    transform_params_.src_left = 0;
    transform_params_.src_width = input_width_;
    transform_params_.src_height = expect_height;
    transform_params_.dst_top = 0;
    transform_params_.dst_left = 0;
    transform_params_.dst_width = output_width_;
    transform_params_.dst_height = output_height_;
    transform_params_.flag = NVBUFSURF_TRANSFORM_CROP_SRC;
    transform_params_.flip = NvBufSurfTransform_None;
    transform_params_.filter = NvBufSurfTransformInter_Nearest;

    // create video encoder
    if (createVideoEncoder(name) < 0) {
        AIMRTE_ERROR("Failed to create video encoder");
        return -2;
    }

    video_encoder_->output_plane.setStreamStatus(true);

    video_encoder_->capture_plane.setStreamStatus(true);

    video_encoder_->capture_plane.setDQThreadCallback(encoderCallback);

    video_encoder_->capture_plane.startDQThread(this);

    for (uint32_t i = 0; i < video_encoder_->capture_plane.getNumBuffers(); i++) {
        struct v4l2_buffer v4l2_buf;
        struct v4l2_plane planes[MAX_PLANES];

        memset(&v4l2_buf, 0, sizeof(v4l2_buf));
        memset(planes, 0, sizeof(struct v4l2_plane) * MAX_PLANES);

        v4l2_buf.index = i;
        v4l2_buf.m.planes = planes;

        if (video_encoder_->capture_plane.qBuffer(v4l2_buf, NULL) < 0) {
            AIMRTE_ERROR("Failed to queue buffer to capture plane");
            return -3;
        }
    }

    return 0;
}

int H264RawStreamer::createVideoEncoder(const std::string& name) {
    video_encoder_ = NvVideoEncoder::createVideoEncoder(name.c_str());
    if (!video_encoder_) {
        return -1;
    }

    if (video_encoder_->setCapturePlaneFormat(V4L2_PIX_FMT_H264, output_width_, output_height_, default_bitrate_ / 2))
        return -2;

    if (video_encoder_->setOutputPlaneFormat(V4L2_PIX_FMT_NV12M, output_width_, output_height_))
        return -3;

    if (video_encoder_->setBitrate(default_bitrate_))
        return -4;

    if (video_encoder_->setProfile(V4L2_MPEG_VIDEO_H264_PROFILE_MAIN))
        return -5;

    if (video_encoder_->setLevel(V4L2_MPEG_VIDEO_H264_LEVEL_5_0))
        return -6;

    if (video_encoder_->setRateControlMode(V4L2_MPEG_VIDEO_BITRATE_MODE_CBR))
        return -7;

    if (video_encoder_->setIFrameInterval(30))
        return -8;

    if (video_encoder_->setFrameRate(30, 1))
        return -9;

    if (video_encoder_->setInsertSpsPpsAtIdrEnabled(true))
        return -12;

    if (video_encoder_->output_plane.setupPlane(V4L2_MEMORY_DMABUF, dma_fd_pool_size_, false, false))
        return -10;

    if (video_encoder_->capture_plane.setupPlane(V4L2_MEMORY_MMAP, dma_fd_pool_size_, true, false))
        return -11;

    return 0;
}

int H264RawStreamer::Start() {
    running_.store(true);

    return 0;
}

void H264RawStreamer::Stop() {
    running_.store(false);
    AIMRTE_ERROR("stopping encoder, end of stream");
    video_encoder_->output_plane.setStreamStatus(false);
    video_encoder_->capture_plane.setStreamStatus(false);
    video_encoder_->capture_plane.waitForDQThread(-1);
}

void H264RawStreamer::PushImage(uint8_t* input) {
    return;
}

void H264RawStreamer::PushImageFd(int src_fd) {
    // convert to NV12
    if (dma_fd_pool_.empty()) {
        AIMRTE_ERROR("No available DMA fd in pool");
        return;
    }

    int dma_fd = dma_fd_pool_[frame_index_ % dma_fd_pool_size_];
    frame_index_ += 1;

    if (NvBufSurf::NvTransform(&transform_params_, src_fd, dma_fd) < 0) {
        AIMRTE_ERROR("NvTransform failed");
        return;
    }

    struct v4l2_buffer v4l2_buf;
    struct v4l2_plane planes[MAX_PLANES];

    memset(&v4l2_buf, 0, sizeof(v4l2_buf));
    memset(planes, 0, sizeof(struct v4l2_plane) * MAX_PLANES);
    v4l2_buf.m.planes = planes;

    if (video_encoder_->output_plane.getNumQueuedBuffers() < video_encoder_->output_plane.getNumBuffers()) {
        v4l2_buf.index = video_encoder_->output_plane.getNumQueuedBuffers();
        v4l2_buf.m.planes[0].m.fd = dma_fd;
        v4l2_buf.m.planes[0].bytesused = 1;
        if (video_encoder_->output_plane.qBuffer(v4l2_buf, NULL) < 0) {
            AIMRTE_ERROR("Failed to queue buffer to output plane");
            return;
        }
    } else {
        // dq get buffer
        if (video_encoder_->output_plane.dqBuffer(v4l2_buf, NULL, NULL, 10) < 0) {
            AIMRTE_ERROR("Failed to dequeue buffer from output plane");
            return;
        }
        // dma_fd_pool_.push(v4l2_buf.m.planes[0].m.fd);
        v4l2_buf.m.planes[0].m.fd = dma_fd;
        if (running_.load())
            v4l2_buf.m.planes[0].bytesused = 1;
        else
            v4l2_buf.m.planes[0].bytesused = 0;

        if (video_encoder_->output_plane.qBuffer(v4l2_buf, NULL) < 0) {
            AIMRTE_ERROR("Failed to queue buffer to output plane");
            return;
        }
    }
}

std::shared_ptr<foxglove_msgs::msg::CompressedVideo> H264RawStreamer::GetFrame() {
    std::unique_lock<std::mutex> lock(queue_mtx_);
    cond_var_.wait(lock, [this] { return !running_.load() || !video_queue_.empty(); });
    if (video_queue_.empty()) {
        return nullptr;
    }
    auto msg = std::move(video_queue_.front());
    video_queue_.pop();
    return msg;
}

bool H264RawStreamer::encoderCallbackImpl(struct v4l2_buffer* v4l2_buf, NvBuffer* buffer, NvBuffer* shared_buffer) {
    if (!v4l2_buf) {
        video_encoder_->abort();
        AIMRTE_ERROR("Failed to dequeue buffer from capture plane");
        return false;
    }

    if (running_.load() == false) {
        video_encoder_->abort();
        return false;
    }

    const uint8_t* data = (const uint8_t*)buffer->planes[0].data;
    size_t size = buffer->planes[0].bytesused;

    auto msg = std::make_shared<foxglove_msgs::msg::CompressedVideo>();
    msg->frame_id = "camera_frame";
    msg->format = "h264";
    rclcpp::Clock clock(RCL_SYSTEM_TIME);
    msg->timestamp = clock.now();
    msg->data.resize(size);
    std::memcpy(msg->data.data(), data, size);

    {
        std::lock_guard<std::mutex> lock(queue_mtx_);
        video_queue_.push(msg);
    }
    cond_var_.notify_one();

    video_encoder_->capture_plane.qBuffer(*v4l2_buf, NULL);
    
    if (buffer->planes[0].bytesused == 0) {
        return false;
    }

    return true;
}

}