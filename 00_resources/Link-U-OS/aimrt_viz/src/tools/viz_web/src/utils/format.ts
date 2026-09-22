// 格式化时间
export const formatOnlineTime = (seconds: number | undefined): string => {
  if (seconds == null) return '离线';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

export const formatTimestamp = (timestamp: number): string => {
  if (timestamp === undefined || timestamp === null) return '未知';
  try {
    const date = new Date(Number(timestamp) / 1000000); // 纳秒转毫秒
    return date.toLocaleString();
  } catch (e) {
    return '无效时间戳';
  }
};

// 格式化内存
export const formatMemory = (kb: number, percent: number): string => {
  if (kb == null) return '-';

  const mb = kb / 1024;
  if (mb < 1024) {
    return `${mb.toFixed(1)} MB (${percent?.toFixed(1)}%)`;
  } else {
    return `${(mb / 1024).toFixed(2)} GB (${percent?.toFixed(1)}%)`;
  }
};

// 格式化百分比
export const formatPercentage = (value: number): string => {
  return value != null ? `${value.toFixed(1)}%` : '-';
};
