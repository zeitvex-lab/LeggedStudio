#include "convert.cuh"

// 数值截断函数
static __device__ int clamp(int val, int min, int max) {
    return val < min ? min : (val > max ? max : val);
}

// YUYV 到 BGR 转换核函数
__global__ void yuyv_to_bgr_kernel(
    const uint8_t* yuyv, 
    uint8_t* bgr, 
    int width, 
    int height
) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;

    if (x >= width / 2 || y >= height) return;

    // 计算输入和输出的内存偏移
    int in_idx = y * width * 2 + x * 4;    // 每行 width*2 字节，每线程处理 4 字节
    int out_idx = y * width * 3 + x * 6;   // 每行 width*3 字节，每线程输出 6 字节

    // 读取 YUYV 数据
    uint8_t y0 = yuyv[in_idx];
    uint8_t u0 = yuyv[in_idx + 1];
    uint8_t y1 = yuyv[in_idx + 2];
    uint8_t v0 = yuyv[in_idx + 3];

    // YUV 到 BGR 转换（BT.601 标准）
    // 公式简化：使用整数运算加速
    int c = y0 - 16;
    int d = u0 - 128;
    int e = v0 - 128;

    // 像素 1 (Y0-U0-V0)
    int b0 = clamp((298 * c + 516 * d + 128) >> 8, 0, 255);
    int g0 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8, 0, 255);
    int r0 = clamp((298 * c + 409 * e + 128) >> 8, 0, 255);

    // 像素 2 (Y1-U0-V0)
    c = y1 - 16;
    int b1 = clamp((298 * c + 516 * d + 128) >> 8, 0, 255);
    int g1 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8, 0, 255);
    int r1 = clamp((298 * c + 409 * e + 128) >> 8, 0, 255);

    // 写入 BGR 数据
    bgr[out_idx]     = b0;    // B0
    bgr[out_idx + 1] = g0;    // G0
    bgr[out_idx + 2] = r0;    // R0
    bgr[out_idx + 3] = b1;    // B1
    bgr[out_idx + 4] = g1;    // G1
    bgr[out_idx + 5] = r1;    // R1
}

__global__ void resize_bgr_kernel(
    const uint8_t* input_bgr, 
    uint8_t* output_bgr, 
    int input_width, 
    int input_height, 
    int output_width, 
    int output_height
) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;

    if (x >= output_width || y >= output_height) return;

    float scale_x = static_cast<float>(input_width) / output_width;
    float scale_y = static_cast<float>(input_height) / output_height;

    int src_x = min(static_cast<int>(x * scale_x), input_width - 1);
    int src_y = min(static_cast<int>(y * scale_y), input_height - 1);
    
    int src_idx = (src_y * input_width + src_x) * 3;
    int dst_idx = (y * output_width + x) * 3;

    output_bgr[dst_idx + 0] = input_bgr[src_idx + 0]; // B
    output_bgr[dst_idx + 1] = input_bgr[src_idx + 1]; // G
    output_bgr[dst_idx + 2] = input_bgr[src_idx + 2]; // R
}

__global__ void crop_yuyv_row_kernel(
    const uint32_t* src, int src_width, int src_height,
    uint32_t* dest, int dest_height, int y_start
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int pixels_per_row = src_width / 2;
    int total_pixels = pixels_per_row * dest_height;

    if (tid < total_pixels) {
        int dest_row = tid / pixels_per_row;
        int dest_col = tid % pixels_per_row;

        int src_row = y_start + dest_row;
        int src_idx = src_row * pixels_per_row + dest_col;

        dest[tid] = src[src_idx];
    }
}

__global__ void bgra_to_bgr_kernel(
    const uint8_t* __restrict__ in,
    uint8_t* __restrict__ out,
    int width, int height,
    int inpitch, int outpitch
) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= width || y >= height) return;

    const uint8_t* pInRow = in + (size_t)y * inpitch;
    uint8_t* pOutRow = out + (size_t)y * outpitch;

    // load 4 bytes as 32-bit (assumes little-endian BGRA in memory)
    uint32_t px = *((const uint32_t*)(pInRow + x * 4));
    uint8_t b = (uint8_t)(px & 0xFF);
    uint8_t g = (uint8_t)((px >> 8) & 0xFF);
    uint8_t r = (uint8_t)((px >> 16) & 0xFF);

    size_t outIdx = (size_t)x * 3;
    pOutRow[outIdx + 0] = b;
    pOutRow[outIdx + 1] = g;
    pOutRow[outIdx + 2] = r;
}

void yuyv_to_bgr_cuda(
    const uint8_t* YUYV,
    uint8_t* BGR,
    int width,
    int height
) {
    // 定义线程块和网格大小
    dim3 block(16, 16);
    dim3 grid((width / 2 + block.x - 1) / block.x, (height + block.y - 1) / block.y);

    // 启动核函数
    yuyv_to_bgr_kernel<<<grid, block>>>(YUYV, BGR, width, height);
    return;
}

void yuyv_to_bgr_and_resize_cuda(
    const uint8_t* YUYV,
    uint8_t* BGR,
    uint8_t* DST_BGR,
    int width,
    int height,
    int dst_width,
    int dst_height
) {
    // 定义线程块和网格大小
    dim3 block(16, 16);
    dim3 grid((width / 2 + block.x - 1) / block.x, (height + block.y - 1) / block.y);
    dim3 grid2((dst_width + block.x - 1) / block.x, (dst_height + block.y - 1) / block.y);

    // 启动核函数
    yuyv_to_bgr_kernel<<<grid, block>>>(YUYV, BGR, width, height);

    // resize
    resize_bgr_kernel<<<grid2, block>>>(BGR, DST_BGR, width, height, dst_width, dst_height);
    return;
}

void crop_yuyv_row_cuda(
    const uint32_t* src, int src_width, int src_height,
    uint32_t* dest, int dest_height, int y_start
) {
    // 定义线程块和网格大小
    const int pixels_per_row = src_width / 2;
    const int total_pixels = pixels_per_row * dest_height;
    const int block_size = 256; // 根据GPU调整
    const int grid_size = (total_pixels + block_size - 1) / block_size;

    // 启动核函数
    crop_yuyv_row_kernel<<<grid_size, block_size>>>(src, src_width, src_height, dest, dest_height, y_start);
}

void bgra_to_bgr_cuda(
    const uint8_t* BGRA,
    uint8_t* BGR,
    int width,
    int height
) {
    dim3 block(16, 16);
    dim3 grid((width + block.x -1)/block.x, (height + block.y -1)/block.y);
    auto inpitch = width * 4;
    auto outpitch = width * 3;
    bgra_to_bgr_kernel<<<grid, block>>>((const uint8_t*)BGRA, BGR,
                                            width, height, inpitch, (int)outpitch);
}